from dataclasses import dataclass

from receive.readings import IntakeReadings


@dataclass(frozen=True, slots=True)
class Metrics:
    valid_count: int
    peak: int | None


def summarize(readings: IntakeReadings) -> Metrics:
    valid_count = 0
    peak = None
    for frame in readings.frames:
        value = frame.value
        if value is not None:
            valid_count += 1
            if peak is None or value > peak:
                peak = value
    return Metrics(valid_count, peak)
