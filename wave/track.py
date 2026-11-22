import sqlite3
from collections.abc import Iterable

from capture.frames import SourceFrame
from capture.revisions import load_revision
from wave.codec import decode_frame
from wave.predictor import PredictorState, step_frame
from wave.quality import FrameReading


def decode_track(frames: Iterable[SourceFrame]) -> tuple[FrameReading, ...]:
    state: PredictorState | None = None
    readings = []
    for number, frame in enumerate(frames, 1):
        if frame.number != number:
            raise ValueError(f'expected original frame number {number}')
        try:
            state, value = step_frame(state, decode_frame(frame.raw))
        except ValueError as exc:
            raise ValueError(f'frame {number}: {exc}') from exc
        readings.append(FrameReading(number, frame.origin, value))
    return tuple(readings)


def inspect(
    connection: sqlite3.Connection, track: str, revision_id: str
) -> tuple[FrameReading, ...]:
    revision = load_revision(connection, track, revision_id)
    return decode_track(revision.frames)
