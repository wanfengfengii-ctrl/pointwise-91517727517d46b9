import base64
import binascii
from collections.abc import Iterable
from dataclasses import dataclass

from capture.frames import SourceFrame
from capture.origin import Origin, read_origin
from issue.selection import validate_selection


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    number: int
    raw: bytes
    origin: Origin

    def as_dict(self) -> dict[str, object]:
        return {
            'number': self.number,
            'raw': base64.b64encode(self.raw).decode('ascii'),
            'origin': self.origin.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class Manifest:
    entries: tuple[ManifestEntry, ...]

    @property
    def selection(self) -> tuple[int, ...]:
        return tuple(entry.number for entry in self.entries)


def make_manifest(frames: Iterable[SourceFrame]) -> Manifest:
    return Manifest(tuple(ManifestEntry(frame.number, frame.raw, frame.origin) for frame in frames))


def read_manifest(selection: object, rows: object) -> Manifest:
    if not isinstance(selection, list) or not isinstance(rows, list):
        raise ValueError('selection and frame manifest must be arrays')
    numbers = validate_selection(selection)
    if len(numbers) != len(rows):
        raise ValueError('selection and frame manifest length differ')
    entries = []
    for number, row in zip(numbers, rows, strict=True):
        if not isinstance(row, dict) or row.keys() != {'number', 'raw', 'origin'}:
            raise ValueError('invalid frame manifest entry')
        if type(row['number']) is not int or row['number'] != number:
            raise ValueError(f'frame manifest does not match selected position {number}')
        if not isinstance(row['raw'], str):
            raise ValueError(f'frame {number} raw encoding must be base64 text')
        try:
            raw = base64.b64decode(row['raw'], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError(f'frame {number} has invalid base64') from exc
        if not raw:
            raise ValueError(f'frame {number} has no original bytes')
        entries.append(ManifestEntry(number, raw, read_origin(row['origin'])))
    return Manifest(tuple(entries))
