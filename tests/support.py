import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from capture.frames import SourceFrame
from capture.origin import Origin
from capture.store import initialize_capture, open_source
from handoff_demo import load_device_export
from issue.register import initialize_issue
from receive.register import initialize_intake, open_offline
from report.store import initialize_reports


FIXTURES = Path(__file__).resolve().parent.parent / 'fixtures'


def bench_export():
    return load_device_export(FIXTURES / 'bench-export.json')


def source_frames(*raw: bytes, export: str = 'device.run') -> tuple[SourceFrame, ...]:
    return tuple(
        SourceFrame(number, encoded, Origin(export, f'row/{number}'))
        for number, encoded in enumerate(raw, 1)
    )


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def seal_payload(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    archive = {'version': 1, 'payload': payload, 'sha256': hashlib.sha256(body.encode('ascii')).hexdigest()}
    return json.dumps(archive, ensure_ascii=True).encode('ascii')


def emit_case(evidence: dict[str, object]) -> None:
    print('POINTWISE_SCENARIO ' + json.dumps(evidence, ensure_ascii=False, sort_keys=True))


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory(prefix='wave-tests-')
        self.addCleanup(folder.cleanup)
        self.source_path = Path(folder.name) / 'source.sqlite'
        self.offline_path = Path(folder.name) / 'offline.sqlite'

    def source(self):
        connection = open_source(self.source_path)
        self.addCleanup(connection.close)
        initialize_capture(connection)
        initialize_issue(connection)
        return connection

    def offline(self):
        connection = open_offline(self.offline_path)
        self.addCleanup(connection.close)
        initialize_intake(connection)
        initialize_reports(connection)
        return connection

    def issue_counts(self, connection):
        return connection.execute('SELECT count(*), count(receipt_id) FROM issues').fetchone()

    def audit_counts(self, connection):
        return connection.execute(
            '''SELECT (SELECT count(*) FROM intakes),
                      (SELECT count(*) FROM findings),
                      (SELECT count(*) FROM finding_receipts)'''
        ).fetchone()
