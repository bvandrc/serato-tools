import os
from datetime import datetime

import pytest

from serato_tools.crate import Crate
from serato_tools.database_v2 import DatabaseV2
from serato_tools.smart_crate import SmartCrate, main

from test.helpers.bin_files import TEST_DATABASE, TEST_SMART_CRATE, TRACKS_DIR
from test.helpers.cli import cli_args
from test.helpers.files import copy_into, read_bytes, read_text

# the test smart crate parsed, as its __str__ prints it
TEST_SMART_CRATE_TXT_FILE = "test/data/smart_crate.txt"
Comparison = SmartCrate.RuleComparison
Field = SmartCrate.RuleField
ValueField = SmartCrate.RuleFields
DbField = DatabaseV2.Fields


def rule_entries(
    comparison: Comparison, field: Field, value_field: ValueField, value: str | int
) -> SmartCrate.EntryList:
    """A rule's entries, as Serato writes them."""
    return [
        (ValueField.RULE_COMPARISON.value, comparison.value),
        (ValueField.RULE_FIELD.value, field.value),
        (value_field.value, value),
    ]


def make_rule(comparison: Comparison, field: Field, value_field: ValueField, value: str | int) -> SmartCrate.Rule:
    return SmartCrate.Rule(rule_entries(comparison, field, value_field, value))


def test_parse():
    crate = SmartCrate(TEST_SMART_CRATE)
    assert crate.to_bytes() == read_bytes(TEST_SMART_CRATE), "round-trips byte-exact"
    assert crate.__str__() == read_text(TEST_SMART_CRATE_TXT_FILE)


def test_add_rule():
    crate = SmartCrate(TEST_SMART_CRATE)
    expected = read_text(TEST_SMART_CRATE_TXT_FILE)

    crate.set_rule(Field.ALBUM, Comparison.STR_IS_NOT, "albo")
    assert crate.__str__() == (
        expected
        + "\nrurt (SmartCrate Rule): [ trft (Rule Comparison): cond_isn_str (STR_IS_NOT) ], [ urkt (Rule Field): 8 (album) ], [ trpt (Rule Value Text): albo ]"
    )


def test_delete_rule_returns_whether_removed():
    crate = SmartCrate(TEST_SMART_CRATE)

    assert crate.delete_rule(Field.ALBUM) is False, "the crate has no album rule"
    assert not crate.has_changed
    assert crate.delete_rule(Field.GROUPING) is True
    assert crate.delete_rule(Field.GROUPING) is False, "the grouping rule was already removed"


@pytest.mark.parametrize(
    "value_field, value",
    [
        pytest.param(ValueField.RULE_VALUE_INTEGER, 0, id="RULE_VALUE_INTEGER"),
        pytest.param(ValueField.RULE_VALUE_TEXT, "", id="RULE_VALUE_TEXT"),
        pytest.param(ValueField.RULE_VALUE_DATE, "", id="RULE_VALUE_DATE"),
    ],
)
def test_rule_falsy_value_reads_back(value_field: ValueField, value: str | int):
    rule = make_rule(Comparison.INT_IS_GE, Field.PLAYS, value_field, value)
    assert rule.value == value, "a falsy rule value must not read as no value"


@pytest.mark.parametrize("comparison", Comparison, ids=lambda c: c.name)
def test_every_comparison_maps_to_a_value_field(comparison: Comparison):
    # the suffix lookup must cover every comparison, so a comparison with an unknown suffix
    # fails here rather than at set_rule time
    assert SmartCrate._get_rule_value_field(comparison.value) in SmartCrate.RULE_VALUE_FIELDS


def test_rule_value_field_follows_comparison_not_value_type():
    ARGS = (Comparison.STR_IS, Field.ARTIST, ValueField.RULE_VALUE_TEXT)
    # confirmed against Serato itself: an artist rule set to 100 is stored as the text "100",
    # so the comparison, not the passed value's type, decides the value field
    rule = make_rule(*ARGS, "some artist")
    rule.set_value(100)
    assert rule.to_entries() == rule_entries(*ARGS, "100")


def test_rule_set_value_replaces_value_field_on_comparison_type_change():
    rule = make_rule(Comparison.STR_IS, Field.PLAYS, ValueField.RULE_VALUE_TEXT, "100")
    rule.set_comparison(Comparison.INT_IS_GE)
    rule.set_value("100")
    # the old text value field replaced in place, not kept alongside the integer field
    assert rule.to_entries() == rule_entries(Comparison.INT_IS_GE, Field.PLAYS, ValueField.RULE_VALUE_INTEGER, 100)


def test_rule_set_value_rejects_non_integer_for_integer_comparison():
    rule = make_rule(Comparison.INT_IS_GE, Field.PLAYS, ValueField.RULE_VALUE_INTEGER, 5)
    with pytest.raises(ValueError, match="requires an integer value"):
        rule.set_value("abc")


def test_rule_properties_follow_its_entries():
    rule = make_rule(Comparison.INT_IS_GE, Field.PLAYS, ValueField.RULE_VALUE_INTEGER, 5)
    rule.set_comparison(Comparison.STR_CONTAINS)
    rule.set_field(Field.GENRE)
    rule.set_value("House")
    assert (rule.comparison, rule.field, rule.value) == (
        Comparison.STR_CONTAINS.value,
        Field.GENRE.value,
        "House",
    ), "set through its setters"

    rule.remove_field(ValueField.RULE_VALUE_TEXT)
    assert rule.value is None, "removed"


def test_to_regular_crate_keeps_the_tracks_sort_and_columns_but_not_the_rules(tmp_dir: str):
    smart_crate = SmartCrate(TEST_SMART_CRATE)
    view_fields = {Crate.Fields.SORTING.value, Crate.Fields.COLUMN.value}
    rule_fields = {field.value for field in ValueField}
    assert smart_crate.get_track_paths(), "the fixture has tracks"
    assert any(field in view_fields for field, _ in smart_crate._entries), "and a sort and columns"
    assert any(field in rule_fields for field, _ in smart_crate._entries), "and rules"
    file = os.path.join(tmp_dir, "Regular.crate")
    smart_crate.to_regular_crate(file).save()

    saved = Crate(file)
    assert saved._version == Crate.DEFAULT_ENTRIES[0][1], "a regular crate's version"
    assert saved.get_track_paths() == smart_crate.get_track_paths()
    assert saved._entries[1:] == [entry for entry in smart_crate._entries[1:] if entry[0] not in rule_fields], (
        "everything but the version and the rules, in order"
    )


def make_database(tmp_dir: str, tracks: dict[str, SmartCrate.EntryList]) -> DatabaseV2:
    """A database in `tmp_dir` holding only `tracks`, in order: each file's name in TRACKS_DIR, with its fields."""
    db = DatabaseV2(copy_into(tmp_dir, TEST_DATABASE, DatabaseV2.FILENAME))
    db._entries = [
        db._entries[0],
        *(
            (DbField.TRACK.value, [(DbField.FILE_PATH.value, f"{TRACKS_DIR}/{name}"), *fields])
            for name, fields in tracks.items()
        ),
    ]
    return db


def new_smart_crate(tmp_dir: str, *, match_all: bool = False) -> SmartCrate:
    """A new smart crate in `tmp_dir`, without rules or tracks, matching all its rules or any of them."""
    crate = SmartCrate.new(os.path.join(tmp_dir, "Test.scrate"))
    crate._entries = [
        (field, [(ValueField.SETTING_VALUE.value, match_all)])
        if field == ValueField.SMARTCRATE_MATCH_ALL
        else (field, value)
        for field, value in crate._entries
    ]
    return crate


def track_names(crate: SmartCrate) -> list[str]:
    """The file name of each of the crate's tracks, in order."""
    return [os.path.basename(path) for path in crate.get_track_paths()]


def added_on(day: str) -> int:
    """The Unix timestamp of noon on `day` (month/day/year), on this computer's clock, as the database holds it."""
    return int(datetime.strptime(day + " 12", "%m/%d/%Y %H").timestamp())  # noqa: DTZ007


ARTISTS = {
    "Zeds.mp3": [(DbField.ARTIST.value, "Zeds Dead")],
    "Tripp.mp3": [(DbField.ARTIST.value, "Tripp St.")],
    "No Artist.mp3": [],
}
PLAYS = {
    "Five.mp3": [(DbField.PLAY_COUNT.value, 5)],
    "Three.mp3": [(DbField.PLAY_COUNT.value, 3)],
    # Serato leaves the play count out until the track is first played
    "None.mp3": [],
}
BPMS = {
    "128.mp3": [(DbField.BPM.value, "128.00")],
    "127.98.mp3": [(DbField.BPM.value, "127.98")],
    "No BPM.mp3": [],
}
ADDED = {
    "Before.mp3": [(DbField.DATE_ADDED_U.value, added_on("5/12/2020"))],
    "On.mp3": [(DbField.DATE_ADDED_U.value, added_on("5/13/2020"))],
    "After.mp3": [(DbField.DATE_ADDED_U.value, added_on("5/14/2020"))],
}


@pytest.mark.parametrize(
    "tracks, field, comparison, value, expected",
    [
        (ARTISTS, Field.ARTIST, Comparison.STR_CONTAINS, "DEAD", ["Zeds.mp3"]),
        (ARTISTS, Field.ARTIST, Comparison.STR_DOES_NOT_CONTAIN, "dead", ["Tripp.mp3", "No Artist.mp3"]),
        (ARTISTS, Field.ARTIST, Comparison.STR_IS, " zeds dead ", ["Zeds.mp3"]),
        (ARTISTS, Field.ARTIST, Comparison.STR_IS_NOT, "zeds dead", ["Tripp.mp3", "No Artist.mp3"]),
        (ARTISTS, Field.ARTIST, Comparison.STR_IS, "", ["No Artist.mp3"]),
        (ARTISTS, Field.FILENAME, Comparison.STR_IS, "tripp.mp3", ["Tripp.mp3"]),
        (PLAYS, Field.PLAYS, Comparison.INT_IS_GE, 3, ["Five.mp3", "Three.mp3"]),
        (PLAYS, Field.PLAYS, Comparison.INT_IS_LE, 3, ["Three.mp3", "None.mp3"]),
        (BPMS, Field.BPM, Comparison.INT_IS_GE, 128, ["128.mp3"]),
        (BPMS, Field.BPM, Comparison.INT_IS_LE, 127, ["No BPM.mp3"]),
        (ADDED, Field.ADDED, Comparison.TIME_IS_AFTER, "5/13/2020", ["After.mp3"]),
        (ADDED, Field.ADDED, Comparison.TIME_IS_BEFORE, "5/13/2020", ["Before.mp3"]),
    ],
    ids=lambda v: getattr(v, "name", None),
)
def test_update_tracks_matches_each_comparison(
    tmp_dir: str,
    tracks: dict[str, SmartCrate.EntryList],
    field: Field,
    comparison: Comparison,
    value: str | int,
    expected: list[str],
):
    crate = new_smart_crate(tmp_dir)
    crate.set_rule(field, comparison, value)
    assert crate.update_tracks(make_database(tmp_dir, tracks)) is True
    assert track_names(crate) == expected


@pytest.mark.parametrize(
    "match_all, expected",
    [(True, ["Both.mp3"]), (False, ["Both.mp3", "Artist Only.mp3", "Genre Only.mp3"])],
    ids=["match all", "match any"],
)
def test_update_tracks_matches_all_rules_or_any(tmp_dir: str, match_all: bool, expected: list[str]):
    db = make_database(
        tmp_dir,
        {
            "Both.mp3": [(DbField.ARTIST.value, "Zeds Dead"), (DbField.GENRE.value, "Dubstep")],
            "Artist Only.mp3": [(DbField.ARTIST.value, "Zeds Dead")],
            "Genre Only.mp3": [(DbField.GENRE.value, "Dubstep")],
            "Neither.mp3": [],
        },
    )
    crate = new_smart_crate(tmp_dir, match_all=match_all)
    crate.set_rule(Field.ARTIST, Comparison.STR_IS, "Zeds Dead")
    crate.set_rule(Field.GENRE, Comparison.STR_IS, "Dubstep")
    crate.update_tracks(db)
    assert track_names(crate) == expected


@pytest.mark.parametrize("match_all", [True, False], ids=["match all", "match any"])
def test_update_tracks_without_rules_matches_nothing(tmp_dir: str, match_all: bool):
    crate = new_smart_crate(tmp_dir, match_all=match_all)
    crate.add_tracks([f"{TRACKS_DIR}/Zeds.mp3"])
    assert crate.update_tracks(make_database(tmp_dir, ARTISTS)) is True
    assert track_names(crate) == []


def test_update_tracks_keeps_the_order_of_tracks_still_matched(tmp_dir: str):
    db = make_database(tmp_dir, {name: [(DbField.GENRE.value, "House")] for name in ["A.mp3", "B.mp3", "C.mp3"]})
    crate = new_smart_crate(tmp_dir)
    crate.set_rule(Field.GENRE, Comparison.STR_IS, "House")
    # C held twice, once in another case, and Gone no longer in the database
    crate.add_tracks(f"{TRACKS_DIR}/{name}" for name in ["C.mp3", "Gone.mp3", "A.mp3"])
    crate._entries.append((DbField.TRACK.value, [(DbField.TRACK_PATH.value, f"{TRACKS_DIR}/c.MP3")]))

    assert crate.update_tracks(db) is True
    assert track_names(crate) == ["C.mp3", "A.mp3", "B.mp3"], "kept in order, unmatched and repeats gone, new last"
    assert crate.update_tracks(db) is False, "already up to date"


def test_update_tracks_refuses_a_comparison_it_cant_match(tmp_dir: str):
    crate = new_smart_crate(tmp_dir)
    crate.set_rule(Field.YEAR, Comparison.STR_DATE_BEFORE, "2000")
    with pytest.raises(NotImplementedError, match="STR_DATE_BEFORE"):
        crate.update_tracks(make_database(tmp_dir, ARTISTS))
    assert crate.get_track_paths() == [], "no track added"


TEXT_RULE = rule_entries(Comparison.STR_IS, Field.ARTIST, ValueField.RULE_VALUE_TEXT, "x")


@pytest.mark.parametrize(
    "rule, error",
    [
        (TEXT_RULE[:2], "has no value"),
        ([(ValueField.RULE_COMPARISON.value, "cond_new_str"), *TEXT_RULE[1:]], "unknown rule field or comparison"),
        (
            rule_entries(Comparison.TIME_IS_AFTER, Field.YEAR, ValueField.RULE_VALUE_DATE, "5/13/2020"),
            "only the added field",
        ),
        (
            rule_entries(Comparison.TIME_IS_AFTER, Field.ADDED, ValueField.RULE_VALUE_DATE, "2020-05-13"),
            "month/day/year",
        ),
    ],
    ids=["no value", "unknown comparison", "time comparison of another field", "date not month/day/year"],
)
def test_update_tracks_refuses_a_rule_it_cant_read(tmp_dir: str, rule: SmartCrate.EntryList, error: str):
    crate = new_smart_crate(tmp_dir)
    crate.add_tracks([f"{TRACKS_DIR}/Zeds.mp3"])
    crate._entries.append((ValueField.SMARTCRATE_RULE.value, rule))
    with pytest.raises(ValueError, match=error):
        crate.update_tracks(make_database(tmp_dir, ARTISTS))
    assert track_names(crate) == ["Zeds.mp3"], "tracks unchanged"


def test_fixture_rules_can_all_be_matched(tmp_dir: str):
    # every rule Serato wrote in the fixture, including its added date, is one update_tracks can match
    crate = SmartCrate(TEST_SMART_CRATE)
    crate.update_tracks(make_database(tmp_dir, ARTISTS))
    assert crate.get_track_paths() == [], "nothing in the database matches its label rule, so all of them"


def test_set_rule_and_delete_rule_update_tracks_only_when_given_a_database(tmp_dir: str):
    db = make_database(tmp_dir, ARTISTS)
    crate = new_smart_crate(tmp_dir)

    crate.set_rule(Field.ARTIST, Comparison.STR_CONTAINS, "dead")
    assert track_names(crate) == [], "rules only"
    crate.set_rule(Field.ARTIST, Comparison.STR_CONTAINS, "dead", update_tracks=db)
    assert track_names(crate) == ["Zeds.mp3"]

    crate.set_rule(Field.GENRE, Comparison.STR_IS, "House")
    assert crate.delete_rule(Field.ARTIST) is True
    assert track_names(crate) == ["Zeds.mp3"], "rules only"
    assert crate.delete_rule(Field.GENRE, update_tracks=db) is True
    assert track_names(crate) == [], "no rules left"


def test_set_rule_and_delete_rule_change_nothing_when_updating_tracks_fails(tmp_dir: str):
    db = make_database(tmp_dir, ARTISTS)
    crate = new_smart_crate(tmp_dir)
    crate.set_rule(Field.YEAR, Comparison.STR_DATE_BEFORE, "2000")
    before = crate.to_bytes()

    with pytest.raises(NotImplementedError):
        crate.set_rule(Field.ARTIST, Comparison.STR_IS, "Zeds Dead", update_tracks=db)
    assert crate.to_bytes() == before, "the new rule not added"
    with pytest.raises(NotImplementedError):
        crate.set_rule(Field.YEAR, Comparison.STR_DATE_AFTER, "1990", update_tracks=db)
    assert crate.to_bytes() == before, "the rule not changed"

    crate.set_rule(Field.ARTIST, Comparison.STR_IS, "Zeds Dead")
    before = crate.to_bytes()
    with pytest.raises(NotImplementedError):
        crate.delete_rule(Field.ARTIST, update_tracks=db)
    assert crate.to_bytes() == before, "the rule not removed"


def test_printing_shows_a_comparison_or_field_it_doesnt_know():
    crate = SmartCrate(TEST_SMART_CRATE)
    # a rule a newer Serato could write
    rule = [(ValueField.RULE_COMPARISON.value, "cond_new"), (ValueField.RULE_FIELD.value, 999)]
    crate._entries.append((ValueField.SMARTCRATE_RULE.value, rule))
    printed = str(crate)
    assert "cond_new (unknown)" in printed
    assert "999 (unknown)" in printed


class TestCli:
    """The serato_smartcrate CLI, run on a copy of the test smart crate."""

    @pytest.fixture
    def path(self, tmp_dir: str) -> str:
        return copy_into(tmp_dir, TEST_SMART_CRATE)

    def run_cli(self, path: str, *args: str) -> str:
        """Runs `serato_smartcrate` on `path` with `args`, and returns what it printed to stdout."""
        with cli_args("serato_smartcrate", path, *args) as stdout:
            main()
        return stdout.getvalue()

    def saved_rules(self, path: str) -> dict[Field, tuple[str, str | int | None]]:
        """Each rule in the crate saved at `path`, by field, as its comparison and value."""
        rules = [
            SmartCrate.Rule(v)
            for f, v in SmartCrate(path)._entries
            if f == ValueField.SMARTCRATE_RULE and isinstance(v, list)
        ]
        return {Field(r.field): (r.comparison, r.value) for r in rules}

    def test_sets_and_deletes_rules(self, path: str):
        assert Field.YEAR in self.saved_rules(path)
        self.run_cli(path, "--GROUPING", "str_is", "UNTAGGED", "--Plays", "INT_IS_GE", "3", "--year", "delete")
        rules = self.saved_rules(path)
        assert rules[Field.GROUPING] == ("cond_is_str", "UNTAGGED"), "field option in any case"
        assert rules[Field.PLAYS] == ("cond_greq_uint", 3), "field option and comparison in any case"
        assert Field.YEAR not in rules, "DELETE in any case"

    def test_new_rules_are_added_in_the_order_given(self, path: str):
        self.run_cli(path, "--genre", "str_is", "G", "--album", "str_is", "A")
        assert list(self.saved_rules(path))[-2:] == [Field.GENRE, Field.ALBUM]

    def test_rules_set_to_their_values_dont_rewrite_the_crate(self, path: str, bin_file_writes: list[str]):
        self.run_cli(path, "--year", "str_is", "2000", "--label", "str_contains", "YT")
        assert bin_file_writes == []

    def test_without_rule_options_prints_the_crate_and_changes_nothing(self, path: str, bin_file_writes: list[str]):
        assert "SmartCrate Rule" in self.run_cli(path)
        assert bin_file_writes == []

    def test_update_tracks_rewrites_each_crates_tracks_after_its_rules(self, path: str, tmp_dir: str):
        db = make_database(tmp_dir, ARTISTS)
        db.save()
        self.run_cli(
            path,
            "--artist",
            "str_contains",
            "dead",
            "--label",
            "delete",
            "--year",
            "delete",
            "--grouping",
            "delete",
            "--added",
            "delete",
            "--update_tracks",
            "--database",
            db.filepath,
        )
        assert track_names(SmartCrate(path)) == ["Zeds.mp3"]

    def test_update_tracks_without_rule_options_only_updates_tracks(self, path: str, tmp_dir: str):
        db = make_database(tmp_dir, ARTISTS)
        db.save()
        rules = self.saved_rules(path)
        self.run_cli(path, "--update_tracks", "--database", db.filepath)
        assert self.saved_rules(path) == rules
        assert SmartCrate(path).get_track_paths() == [], "nothing in the database matches its rules"

    def test_update_tracks_leaves_a_crate_it_cant_match_unchanged(
        self, path: str, tmp_dir: str, bin_file_writes: list[str]
    ):
        db = make_database(tmp_dir, ARTISTS)
        db.save()
        bin_file_writes.clear()
        with pytest.raises(SystemExit) as exit_info:
            self.run_cli(path, "--year", "str_date_before", "2000", "--update_tracks", "--database", db.filepath)
        assert exit_info.value.code == 1
        assert bin_file_writes == [], "neither its rules nor its tracks saved"

    @pytest.mark.parametrize(
        "args",
        [
            ["--nope", "str_is", "X"],
            ["--grouping", "nope", "X"],
            ["--grouping", "str_is"],
            ["--grouping", "str_is", "X", "Y"],
            ["--plays", "int_is_ge", "abc"],
        ],
        ids=" ".join,
    )
    def test_bad_rule_options_change_nothing(self, path: str, bin_file_writes: list[str], args: list[str]):
        with pytest.raises(SystemExit):
            self.run_cli(path, *args)
        assert bin_file_writes == []
