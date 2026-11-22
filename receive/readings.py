import json
from dataclasses import dataclass

from capture.origin import read_origin
from wave.codec import integer_text, read_integer
from wave.quality import FrameReading


@dataclass(frozen=True, slots=True)
class IntakeReadings:
    package_id: str
    track: str
    revision_id: str
    frames: tuple[FrameReading, ...]


def encode_readings(readings: IntakeReadings) -> str:
    return json.dumps({
        'package_id': readings.package_id,
        'track': readings.track,
        'revision_id': readings.revision_id,
        'frames': [
            {
                'number': row.number,
                'origin': row.origin.as_dict(),
                'value': None if row.value is None else integer_text(row.value),
            }
            for row in readings.frames
        ],
    }, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def decode_readings(encoded: str) -> IntakeReadings:
    data = json.loads(encoded)
    frames = tuple(
        FrameReading(
            row['number'], read_origin(row['origin']),
            None if row['value'] is None else read_integer(row['value']),
        )
        for row in data['frames']
    )
    return IntakeReadings(data['package_id'], data['track'], data['revision_id'], frames)
