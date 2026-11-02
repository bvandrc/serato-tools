import os
import sys
from typing import Optional
from dataclasses import dataclass

from mutagen.id3._frames import RVA2

if __package__ is None:
    sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))

from serato_tools.utils.track_tags import SeratoTrack


class TrackGain(SeratoTrack):
    # Serato stores gain in ID3 files as an RVA2 (relative volume adjustment) frame with this description
    RVA2_DESC = "SeratoGain"
    RVA2_KEY = f"RVA2:{RVA2_DESC}"

    def __init__(self, file: SeratoTrack.FileArg):
        super().__init__(file)
        frame = self.tagfile.get(TrackGain.RVA2_KEY, None)
        self.gain: float | None = frame.gain if frame is not None else None
        self.peak: float | None = frame.peak if frame is not None else None

    def __str__(self) -> str:
        return f"gain: {self.gain}\npeak: {self.peak}"

    def set_and_save(self, gain: Optional[float] = None, peak: Optional[float] = None):
        if gain is not None:
            self.gain = gain
        if peak is not None:
            self.peak = peak
        if self.gain is None or self.peak is None:
            raise ValueError("both gain and peak must be set (file had no existing SeratoGain tag)")

        self.tagfile[TrackGain.RVA2_KEY] = RVA2(desc=TrackGain.RVA2_DESC, channel=1, gain=self.gain, peak=self.peak)
        self.tagfile.save()

    def save(self):
        self.tagfile.save()

    def delete(self):
        return self._del_tag(TrackGain.RVA2_KEY)


if __name__ == "__main__":
    import argparse

    @dataclass
    class Args:
        file: str

    parser = argparse.ArgumentParser()
    parser.add_argument("file")
    args = Args(**vars(parser.parse_args()))

    tags = TrackGain(args.file)
    print(str(tags))
