"""Whole-track replay for V2 review packages.

The V2 review basis lists every omitted original frame as a derived effect
(["A", value, difference], ["D", increment], or ["M"] with canonical decimal
integer text).  Intake checks that the basis and the selection tile the frozen
track 1..N without gaps or overlaps, then replays the assembled track under
the empty edit set.  Review edits replace a selected original anchor with a
new (reading, difference) anchor or mark it missing; all edits apply to the
frozen track at once, and any delta preceding the first remaining valid
anchor refuses the whole review.
"""
from dataclasses import dataclass

from issue.package import ReviewPackage
from receive.readings import IntakeReadings
from wave.codec import Anchor, Delta, Frame, Missing, decode_frame, read_integer
from wave.predictor import PredictorState, step_frame
from wave.quality import FrameReading


@dataclass(frozen=True, slots=True)
class ReviewSkeleton:
    frames: tuple[tuple[int, Frame], ...]


def _read_basis_frame(data: object) -> Frame:
    if not isinstance(data, list) or not data:
        raise ValueError('review basis frame must be a nonempty array')
    kind = data[0]
    if kind == 'A' and len(data) == 3:
        return Anchor(read_integer(data[1]), read_integer(data[2]))
    if kind == 'D' and len(data) == 2:
        return Delta(read_integer(data[1]))
    if kind == 'M' and len(data) == 1:
        return Missing()
    raise ValueError('invalid review basis anchor, delta, or missing frame')


def validate_review_basis(package: ReviewPackage) -> ReviewSkeleton:
    records = package.raw_basis
    if not isinstance(records, list):
        raise ValueError('review basis must be an array')
    omitted: dict[int, Frame] = {}
    for row in records:
        if not isinstance(row, dict) or row.keys() != {'number', 'frame'}:
            raise ValueError('review basis entry requires number and frame')
        number = row['number']
        if type(number) is not int or number <= 0:
            raise ValueError('review basis number must be a positive original position')
        if number in omitted:
            raise ValueError(f'review basis repeats original position {number}')
        omitted[number] = _read_basis_frame(row['frame'])
    selected = package.manifest.selection
    if set(selected) & omitted.keys():
        raise ValueError('review basis overlaps the selected positions')
    merged = sorted((*selected, *omitted))
    if merged != list(range(1, len(merged) + 1)):
        raise ValueError('review basis and selection do not tile the frozen track')
    decoded = {entry.number: decode_frame(entry.raw) for entry in package.manifest.entries}
    return ReviewSkeleton(tuple(
        (number, decoded[number] if number in decoded else omitted[number])
        for number in merged
    ))


def validate_review_edits(
    package: ReviewPackage, skeleton: ReviewSkeleton, edits: object
) -> dict[int, tuple[int, int] | None]:
    if not isinstance(edits, dict):
        raise ValueError('review edits must be a dictionary')
    frames = dict(skeleton.frames)
    selected = set(package.manifest.selection)
    validated: dict[int, tuple[int, int] | None] = {}
    for number, edit in edits.items():
        if type(number) is not int:
            raise ValueError('review edit positions must be integers')
        if number not in selected or not isinstance(frames[number], Anchor):
            raise ValueError(f'position {number} is not a selected original anchor')
        if edit is None:
            validated[number] = None
            continue
        if not isinstance(edit, tuple) or len(edit) != 2:
            raise ValueError('review edit must be None or a (reading, difference) tuple')
        reading, difference = edit
        if type(reading) is not int or type(difference) is not int:
            raise ValueError('review edit reading and difference must be integers')
        validated[number] = (reading, difference)
    return validated


def replay_review(
    package: ReviewPackage,
    skeleton: ReviewSkeleton,
    edits: dict[int, tuple[int, int] | None],
) -> IntakeReadings:
    origins = {entry.number: entry.origin for entry in package.manifest.entries}
    readings = []
    state: PredictorState | None = None
    for number, effect in skeleton.frames:
        if number in edits:
            edit = edits[number]
            frame: Frame = Missing() if edit is None else Anchor(edit[0], edit[1])
        else:
            frame = effect
        try:
            state, value = step_frame(state, frame)
        except ValueError as exc:
            raise ValueError(f'reviewed track fails at original frame {number}: {exc}') from exc
        origin = origins.get(number)
        if origin is not None:
            readings.append(FrameReading(number, origin, value))
    return IntakeReadings(package.package_id, package.track, package.revision_id, tuple(readings))
