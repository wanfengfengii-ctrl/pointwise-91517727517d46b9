import json
import re
from dataclasses import dataclass
from decimal import Decimal


_DECIMAL_INTEGER = re.compile(r'(?:0|-?[1-9][0-9]*)', re.ASCII)


@dataclass(frozen=True, slots=True)
class Anchor:
    value: int
    difference: int


@dataclass(frozen=True, slots=True)
class Delta:
    increment: int


@dataclass(frozen=True, slots=True)
class Missing:
    pass


Frame = Anchor | Delta | Missing


def integer_text(value: int) -> str:
    if type(value) is not int:
        raise ValueError('expected an integer')
    return format(Decimal(value), 'f')


def read_integer(text: object) -> int:
    if not isinstance(text, str) or _DECIMAL_INTEGER.fullmatch(text) is None:
        raise ValueError('expected canonical decimal integer text')
    return int(Decimal(text))


def _json_integer(text: str) -> int:
    return int(Decimal(text))


def decode_frame(raw: bytes) -> Frame:
    if not isinstance(raw, bytes):
        raise ValueError('original frame must be bytes')
    try:
        fields = json.loads(raw.decode('utf-8'), parse_int=_json_integer)
    except (ValueError, RecursionError) as exc:
        raise ValueError('invalid original frame encoding') from exc
    if not isinstance(fields, list) or not fields:
        raise ValueError('original frame must be a nonempty array')
    kind = fields[0]
    if kind == 'A' and len(fields) == 3 and all(type(item) is int for item in fields[1:]):
        return Anchor(fields[1], fields[2])
    if kind == 'D' and len(fields) == 2 and type(fields[1]) is int:
        return Delta(fields[1])
    if kind == 'M' and len(fields) == 1:
        return Missing()
    raise ValueError('invalid anchor, delta, or missing frame fields')
