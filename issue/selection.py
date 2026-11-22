from collections.abc import Iterable

from capture.frames import SourceFrame
from issue.freeze import FrozenRevision


def validate_selection(
    numbers: Iterable[int], frame_count: int | None = None
) -> tuple[int, ...]:
    try:
        selection = tuple(numbers)
    except TypeError as exc:
        raise ValueError('frame selection must be iterable') from exc
    if not selection:
        raise ValueError('select at least one original frame')
    previous = 0
    for number in selection:
        if type(number) is not int or number <= 0:
            raise ValueError('selected frame numbers must be positive integers')
        if number <= previous:
            raise ValueError('selected frame numbers must be strictly increasing')
        if frame_count is not None and number > frame_count:
            raise ValueError(f'frame {number} is outside the revision')
        previous = number
    return selection


def pick_frames(frozen: FrozenRevision, numbers: Iterable[int]) -> tuple[SourceFrame, ...]:
    selection = validate_selection(numbers, len(frozen.frames))
    return tuple(frozen.frames[number - 1] for number in selection)
