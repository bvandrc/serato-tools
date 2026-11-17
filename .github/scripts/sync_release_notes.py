"""Rewrite each GitHub release's notes as its version's section of CHANGELOG.md.

Run by the Sync Release Notes workflow, with the `gh` CLI signed in to the repository. A release whose version has no
section is left alone, and so is one whose notes already match. The "Published to PyPI ..." paragraph the releases
added after the fact end with is kept.
"""

import argparse
import re
import subprocess

# "## [5.7.0] - 2026-11-15", or "## 5.2.1 - 2026-11-03" for a version without a tag to link
_VERSION_HEADING = re.compile(r"^## \[?([^\]\s]+)\]? - \d{4}-\d{2}-\d{2}\s*$")
_LINK_DEFINITION = re.compile(r"^\[[^\]]+\]: \S+$")
_PYPI_FOOTER = "Published to [PyPI]"


def changelog_sections(changelog: str) -> dict[str, str]:
    """Each version's section of the changelog, without its heading, by version."""
    sections: dict[str, list[str]] = {}
    lines: list[str] | None = None
    for line in changelog.splitlines():
        if match := _VERSION_HEADING.match(line):
            lines = sections.setdefault(match.group(1), [])
        elif line.startswith("## "):
            lines = None
        # the link definitions at the bottom of the file follow the last section, but aren't part of it
        elif lines is not None and not _LINK_DEFINITION.match(line):
            lines.append(line)
    return {version: "\n".join(lines).strip() for version, lines in sections.items()}


def release_notes(section: str, current_notes: str) -> str:
    """The notes for a release with this changelog section, keeping its current notes' PyPI footer if they have one."""
    current_notes = current_notes.replace("\r\n", "\n")
    footer_start = current_notes.find(_PYPI_FOOTER)
    if footer_start == -1:
        return section
    return f"{section}\n\n{current_notes[footer_start:].strip()}"


def _gh(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True, check=True).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--changelog", default="CHANGELOG.md")
    parser.add_argument("--dry-run", action="store_true", help="print the new notes without changing any release")
    args = parser.parse_args()

    with open(args.changelog, encoding="utf-8") as f:
        sections = changelog_sections(f.read())

    tags = _gh("release", "list", "--limit", "1000", "--json", "tagName", "--jq", ".[].tagName").split()
    changed = 0
    for tag in tags:
        section = sections.get(tag.removeprefix("v"))
        if not section:
            print(f"{tag}: no changelog section, left as is")
            continue
        current = _gh("release", "view", tag, "--json", "body", "--jq", ".body").rstrip("\n")
        notes = release_notes(section, current)
        if notes == current.replace("\r\n", "\n"):
            print(f"{tag}: already matches the changelog")
            continue
        changed += 1
        if args.dry_run:
            print(f"{tag}: would change its notes to:\n{notes}\n")
        else:
            _gh("release", "edit", tag, "--notes-file", "-", stdin=notes)
            print(f"{tag}: updated")
    print(f"{changed} release(s) {'would be ' if args.dry_run else ''}updated")


if __name__ == "__main__":
    main()
