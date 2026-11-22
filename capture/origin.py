from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Origin:
    export: str
    locator: str

    def as_dict(self) -> dict[str, str]:
        return {'export': self.export, 'locator': self.locator}


def require_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or '\x00' in value:
        raise ValueError(f'{label} must be nonempty text without NUL')
    try:
        value.encode('utf-8')
    except UnicodeEncodeError as exc:
        raise ValueError(f'{label} must be UTF-8 text') from exc
    return value


def validate_origin(origin: object) -> Origin:
    if not isinstance(origin, Origin):
        raise ValueError('frame origin must be an Origin')
    require_text(origin.export, 'device export')
    require_text(origin.locator, 'device locator')
    return origin


def read_origin(data: object) -> Origin:
    if not isinstance(data, dict) or data.keys() != {'export', 'locator'}:
        raise ValueError('origin must contain export and locator')
    return validate_origin(Origin(data['export'], data['locator']))
