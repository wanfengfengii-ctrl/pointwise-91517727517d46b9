import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass

from capture.origin import require_text
from issue.freeze import FrozenRevision
from issue.manifest import Manifest, make_manifest, read_manifest
from issue.selection import pick_frames
from wave.codec import Delta, Missing, decode_frame, integer_text
from wave.predictor import PredictorState, step_frame
from wave.quality import require_prior_anchor


_PAYLOAD_FIELDS = {'package_id', 'track', 'revision_id', 'selection', 'frames'}


@dataclass(frozen=True, slots=True)
class FixedPackage:
    package_id: str
    track: str
    revision_id: str
    manifest: Manifest
    raw_basis: object


def _canonical(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(',', ':'), allow_nan=False
    ).encode('ascii')


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate package field {key!r}')
        result[key] = value
    return result


def _entry_basis(frozen: FrozenRevision, manifest: Manifest) -> list[dict[str, int | str]]:
    selected = set(manifest.selection)
    basis = []
    state: PredictorState | None = None
    span_entry: PredictorState | None = None
    previous_selected = 0
    span_start = 0
    first_measurable_pending = False
    for source in frozen.frames:
        frame = decode_frame(source.raw)
        if source.number in selected:
            if previous_selected == 0 or source.number != previous_selected + 1:
                span_start = source.number
                span_entry = state
                first_measurable_pending = True
            if first_measurable_pending and not isinstance(frame, Missing):
                if isinstance(frame, Delta):
                    prior = require_prior_anchor(span_entry)
                    basis.append({
                        'start': span_start,
                        'value': integer_text(prior.value),
                        'difference': integer_text(prior.difference),
                    })
                first_measurable_pending = False
            previous_selected = source.number
        state, _ = step_frame(state, frame)
    return basis


def build_package(frozen: FrozenRevision, numbers: Iterable[int], package_id: str) -> bytes:
    require_text(package_id, 'package ID')
    manifest = make_manifest(pick_frames(frozen, numbers))
    payload = {
        'package_id': package_id,
        'track': frozen.track,
        'revision_id': frozen.revision_id,
        'selection': list(manifest.selection),
        'frames': [entry.as_dict() for entry in manifest.entries],
        'basis': _entry_basis(frozen, manifest),
    }
    return _canonical({
        'version': 1,
        'payload': payload,
        'sha256': hashlib.sha256(_canonical(payload)).hexdigest(),
    })


def read_package(raw: bytes) -> FixedPackage:
    if not isinstance(raw, bytes):
        raise ValueError('package must be original bytes')
    try:
        envelope = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object)
    except (ValueError, RecursionError) as exc:
        raise ValueError('invalid package JSON') from exc
    if not isinstance(envelope, dict) or envelope.keys() != {'version', 'payload', 'sha256'}:
        raise ValueError('invalid package envelope')
    version = envelope['version']
    if type(version) is not int or version != 1:
        raise ValueError('unsupported package version')
    payload = envelope['payload']
    if not isinstance(payload, dict) or payload.keys() not in (
        _PAYLOAD_FIELDS, _PAYLOAD_FIELDS | {'basis'}
    ):
        raise ValueError('invalid package payload fields')
    try:
        digest = hashlib.sha256(_canonical(payload)).hexdigest()
    except (ValueError, RecursionError) as exc:
        raise ValueError('noncanonical package payload') from exc
    if envelope['sha256'] != digest:
        raise ValueError('package checksum mismatch')
    return FixedPackage(
        require_text(payload['package_id'], 'package ID'),
        require_text(payload['track'], 'track'),
        require_text(payload['revision_id'], 'revision ID'),
        read_manifest(payload['selection'], payload['frames']),
        payload.get('basis', []),
    )
