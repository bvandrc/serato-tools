from typing import Optional
from dataclasses import dataclass

from mutagen.id3._frames import RVA2


from serato_tools.utils.track_tags import ID3FileOrPath, ID3FileTag, del_tag


class TrackGain(ID3FileTag):
    # Serato stores gain in ID3 files as an RVA2 (relative volume adjustment, ID3v2.4 section 4.11) frame
    # with this description: see this repo's test/data/test_mp3.mp3, or the report of Serato DJ's manual
    # gain writing RVA2:SeratoGain in https://invent.kde.org/multimedia/kid3/-/issues/511
    RVA2_DESC = "SeratoGain"
    RVA2_KEY = f"RVA2:{RVA2_DESC}"

    def __init__(self, file: ID3FileOrPath):
        super().__init__(file)
        frame = self.tagfile.get(TrackGain.RVA2_KEY, None)
        self.gain: float | None = frame.gain if frame is not None else None
        self.peak: float | None = frame.peak if frame is not None else None
        # the values the tagfile holds, saved to disk or not, so _write_to_tagfile can tell if there's anything to write
        self._tagged = (self.gain, self.peak)

    def __str__(self) -> str:
        return f"gain: {self.gain}\npeak: {self.peak}"

    def set(self, gain: Optional[float] = None, peak: Optional[float] = None):
        """Sets the gain and/or peak in memory; call `save()` to write them to the file.

        Raises ValueError if that leaves either unset, which happens when the file had no SeratoGain frame.
        """
        if gain is not None:
            self.gain = gain
        if peak is not None:
            self.peak = peak
        if self.gain is None or self.peak is None:
            raise ValueError("both gain and peak must be set (file had no existing SeratoGain tag)")

    def set_and_save(self, gain: Optional[float] = None, peak: Optional[float] = None):
        self.set(gain, peak)
        self.save()

    def _write_to_tagfile(self) -> bool:
        if (self.gain, self.peak) == self._tagged:
            return False
        if self.gain is None and self.peak is None:
            del_tag(self.tagfile, TrackGain.RVA2_KEY)
        elif self.gain is None or self.peak is None:
            raise ValueError("both gain and peak must be set (file had no existing SeratoGain tag)")
        else:
            self.tagfile[TrackGain.RVA2_KEY] = RVA2(desc=TrackGain.RVA2_DESC, channel=1, gain=self.gain, peak=self.peak)
        self._tagged = (self.gain, self.peak)
        return True

    def save(self, force: bool = False):
        """Writes the gain and peak to the file, if they changed since it was read or last saved, or if `force`."""
        if self._write_to_tagfile() or force:
            self.tagfile.save()

    def delete(self):
        """Deletes the SeratoGain frame in memory, leaving gain and peak None; returns whether there was one."""
        self.gain = None
        self.peak = None
        return del_tag(self.tagfile, TrackGain.RVA2_KEY)


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
