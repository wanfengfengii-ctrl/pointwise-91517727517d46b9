from dataclasses import dataclass
from typing import TypeVar

from capture.origin import Origin


_State = TypeVar('_State')


@dataclass(frozen=True, slots=True)
class FrameReading:
    number: int
    origin: Origin
    value: int | None


def require_prior_anchor(state: _State | None) -> _State:
    if state is None:
        raise ValueError('delta frame requires an established anchor state')
    return state
