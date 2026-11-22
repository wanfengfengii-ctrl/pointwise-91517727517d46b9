import json
import sqlite3

from capture.importer import record
from capture.origin import Origin
from issue.package import read_package
from issue.register import dispatch
from receive.intake import accept
from receive.register import initialize_intake, load_intake
from report.lookup import fetch
from report.metrics import Metrics
from report.publish import publish
from report.store import initialize_reports
from tests.support import ArchiveTests, bench_export, emit_case, fixture_bytes, seal_payload, source_frames
from wave.track import inspect


def values(readings):
    return [row.value for row in readings.frames]


class AuditTests(ArchiveTests):
    def test_sparse_offline(self):
        source = self.source()
        track, frames = bench_export()
        revision = record(source, track, frames)
        full = inspect(source, track, revision)
        selection = (1, 3, 5)
        raw, issued = dispatch(source, track, revision, selection)
        source.close()
        offline = self.offline()
        intake = accept(offline, raw)
        self.assertEqual(values(intake.readings), [10, 16, 8], 'WAVE_SPARSE_READING_MISMATCH')
        self.assertEqual(intake.readings.frames, tuple(full[number - 1] for number in selection))
        self.assertEqual(intake.readings.package_id, issued.package_id)
        self.assertEqual(intake.readings.revision_id, revision)
        self.assertEqual(intake.original, raw)
        finding, receipt = publish(offline, intake.intake_id)
        self.assertEqual(finding.readings, intake.readings)
        self.assertEqual(finding.metrics, Metrics(3, 16))
        self.assertEqual((receipt.finding_id, receipt.intake_id), (finding.finding_id, intake.intake_id))
        offline.close()
        reopened = self.offline()
        archived, archived_receipt = fetch(reopened, finding.finding_id)
        self.assertEqual((archived, archived_receipt), (finding, receipt))
        self.assertEqual(load_intake(reopened, intake.intake_id), intake)
        actual = {
            'selection': [row.number for row in intake.readings.frames],
            'values': values(intake.readings),
            'origins': [row.origin.as_dict() for row in intake.readings.frames],
        }
        expected = {
            'selection': [1, 3, 5], 'values': [10, 16, 8],
            'origins': [{'export': 'bench-07.run', 'locator': f'row/{number}'} for number in (1, 3, 5)],
        }
        downstream_expected = {'valid_count': 3, 'peak': 16, 'same_receipt': True}
        downstream_actual = {
            'valid_count': archived.metrics.valid_count, 'peak': archived.metrics.peak,
            'same_receipt': archived_receipt == receipt,
        }
        self.assertEqual(actual, expected)
        self.assertEqual(downstream_actual, downstream_expected)
        emit_case({
            'case_id': 't6',
            'input': {'selection': list(selection), 'raw': [row.raw.decode('ascii') for row in frames]},
            'expected': expected, 'actual': actual,
            'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
            'code_paths': ['issue/package.py', 'receive/intake.py', 'receive/evidence.py',
                           'receive/replay.py', 'report/publish.py', 'report/lookup.py'],
            'oracle': '沿全部五帧手算为 10、13、16、8、8，取原位 1、3、5 后求有效数和最大值。',
        })

    def test_independent_package(self):
        offline = self.offline()
        raw = fixture_bytes('night-handoff.json')
        intake = accept(offline, raw)
        self.assertEqual(values(intake.readings), [10, 16, 8], 'WAVE_INDEPENDENT_REPLAY_MISMATCH')
        self.assertEqual([row.number for row in intake.readings.frames], [1, 3, 5])
        self.assertEqual([row.origin for row in intake.readings.frames],
                         [Origin('bench-07.run', f'row/{number}') for number in (1, 3, 5)])
        self.assertEqual(intake.readings.revision_id, 'bench-revision-v1')
        self.assertEqual(load_intake(offline, intake.intake_id).original, raw)
        finding, _ = publish(offline, intake.intake_id)
        self.assertEqual(finding.metrics, Metrics(3, 16))
        self.assertFalse(self.source_path.exists())

    def test_selection_invariance(self):
        source = self.source()
        track, frames = bench_export()
        revision = record(source, track, frames)
        sparse, _ = dispatch(source, track, revision, (1, 3, 5))
        expanded, _ = dispatch(source, track, revision, (1, 3, 4, 5))
        source.close()
        offline = self.offline()
        first = accept(offline, sparse)
        second = accept(offline, expanded)
        self.assertEqual(values(second.readings), [10, 16, 8, 8])
        self.assertEqual(first.readings.frames,
                         tuple(row for row in second.readings.frames if row.number != 4))

    def test_leading_missing_span(self):
        source = self.source()
        frames = source_frames(b'["A",4,2]', b'["D",1]', b'["M"]', b'["D",0]')
        revision = record(source, 'rig', frames)
        raw, _ = dispatch(source, 'rig', revision, (3, 4))
        source.close()
        self.assertEqual(read_package(raw).raw_basis, [{'start': 3, 'value': '7', 'difference': '3'}])
        intake = accept(self.offline(), raw)
        self.assertEqual(values(intake.readings), [None, 10])
        self.assertEqual([row.number for row in intake.readings.frames], [3, 4])
        self.assertEqual([row.origin for row in intake.readings.frames], [frames[2].origin, frames[3].origin])

    def test_legacy_reopen(self):
        offline = self.offline()
        raw = fixture_bytes('legacy-handoff.json')
        self.assertNotIn('basis', json.loads(raw)['payload'])
        intake = accept(offline, raw)
        self.assertEqual(values(intake.readings), [-5, -6, None])
        self.assertEqual([row.number for row in intake.readings.frames], [6, 7, 10])
        self.assertEqual([row.origin for row in intake.readings.frames],
                         [Origin('bench-07.old', f'row/{number}') for number in (6, 7, 10)])
        archived = publish(offline, intake.intake_id)
        self.assertEqual(archived[0].metrics, Metrics(2, -5))
        offline.close()
        reopened = self.offline()
        initialize_intake(reopened)
        initialize_reports(reopened)
        self.assertEqual(load_intake(reopened, intake.intake_id), intake)
        self.assertEqual(load_intake(reopened, intake.intake_id).original, raw)
        self.assertEqual(fetch(reopened, archived[0].finding_id), archived)

    def test_missing_context(self):
        offline = self.offline()
        payload = json.loads(fixture_bytes('night-handoff.json'))['payload']
        del payload['basis']
        raw = seal_payload(payload)
        self.assertEqual(read_package(raw).manifest.selection, (1, 3, 5))
        with self.assertRaisesRegex(ValueError, 'basis boundary'):
            accept(offline, raw)
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))
        with self.assertRaises(LookupError):
            publish(offline, 'night-independent')
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_misbound_context(self):
        offline = self.offline()
        payload = json.loads(fixture_bytes('night-handoff.json'))['payload']
        payload['basis'][0]['start'] = 4
        raw = seal_payload(payload)
        self.assertEqual(read_package(raw).raw_basis[0]['start'], 4)
        with self.assertRaisesRegex(ValueError, 'basis boundary'):
            accept(offline, raw)
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_corrupt_envelope(self):
        offline = self.offline()
        envelope = json.loads(fixture_bytes('night-handoff.json'))
        envelope['payload']['frames'][0]['raw'] = 'WyJNIl0='
        with self.assertRaisesRegex(ValueError, 'checksum'):
            accept(offline, json.dumps(envelope).encode('utf-8'))
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_manifest_disagrees_with_selection(self):
        offline = self.offline()
        payload = json.loads(fixture_bytes('night-handoff.json'))['payload']
        payload['frames'][1]['number'] = 2
        with self.assertRaisesRegex(ValueError, 'manifest does not match'):
            accept(offline, seal_payload(payload))
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_rejects_incomplete_or_surplus_basis(self):
        offline = self.offline()
        for basis in (
            None,
            [{'start': 3, 'value': '13'}],
            [{'start': 3, 'value': '13', 'difference': '3'}],
            [{'start': 1, 'value': '10', 'difference': '2'},
             {'start': 3, 'value': '13', 'difference': '3'},
             {'start': 5, 'value': '8', 'difference': '0'}],
        ):
            with self.subTest(basis=basis):
                payload = json.loads(fixture_bytes('night-handoff.json'))['payload']
                payload['basis'] = basis
                with self.assertRaisesRegex(ValueError, 'basis'):
                    accept(offline, seal_payload(payload))
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_failed_publish(self):
        offline = self.offline()
        intake = accept(offline, fixture_bytes('night-handoff.json'))
        old = publish(offline, intake.intake_id)
        offline.execute('''CREATE TRIGGER reject_receipt BEFORE INSERT ON finding_receipts
                           BEGIN SELECT RAISE(ABORT, 'filing unavailable'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'filing unavailable'):
            publish(offline, intake.intake_id)
        offline.close()
        reopened = self.offline()
        self.assertEqual(self.audit_counts(reopened), (1, 1, 1))
        self.assertEqual(fetch(reopened, old[0].finding_id), old)

    def test_atomic_visibility(self):
        writer = self.offline()
        intake = accept(writer, fixture_bytes('legacy-handoff.json'))
        old = publish(writer, intake.intake_id)
        observer = self.offline()
        observed = []

        def observe_before_receipt():
            observed.append(self.audit_counts(observer))
            return 0

        writer.create_function('observe_before_receipt', 0, observe_before_receipt)
        writer.execute('''CREATE TRIGGER reject_after_candidate BEFORE INSERT ON finding_receipts
                          WHEN EXISTS (SELECT 1 FROM findings WHERE finding_id = NEW.finding_id)
                          BEGIN
                              SELECT observe_before_receipt();
                              SELECT RAISE(ABORT, 'candidate must roll back');
                          END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'candidate must roll back'):
            publish(writer, intake.intake_id)
        self.assertEqual(observed, [(1, 1, 1)])
        writer.close()
        observer.close()
        reopened = self.offline()
        self.assertEqual(self.audit_counts(reopened), (1, 1, 1))
        self.assertEqual(fetch(reopened, old[0].finding_id), old)

    def test_unknown_intake(self):
        offline = self.offline()
        with self.assertRaisesRegex(LookupError, 'unknown intake'):
            publish(offline, 'absent')
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_unknown_fetch(self):
        offline = self.offline()
        intake = accept(offline, fixture_bytes('legacy-handoff.json'))
        old = publish(offline, intake.intake_id)
        with self.assertRaisesRegex(LookupError, 'unknown finding'):
            fetch(offline, 'absent')
        self.assertEqual(fetch(offline, old[0].finding_id), old)
        self.assertEqual(self.audit_counts(offline), (1, 1, 1))

    def test_missing_peak(self):
        source = self.source()
        frames = source_frames(b'["A",4,2]', b'["M"]', b'["M"]', b'["D",0]')
        revision = record(source, 'rig', frames)
        raw, _ = dispatch(source, 'rig', revision, (2, 3))
        source.close()
        offline = self.offline()
        intake = accept(offline, raw)
        finding, _ = publish(offline, intake.intake_id)
        self.assertEqual(values(finding.readings), [None, None])
        self.assertEqual([row.number for row in finding.readings.frames], [2, 3])
        self.assertEqual([row.origin for row in finding.readings.frames], [frames[1].origin, frames[2].origin])
        self.assertEqual(finding.metrics, Metrics(0, None))

    def test_negative_and_zero(self):
        source = self.source()
        negative = record(source, 'negative', source_frames(b'["A",-5,-2]', b'["M"]', b'["D",1]'))
        zero = record(source, 'zero', source_frames(b'["A",0,1]', b'["M"]'))
        negative_raw, _ = dispatch(source, 'negative', negative, (1, 2, 3))
        zero_raw, _ = dispatch(source, 'zero', zero, (1, 2))
        source.close()
        offline = self.offline()
        for raw, expected_values, metrics in (
            (negative_raw, [-5, None, -6], Metrics(2, -5)),
            (zero_raw, [0, None], Metrics(1, 0)),
        ):
            with self.subTest(metrics=metrics):
                intake = accept(offline, raw)
                finding, _ = publish(offline, intake.intake_id)
                self.assertEqual(values(finding.readings), expected_values)
                self.assertEqual(finding.metrics, metrics)

    def test_large_integer_state_survives_storage(self):
        source = self.source()
        anchor = b'["A",' + b'9' * 4400 + b',1]'
        revision = record(source, 'wide', source_frames(anchor, b'["D",0]'))
        raw, _ = dispatch(source, 'wide', revision, (2,))
        source.close()
        offline = self.offline()
        intake = accept(offline, raw)
        finding, _ = publish(offline, intake.intake_id)
        offline.close()
        archived, _ = fetch(self.offline(), finding.finding_id)
        self.assertTrue(archived.metrics.peak == 10 ** 4400)
        self.assertTrue(archived.readings.frames[0].value == 10 ** 4400)
        self.assertEqual(archived.metrics.valid_count, 1)
