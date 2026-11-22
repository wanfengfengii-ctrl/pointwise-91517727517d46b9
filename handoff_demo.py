import json
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from capture.frames import SourceFrame
from capture.importer import record
from capture.origin import Origin, read_origin, require_text
from capture.store import initialize_capture, open_source
from issue.register import copy, dispatch, initialize_issue
from receive.intake import accept
from receive.register import initialize_intake, open_offline
from report.lookup import fetch
from report.publish import publish
from report.store import initialize_reports
from wave.track import inspect


def load_device_export(path: Path) -> tuple[str, tuple[SourceFrame, ...]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, dict) or data.keys() != {'track', 'frames'}:
        raise ValueError('export requires a track and ordered frames')
    track = require_text(data['track'], 'track')
    if not isinstance(data['frames'], list):
        raise ValueError('export frames must be an array')
    frames = []
    for row in data['frames']:
        if not isinstance(row, dict) or row.keys() != {'number', 'raw', 'origin'}:
            raise ValueError('invalid device export row')
        if not isinstance(row['raw'], str):
            raise ValueError('device export raw frame must be text')
        frames.append(SourceFrame(row['number'], row['raw'].encode('utf-8'), read_origin(row['origin'])))
    return track, tuple(frames)


def main() -> None:
    fixture = Path(__file__).resolve().parent / 'fixtures' / 'bench-export.json'
    track, frames = load_device_export(fixture)
    selection = (1, 3, 5)
    with TemporaryDirectory(prefix='wave-handoff-') as folder:
        source_path = Path(folder) / 'source.sqlite'
        offline_path = Path(folder) / 'offline.sqlite'
        with closing(open_source(source_path)) as source:
            initialize_capture(source)
            initialize_issue(source)
            revision = record(source, track, frames)
            full = [row.value for row in inspect(source, track, revision)]
            corrected = replace(frames[0], raw=b'["A",11,2]', origin=Origin('bench-07.fix', 'row/1'))
            newer = record(source, track, (corrected, *frames[1:]), parent=revision)
            revised = [row.value for row in inspect(source, track, newer)]
            raw, issued = dispatch(source, track, revision, selection)
        with closing(open_source(source_path)) as source:
            copied, old_receipt = copy(source, issued.package_id)
            if (copied, old_receipt) != (raw, issued):
                raise RuntimeError('historical issue copy differs')
        with closing(open_offline(offline_path)) as offline:
            initialize_intake(offline)
            initialize_reports(offline)
            intake = accept(offline, copied)
            finding, receipt = publish(offline, intake.intake_id)
        with closing(open_offline(offline_path)) as offline:
            historical, historical_receipt = fetch(offline, finding.finding_id)

    observed = {
        'full': full,
        'corrected': revised,
        'selection': [row.number for row in intake.readings.frames],
        'values': [row.value for row in intake.readings.frames],
        'locators': [row.origin.locator for row in intake.readings.frames],
    }
    expected = {
        'full': [10, 13, 16, 8, 8],
        'corrected': [11, 14, 17, 8, 8],
        'selection': [1, 3, 5],
        'values': [10, 16, 8],
        'locators': ['row/1', 'row/3', 'row/5'],
    }
    downstream = {
        'valid_count': historical.metrics.valid_count,
        'peak': historical.metrics.peak,
        'revision_preserved': historical.readings.revision_id == revision,
        'history_preserved': (historical, historical_receipt) == (finding, receipt),
    }
    expected_downstream = {
        'valid_count': 3, 'peak': 16, 'revision_preserved': True, 'history_preserved': True,
    }
    if observed != expected or downstream != expected_downstream:
        raise RuntimeError(f'wave handoff demo discrepancy: {observed!r}, {downstream!r}')
    evidence = {
        'case_id': 't6',
        'input': {'raw': [frame.raw.decode('utf-8') for frame in frames], 'selection': list(selection)},
        'expected': expected,
        'actual': observed,
        'downstream_expected': expected_downstream,
        'downstream_actual': downstream,
        'code_paths': [
            'capture/importer.py', 'wave/track.py', 'issue/register.py', 'issue/package.py',
            'receive/intake.py', 'receive/evidence.py', 'receive/replay.py',
            'report/publish.py', 'report/lookup.py',
        ],
        'oracle': '手算两版整轨后取第 1、3、5 帧，按原序核对出处并比较重开领取的原报告和回执。',
    }
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    main()
