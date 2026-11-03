## Includes:

- Serato track tag parsing and modification, including cue points, track color, beatgrid, waveform, autogain, etc.
- Serato library database parsing and modification
- Serato crate parsing and modification
- Serato smart crate parsing and rule modification
- Dynamic beatgrid analysis that can be saved to a track's beatgrid.
- Serato USB export that beats Serato's sync by putting all files in 1 folder (without duplicates) and only copying changed files, unlike Serato's sync which takes forever and creates many duplicate file locations

## Contents

- [Example uses](#example-uses)
- [Installation](#installation)
- [Examples](#examples)
  - [Renaming or removing track files across the library](#renaming-or-removing-track-files-across-the-library)
  - [Modifying the database file](#modifying-the-database-file)
  - [Exporting crates to USB](#exporting-crates-to-usb)
  - [Analyzing and setting a dynamic beatgrid](#analyzing-and-setting-a-dynamic-beatgrid)
  - [Setting track color](#setting-track-color)
  - [Snapping cue positions to the beatgrid](#snapping-cue-positions-to-the-beatgrid)
  - [Modifying track metadata / hot cues](#modifying-track-metadata--hot-cues)
  - [Listing available crates or smart crates](#listing-available-crates-or-smart-crates)
  - [Modifying a SmartCrate Rule](#modifying-a-smartcrate-rule)
  - [Crate details and adding a track](#crate-details-and-adding-a-track)
  - [Smart Crate details](#smart-crate-details)
- [Track Tags](#track-tags)
- [Sources](#sources)
- [Contributing](#contributing)

## Example uses:

**USB:**
- Export crates (including Smart Crates) to USB. Beats Serato's sync by keeping all files in 1 folder and by comparing files for changes (instead of always copying, like Serato does)

**Tracks:**
- Change hot cue's text (i.e. change to all caps; change "c" to "CHORUS", etc.)
- Set a hot cue's text based on its color (i.e. if RED, set to "EXIT")
- Set a track's color (i.e. if has hot cues, change to BLUE)
- Set a piece of metadata due to a track's color (i.e. if track is green, set "grouping" to "TAGGED") (this is useful since can't create smart crates by track color in Serato)
- Analyze a track's Dynamic Beatgrid and save it to the beatgrid Serato tag.
 - Snap cue points to the nearest beat with a configurable tolerance (e.g. 1/16, 1/8, 1/4 of a beat).

**Library:**
- Rename or delete a track file while updating the database, crates, and smart crates as well, so that it doesn't go missing.

**Database:**
- After changing a track's metadata, modify database values for a specific track so that you don't have to "Reload Id3 Tags" in Serato, the change appears in Serato instantly.

**Crate:**
- Read a crate's tracks
- Remove a track from a crate
- Add a track to a crate
- List available crates

**Smart Crate:**
- Read a smart crate's tracks and rules
- Modify a smart crate's rules
- List available smart crates

# Installation

**Currently designed for Python 3.12+. If you would like backwards compatibility with an older version, please reach out!**

```cmd
pip install serato-tools
```

The following deps are optional, but **must be installed based on what features you want to use** (each is also available as a package extra, e.g. `pip install "serato-tools[track_tags]"`):

- For getting/modifying track metadata including tags, cue points, beatgrid, and waveform, must install `pip install mutagen` (extra: `track_tags`)
- For viewing a track's waveform, must install `pip install pillow` (extra: `waveform_drawing`)
- For beatgrid analysis, must install `pip install numpy` and `pip install librosa` (extra: `beatgrid_analysis`)

# Examples

### Renaming or removing track files across the library

`Library` changes a track file and every place Serato points to it: the database, crates, and smart crates, so the track isn't left missing in Serato. Each file is parsed the first time it's needed and then kept, so many changes in a row stay fast. Keep one `Library` per library folder, since another copy's save would overwrite this one's changes.

_NOTE: Recommended to make a backup of the `_Serato_` folder elsewhere, before modifying via this package, in case an unforseen bug appears._

```python
from serato_tools.library import Library

library = Library()  # or Library("/Volumes/USB/_Serato_") for a library on another drive
library.rename_track_file(
    src="/Users/Username/Music/Dubstep/Raaket - ILL - Original Mix.mp3",
    dest="/Users/Username/Music/Dubstep/Raaket - ILL.mp3",
)
library.remove_track_files(["/Users/Username/Music/Dubstep/Raaket - ILL (Radio Edit).mp3"])  # deletes the files too
```

### Modifying the database file

_NOTE: Recommended to make a backup of the database file elsewhere, before modifying via this package, in case an unforseen bug appears._

```python
import time
from typing import Any

from serato_tools.database_v2 import DatabaseV2

now = int(time.time())
files_set_date = ["/Users/Username/Music/Dubstep/Raaket - ILL.mp3"]

def modify_uadd(filename: str, prev_val: Any):
    print(f'Serato library change - Changed "date added" to today: {filename}')
    return now

def modify_tadd(filename: str, prev_val: Any):
    return str(now)

def remove_group(filename: str, prev_val: Any):
    return " "

db = DatabaseV2()
# the available fields are in DatabaseV2.Fields
db.modify_and_save(
    rules=[
        {"field": DatabaseV2.Fields.DATE_ADDED_U, "files": files_set_date, "func": modify_uadd},
        {"field": DatabaseV2.Fields.DATE_ADDED_T, "files": files_set_date, "func": modify_tadd},
        {"field": DatabaseV2.Fields.GROUPING, "func": remove_group}, # all files
    ]
)
```

### Exporting crates to USB

**NOTE: replaces existing crates on flash drive! (but does not delete existing track files) (TODO: ability to merge with existing)**

```cmd
>>> serato_usb_export --drive E --crate_matcher "*house*" "*techno*" --root_crate="Dave USB"
```

### Analyzing and setting a dynamic beatgrid

 Rekordbox has Dynamic Beatgrid Analysis but Serato doesn't. This analyzes a non-consistent BPM across a track, such as a track with live drums, and snaps a beatgrid marker to each beat.

_NOTE: This feature has only been tested on a couple of tracks. Recommend reviewing the resulting beatgrid in Serato— some grid markers may require adjustment. It seems to be working pretty great though!_

```cmd
>>> serato_analyze_beatgrid "/Users/Username/Music/Dubstep/Raaket - ILL.mp3"
```

### Setting track color

```python
from serato_tools.track_cues_v2 import TrackCuesV2

tags = TrackCuesV2('/Users/Username/Music/Dubstep/Raaket - ILL.mp3')
tags.set_track_color(
    TrackCuesV2.TrackColors.PURPLE,
    delete_tags_v1=True
    # delete_tags_v1 (the default) deletes the legacy "Serato Markers_" tag, since a stale one stops the new color from appearing in Serato. No issues have been found from deleting it, but use caution with versions of Serato before 3, which may still read it.
)
tags.save()
```

### Snapping cue positions to the beatgrid

After you have a good beatgrid (including dynamic beatgrids), you can snap cue positions so they land exactly on beats, within a configurable tolerance:

```cmd
serato_snap_cues_v2 "/Users/Username/Music/Dubstep/Raaket - ILL.mp3" --snap_cues --snap_tolerance 1/16
```

- `--snap_cues` enables snapping for all cue entries in the `Serato Markers2` tag.
- `--snap_tolerance` is a fraction of a beat (e.g. `1/16`, `1/8`, `1/4`) that a cue point can come within a beat in order to "snap" to it.

Only cue points within the tolerance window of some beat are moved; others are left unchanged.

### Modifying track metadata / hot cues

```python
import dataclasses
from mutagen.id3._frames import TIT1
from serato_tools.track_cues_v2 import TrackCuesV2

CueColors = TrackCuesV2.CueColors
TrackColors = TrackCuesV2.TrackColors

tags = TrackCuesV2('/Users/Username/Music/Dubstep/Raaket - ILL.mp3')

def track_rule(track: TrackCuesV2.TrackCuesInfo) -> TrackCuesV2.TrackCuesInfo | None:
    # Set ID3 grouping field from track color
    if track.color is not None:
        track_color = track.color.color
        if track_color == TrackColors.LIMEGREEN3.value:
            tags.tagfile.tags.setall("TIT1", [TIT1(text="TAGGED")])
        elif track_color in [TrackColors.WHITE.value, TrackColors.GREY.value, TrackColors.BLACK.value]:
            tags.tagfile.tags.setall("TIT1", [TIT1(text="UNTAGGED")])

    # Normalize cue colors and names
    new_cues = []
    for c in track.cues:
        # Make "close to red", red.
        cue_color = CueColors.RED.value if c.color in [CueColors.PINKRED.value, CueColors.MAGENTA.value] else c.color
        # Make all cuenames all-caps
        cue_name = c.name.strip().upper()

        new_cues.append(dataclasses.replace(c, color=cue_color, name=cue_name))
    new_track = dataclasses.replace(track, cues=new_cues)
    return new_track if new_track != track else None

tags.modify_entries(track_rule, delete_tags_v1=True)
tags.save()
```

### Listing available crates or smart crates

```python
from serato_tools.crate import Crate
print('\n'.join(Crate.get_crate_files()))

from serato_tools.smart_crate import SmartCrate
print('\n'.join(SmartCrate.get_crate_files()))
``` 

### Modifying a SmartCrate Rule

__via command line__

Each rule takes a comparison and a value (or `DELETE` to remove the rule). The available comparisons are the `SmartCrate.RuleComparison` names, lowercase: `str_contains`, `str_is`, `int_is_ge`, etc.

_one crate_
```cmd
>>> serato_smartcrate '/Users/Username/Music/_Serato_/SmartCrates/Dubstep.scrate' --set_rules --grouping str_is UNTAGGED
```

_all crates_
```cmd
>>> serato_smartcrate --all --set_rules --grouping str_is UNTAGGED
```

__via code__

```python
from serato_tools.smart_crate import SmartCrate

crate = SmartCrate('/Users/Username/Music/_Serato_/SmartCrates/Dubstep.scrate')

# updates the rule on this field, or adds the rule if the crate doesn't have one for it.
# the value is stored in the value field the comparison expects, just like Serato does.
crate.set_rule(SmartCrate.RuleField.GROUPING, SmartCrate.RuleComparison.STR_IS, "UNTAGGED")
crate.save()
```

### Crate details and adding a track

```python
from serato_tools.crate import Crate

crate = Crate('/Users/Username/Music/_Serato_/Subcrates/Dubstep.crate')

crate.print_track_paths()
# /Users/Username/Music/Dubstep/Saka - backitup.mp3
# /Users/Username/Music/Dubstep/Mind Splitter - YAPPIN'.mp3
# /Users/Username/Music/Dubstep/Flozone - DO IT.mp3
# /Users/Username/Music/Dubstep/Evalution - Throw It Back.mp3
# ...

print(crate)  # or crate.print()
# vrsn (Version): 1.0/Serato ScratchLive Crate
# osrt (Sorting): [ tvcn (Column Name): key ], [ brev (Reverse Order): False ]
# ovct (Column): [ tvcn (Column Name): song ], [ tvcw (Column Width): 0 ]
# ovct (Column): [ tvcn (Column Name): artist ], [ tvcw (Column Width): 0 ]
# ovct (Column): [ tvcn (Column Name): bpm ], [ tvcw (Column Width): 0 ]
# ovct (Column): [ tvcn (Column Name): playCount ], [ tvcw (Column Width): 0 ]
# otrk (Track): [ ptrk (Track Path): Music/Dubstep/Flozone - Candy Paint.mp3 ]
# otrk (Track): [ ptrk (Track Path): Music/Dubstep/Mind Splitter - LISTEN TO ME.mp3 ]
# otrk (Track): [ ptrk (Track Path): Music/Dubstep/Flozone - DO IT.mp3 ]
# ...


# Example: Add tracks to the crate and save it as a new crate
crate.add_tracks(['/Users/Username/Music/Dubstep/Raaket - ILL.mp3'])
crate.save('/Users/Username/Music/_Serato_/Subcrates/New Crate.crate')
```

### Smart Crate details

```python
from serato_tools.smart_crate import SmartCrate

s_crate = SmartCrate('/Users/Username/Music/_Serato_/SmartCrates/Dubstep.scrate')
print(s_crate)
```

# Track Tags

Original writeup on Serato GEOB tag discoveries: [blog post](https://homepage.ruhr-uni-bochum.de/jan.holthuis/posts/reversing-seratos-geob-tags)

| GEOB Tag                                     | Contents                                                                        | Script File                                  |
| -------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------- |
| [`Serato Analysis`](https://github.com/bvandrc/serato-tools/blob/main/docs/serato_analysis.md) | Serato version information                                                      |
| [`Serato Autotags`](https://github.com/bvandrc/serato-tools/blob/main/docs/serato_autotags.md) | BPM and Gain values                                                             | [`track_autotags.py`](https://github.com/bvandrc/serato-tools/blob/main/src/serato_tools/track_autotags.py) |
| [`Serato BeatGrid`](https://github.com/bvandrc/serato-tools/blob/main/docs/serato_beatgrid.md) | Beatgrid Markers                                                                | [`track_beatgrid.py`](https://github.com/bvandrc/serato-tools/blob/main/src/serato_tools/track_beatgrid.py) |
| [`Serato Markers2`](https://github.com/bvandrc/serato-tools/blob/main/docs/serato_markers2.md) | Hotcues, Saved Loops, etc.<br>_(The main one used in newer versions of Serato)_ | [`track_cues_v2.py`](https://github.com/bvandrc/serato-tools/blob/main/src/serato_tools/track_cues_v2.py)   |
| [`Serato Markers_`](https://github.com/bvandrc/serato-tools/blob/main/docs/serato_markers_.md) | Hotcues, Saved Loops, etc.<br>_(Old, not used in newer versions of Serato)_     | [`track_cues_v1.py`](https://github.com/bvandrc/serato-tools/blob/main/src/serato_tools/track_cues_v1.py)   |
| [`Serato Overview`](https://github.com/bvandrc/serato-tools/blob/main/docs/serato_overview.md) | Waveform data                                                                   | [`track_waveform.py`](https://github.com/bvandrc/serato-tools/blob/main/src/serato_tools/track_waveform.py) |
| [`Serato Offsets_`](https://github.com/bvandrc/serato-tools/blob/main/docs/serato_offsets_.md) | ???                                                                             | -                                            |

What's still unknown in these formats — including the rare, mostly undecoded `Serato Offsets_` tag — is collected in [`docs/MYSTERIES.md`](https://github.com/bvandrc/serato-tools/blob/main/docs/MYSTERIES.md).

The different file/tag formats that Serato uses to store the information are documented in [`docs/fileformats.md`](https://github.com/bvandrc/serato-tools/blob/main/docs/fileformats.md), a script to dump the tag data can be found at [`track_tagdump.py`](https://github.com/bvandrc/serato-tools/blob/main/src/serato_tools/track_tagdump.py).

# Sources

- Serato track file tag parsing and modification from https://github.com/Holzhaus/serato-tags , which appears to be no longer maintained
- Serato crate parsing and modification from https://github.com/sharst/seratopy
- Dynamic beatgrid analysis from [https://github.com/heyitsmass/audio](https://github.com/heyitsmass/audio/blob/master/audio/beat_grid.py)

# Contributing

If you want a new feature, or have a bug fix, please put in a PR!
