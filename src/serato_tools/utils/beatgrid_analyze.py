# Built off of https://github.com/heyitsmass/audio/blob/master/audio/beat_grid.py

import sys
from dataclasses import asdict, dataclass
from typing import List, Optional

import librosa
import numpy as np


@dataclass
class BeatGridInfo:
    bpm: float
    beat_positions: List[float]
    confidence: float
    phase_offset: float
    grid_consistency: float
    downbeats: List[float]


def analyze_beatgrid(file: str, bpm_helper: Optional[int | float] = None):
    audio_data, sample_rate = librosa.load(
        file,
        sr=None,  # sample_rate = default
    )

    # Get tempo and beat frames
    tempo, beat_times = librosa.beat.beat_track(
        y=audio_data,
        sr=sample_rate,
        trim=False,
        tightness=100,
        units="time",
        bpm=bpm_helper,
    )

    # --- Calculate grid strength ---
    # Calculate inter-beat intervals
    ibis = np.diff(beat_times)

    # Calculate variance in intervals
    variance = np.var(ibis)
    mean_ibi = np.mean(ibis)

    # Calculate normalized strength metric
    grid_consistency = float(1.0 / (1.0 + variance / mean_ibi))

    # Calculate confidence based on grid strength and tempo stability
    confidence = float(grid_consistency * max(0.0, 1.0 - abs(tempo - 120) / 120))

    # --- Get downbeats ---
    # Find phase offset (time to first beat)
    phase_offset = beat_times[0] if len(beat_times) > 0 else 0.0

    # Calculate onset strength
    onset_env = librosa.onset.onset_strength(y=audio_data, sr=sample_rate)

    # Get onset peaks near beat positions
    downbeats: list[float] = []
    for beat_time in beat_times[::4]:  # Check every 4th beat
        beat_frame = int(beat_time * sample_rate / 512)  # Convert to onset frames
        if beat_frame < len(onset_env):
            window_start = max(0, beat_frame - 2)
            local_max = np.argmax(onset_env[window_start : min(len(onset_env), beat_frame + 3)])
            # local_max is relative to window_start, which is not beat_frame - 2 near the track start
            downbeats.append(float(beat_time + (window_start + local_max - beat_frame) * 512 / sample_rate))

    return BeatGridInfo(
        bpm=float(tempo),
        beat_positions=list(beat_times),
        confidence=confidence,
        phase_offset=float(phase_offset),
        grid_consistency=grid_consistency,
        downbeats=downbeats,
    )


if __name__ == "__main__":
    from pprint import pprint

    print("Analyzing beatgrid:")
    beat_info = analyze_beatgrid(sys.argv[1])

    pprint(asdict(beat_info))
