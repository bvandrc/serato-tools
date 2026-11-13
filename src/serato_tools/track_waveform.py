#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The `Serato Overview` tag, which holds the waveform overview Serato shows for a track.

It can draw the overview as an image, which needs the `waveform_drawing` extra (pillow).
"""

import io
from dataclasses import dataclass

from mutagen.mp3 import HeaderNotFoundError

from serato_tools.utils import logger
from serato_tools.utils.track_tags import GeobKeys, NoWaveformError, SeratoGeobTag


class TrackWaveform(SeratoGeobTag):
    """The `Serato Overview` tag, which holds the track's waveform overview.

    `data` holds the overview as 240 rows of 16 bytes.

    Raises NoWaveformError when read from a file Serato hasn't built the overview for yet.
    """

    GEOB_KEY = GeobKeys.WAVEFORM
    VERSION = (0x01, 0x05)

    def __init__(self, file_or_data: SeratoGeobTag.FileOrData):
        super().__init__(file_or_data)

        if self._raw_data is None:
            raise NoWaveformError(self.filename)

        # materialize so the version check runs at construction time and the data can be read repeatedly
        self.data = self._parse(self._raw_data)

    def _parse(self, data: bytes) -> list[bytearray]:
        """Parse the waveform data into its 16-byte rows.

        Deliberately a list, not a generator: a generator would defer the body — including the
        version check — to first iteration, letting an untested tag version construct silently,
        and could only be consumed once (a second draw_image() would find it exhausted). The tag
        is a fixed 240 rows of 16 bytes, so materializing costs nothing meaningful.
        """
        fp = io.BytesIO(data)
        self._check_version(fp.read(self.VERSION_LEN))

        rows: list[bytearray] = []
        for x in iter(lambda: fp.read(16), b""):
            if len(x) != 16:
                raise ValueError(f"waveform ends with a row of {len(x)} bytes, not 16")
            rows.append(bytearray(x))
        return rows

    def draw_image(self):
        """The waveform overview as a 240 x 16 pixel PIL image. Needs the `waveform_drawing` extra (pillow)."""
        try:
            from PIL import Image, ImageColor
        except:
            logger.error('must install package "pillow"')
            raise

        img = Image.new("RGB", (240, 16), "black")
        pixels = img.load()

        if len(self.data) < img.size[0]:
            raise ValueError(f"waveform data has {len(self.data)} rows, expected at least {img.size[0]}")

        for i in range(img.size[0]):
            rowdata = self.data[i]
            factor = len([x for x in rowdata if x < 0x80]) / len(rowdata)

            for j, value in enumerate(rowdata):
                # The algorithm to derive the colors from the data has no real mathematical background and was found by experimenting with different values.
                color = "hsl({hue:.2f}, {saturation:d}%, {luminance:.2f}%)".format(
                    hue=(factor * 1.5 * 360) % 360,
                    saturation=40,
                    luminance=(value / 0xFF) * 100,
                )
                pixels[i, j] = ImageColor.getrgb(color)  # pyright: ignore[reportOptionalSubscript]

        return img


if __name__ == "__main__":
    import argparse

    @dataclass
    class Args:
        file: str

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = Args(**vars(parser.parse_args()))

    try:
        tags = TrackWaveform(args.file)
    except HeaderNotFoundError:
        with open(args.file, mode="rb") as fp:
            data = fp.read()
        tags = TrackWaveform(data)

    img = tags.draw_image()
    img.show()
