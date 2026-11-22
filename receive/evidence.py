from collections.abc import Iterator
from dataclasses import dataclass

from issue.package import FixedPackage
from wave.codec import Delta, Missing, decode_frame, read_integer
from wave.predictor import PredictorState


@dataclass(frozen=True, slots=True)
class ReplayBasis:
    entry_states: tuple[tuple[int, PredictorState], ...]


def _required_starts(package: FixedPackage) -> Iterator[int]:
    previous = 0
    span_start = 0
    pending = False
    for entry in package.manifest.entries:
        if previous == 0 or entry.number != previous + 1:
            span_start = entry.number
            pending = True
        previous = entry.number
        if pending:
            frame = decode_frame(entry.raw)
            if isinstance(frame, Delta):
                yield span_start
            pending = isinstance(frame, Missing)


def validate_evidence(package: FixedPackage) -> ReplayBasis:
    records = package.raw_basis
    if not isinstance(records, list):
        raise ValueError('decode basis must be an array')
    entries = []
    for row in records:
        if not isinstance(row, dict) or row.keys() != {'start', 'value', 'difference'}:
            raise ValueError('decode basis requires start, value, and difference')
        start = row['start']
        if type(start) is not int or start <= 0:
            raise ValueError('decode basis start must be a positive original position')
        state = PredictorState(read_integer(row['value']), read_integer(row['difference']))
        entries.append((start, state))
    expected = tuple(_required_starts(package))
    actual = tuple(start for start, _ in entries)
    if actual != expected:
        raise ValueError(f'decode basis boundary mismatch: expected {expected}, received {actual}')
    return ReplayBasis(tuple(entries))
