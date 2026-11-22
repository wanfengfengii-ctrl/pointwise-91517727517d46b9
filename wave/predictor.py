from dataclasses import dataclass

from wave.codec import Anchor, Delta, Frame, Missing
from wave.quality import require_prior_anchor


@dataclass(frozen=True, slots=True)
class PredictorState:
    value: int
    difference: int


def step_frame(
    prior: PredictorState | None, frame: Frame
) -> tuple[PredictorState | None, int | None]:
    if isinstance(frame, Missing):
        return prior, None
    if isinstance(frame, Anchor):
        return PredictorState(frame.value, frame.difference), frame.value
    if isinstance(frame, Delta):
        state = require_prior_anchor(prior)
        difference = state.difference + frame.increment
        value = state.value + difference
        return PredictorState(value, difference), value
    raise ValueError('unknown decoded frame kind')
