from collections.abc import Iterable
from dataclasses import dataclass

from capture.origin import Origin, validate_origin


@dataclass(frozen=True, slots=True)
class SourceFrame:
    number: int
    raw: bytes
    origin: Origin


def collect_frames(frames: Iterable[SourceFrame]) -> tuple[SourceFrame, ...]:
    collected = []
    for number, frame in enumerate(frames, 1):
        if not isinstance(frame, SourceFrame):
            raise ValueError(f'position {number} must contain a SourceFrame')
        if type(frame.number) is not int or frame.number != number:
            raise ValueError(f'expected original frame number {number}')
        if not isinstance(frame.raw, bytes) or not frame.raw:
            raise ValueError(f'frame {number} must contain original bytes')
        validate_origin(frame.origin)
        collected.append(frame)
    if not collected:
        raise ValueError('a revision must have at least one frame')
    return tuple(collected)
