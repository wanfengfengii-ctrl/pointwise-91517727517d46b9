from issue.package import FixedPackage
from receive.evidence import ReplayBasis
from receive.readings import IntakeReadings
from wave.codec import decode_frame
from wave.predictor import PredictorState, step_frame
from wave.quality import FrameReading


def replay(package: FixedPackage, basis: ReplayBasis) -> IntakeReadings:
    starts = dict(basis.entry_states)
    readings = []
    previous = 0
    state: PredictorState | None = None
    for entry in package.manifest.entries:
        if previous == 0 or entry.number != previous + 1:
            state = starts.get(entry.number)
        try:
            state, value = step_frame(state, decode_frame(entry.raw))
        except ValueError as exc:
            raise ValueError(f'cannot replay original frame {entry.number}: {exc}') from exc
        readings.append(FrameReading(entry.number, entry.origin, value))
        previous = entry.number
    return IntakeReadings(package.package_id, package.track, package.revision_id, tuple(readings))
