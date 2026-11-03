# Serato Offsets\_

    $ hexdump -C Serato\ Offsets_.octet-stream | head -4
    00000000  01 02 30 30 30 30 30 30  33 32 30 30 30 30 2e 30  |..000000320000.0|
    00000010  30 30 30 30 30 00 30 30  30 30 30 30 30 34 34 31  |00000.0000000441|
    00000020  30 30 2e 30 30 30 30 30  30 00 04 3e 43 00 04 09  |00.000000..>C...|
    00000030  0e 04 00 00 3f 6b 00 00  08 14 08 14 08 15 08 15  |....?k..........|

The `Serato Offsets_` tag is rare: a scan of 1,500 MP3s out of a 12k-track library found it on only 15 (about 1%). It is also large — 15–38 KB in the copies seen so far, growing with track length (the dump in `data/id3/` is 16,401 bytes).

The data is a header followed by a long binary table.

## Header

| Offset | Length | Raw Value                                | Decoded Value | Type                      | Description
| ------ | ------ | ---------------------------------------- | ------------- | ------------------------- | -----------
|   `00` |   `02` | `01 02`                                   |               | *?* (2 bytes)             | Version
|   `02` |   `14` | `000000320000.000000` + `00`              | 320,000       | ASCII number, NUL-ended   | Bitrate (bits per second)
|   `16` |   `14` | `000000044100.000000` + `00`              | 44,100        | ASCII number, NUL-ended   | Sample rate (Hz)

## Body

Everything after the header (offset `2a` onward) is an undecoded binary table. It is believed to be an index of where each MP3 frame sits in the file, so Serato can seek accurately — which would also explain why so few files carry the tag, if Serato only writes it for MP3s it cannot seek through on its own. Neither point is confirmed.
