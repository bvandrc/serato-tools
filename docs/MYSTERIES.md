# Mysteries

What's left to discover about Serato's tag formats. Everything else in each tag is decoded and documented in its own file in this folder.

## [`Serato BeatGrid`](serato_beatgrid.md)

- The single footer byte. It looks random, we just preserve it on round-trip, and a freshly analyzed beatgrid writes `0` — which Serato accepts — but nobody knows what it encodes.

## [`Serato Markers2`](serato_markers2.md)

- The two-byte tag header (`01 01`).
- Why Serato sometimes emits a base64 body that is one byte longer than a multiple of 4 (invalid base64). Appending an `A` before decoding works, but the reason is unknown.
- `FLIP` entry payloads. They aren't decoded — `FlipEntry` holds the raw bytes and writes them back unchanged.

## [`Serato Markers_`](serato_markers_.md)

- The two-byte tag header (`02 05`).
- Each entry's `field5`.

## [`Serato Offsets_`](serato_offsets_.md)

- The binary table that makes up nearly all of the tag. It is believed to be an index of where each MP3 frame sits in the file, so Serato can seek accurately — unconfirmed.
- When Serato writes the tag at all. It showed up on only ~1% of one 12,000-track MP3 library; the hypothesis is that Serato only writes it for MP3s it cannot seek through on its own — also unconfirmed.
- The tag is not parsed by this package yet.
