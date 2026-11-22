import base64
import json
import sqlite3
from dataclasses import replace

from capture.importer import record
from issue.package import read_package, read_review_package
from issue.register import copy, dispatch, dispatch_review
from receive.intake import accept, accept_review
from receive.register import load_intake
from report.lookup import fetch, fetch_review
from report.metrics import Metrics
from report.publish import publish, publish_review
from tests.support import ArchiveTests, emit_case, seal_payload, source_frames


def values(readings):
    return [row.value for row in readings.frames]


class ReviewTests(ArchiveTests):
    def issue_review(self, source, raws, selection, track='rig'):
        revision = record(source, track, source_frames(*raws))
        raw, receipt = dispatch_review(source, track, revision, selection)
        return revision, raw, receipt

    def test_review_package_structure(self):
        source = self.source()
        revision, raw, receipt = self.issue_review(
            source,
            (b'["A",10,2]', b'["D",0]', b'["A",12,2]', b'["M"]', b'["D",-2]'),
            (1, 4),
        )
        self.assertEqual(json.loads(raw)['version'], 2)
        package = read_review_package(raw)
        self.assertEqual(package.manifest.selection, (1, 4))
        self.assertEqual(package.raw_basis, [
            {'number': 2, 'frame': ['D', '0']},
            {'number': 3, 'frame': ['A', '12', '2']},
            {'number': 5, 'frame': ['D', '-2']},
        ], 'REVIEW_BASIS_MUST_DERIVE_OMITTED_FRAMES')
        self.assertEqual((package.track, package.revision_id), ('rig', revision))
        self.assertEqual(package.package_id, receipt.package_id)
        with self.assertRaisesRegex(ValueError, 'version'):
            read_package(raw)
        self.assertEqual(self.issue_counts(source), (1, 1))
        source.close()
        self.assertEqual(copy(self.source(), receipt.package_id), (raw, receipt))

    def test_review_selection_rules(self):
        source = self.source()
        revision = record(source, 'rig', source_frames(b'["A",10,2]', b'["D",0]'))
        for selection in ((2, 1), (1, 3), (), (0,), (True,), ('1',), (1, 1)):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    dispatch_review(source, 'rig', revision, selection)
        with self.assertRaises(LookupError):
            dispatch_review(source, 'rig', 'unknown-revision', (1,))
        self.assertEqual(self.issue_counts(source), (0, 0))

    def test_failed_review_issue_registration(self):
        source = self.source()
        revision = record(source, 'rig', source_frames(b'["A",10,2]', b'["D",0]'))
        good = dispatch_review(source, 'rig', revision, (1,))
        source.execute('''CREATE TRIGGER reject_issue BEFORE INSERT ON issues
                          BEGIN SELECT RAISE(ABORT, 'issue storage rejected'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'issue storage rejected'):
            dispatch_review(source, 'rig', revision, (2,))
        source.close()
        reopened = self.source()
        self.assertEqual(self.issue_counts(reopened), (1, 1))
        self.assertEqual(copy(reopened, good[1].package_id), good)

    def test_review_package_frozen(self):
        source = self.source()
        frames = source_frames(b'["A",10,2]', b'["D",0]', b'["D",0]')
        first = record(source, 'rig', frames)
        raw, _ = dispatch_review(source, 'rig', first, (1, 3))
        changed = replace(frames[0], raw=b'["A",11,2]')
        record(source, 'rig', (changed, *frames[1:]), parent=first)
        source.close()
        intake = accept_review(self.offline(), raw)
        self.assertEqual(values(intake.readings), [10, 14])
        self.assertEqual(intake.readings.revision_id, first)

    def test_accept_review_after_source_cutoff(self):
        source = self.source()
        _, raw, receipt = self.issue_review(source, (b'["A",10,2]', b'["D",0]', b'["D",0]'), (1, 3))
        source.close()
        self.source_path.unlink()
        offline = self.offline()
        intake = accept_review(offline, raw)
        self.assertEqual(intake.original, raw)
        self.assertEqual(values(intake.readings), [10, 14])
        self.assertEqual([row.number for row in intake.readings.frames], [1, 3])
        self.assertEqual(intake.readings.package_id, receipt.package_id)
        self.assertEqual(load_intake(offline, intake.intake_id), intake)

    def test_accept_review_rejects_v1_and_corrupt(self):
        source = self.source()
        frames = source_frames(b'["A",10,2]', b'["D",0]')
        revision = record(source, 'rig', frames)
        v1_raw, _ = dispatch(source, 'rig', revision, (1, 2))
        v2_raw, _ = dispatch_review(source, 'rig', revision, (1, 2))
        source.close()
        offline = self.offline()
        with self.assertRaisesRegex(ValueError, 'version'):
            accept_review(offline, v1_raw)
        with self.assertRaisesRegex(ValueError, 'version'):
            accept(offline, v2_raw)
        changed = json.loads(v2_raw)
        changed['sha256'] = 'corrupt'
        with self.assertRaisesRegex(ValueError, 'checksum'):
            accept_review(offline, json.dumps(changed).encode('utf-8'))
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_accept_review_basis_binding(self):
        source = self.source()
        _, raw, _ = self.issue_review(source, (b'["A",10,2]', b'["D",1]', b'["D",0]'), (1, 3))
        source.close()
        offline = self.offline()
        entry = {'number': 2, 'frame': ['D', '1']}
        for basis in (
            None,
            'not-a-list',
            [],
            [{'number': 4, 'frame': ['M']}],
            [entry, entry],
            [{'number': 1, 'frame': ['M']}, entry],
            [{'number': 0, 'frame': ['M']}, entry],
            [{'number': True, 'frame': ['M']}, entry],
            [['number', 2]],
            [{'number': 2}],
            [{'number': 2, 'frame': ['X', '1']}],
            [{'number': 2, 'frame': ['D', '1.5']}],
            [{'number': 2, 'frame': ['D', '01']}],
            [{'number': 2, 'frame': ['A', '1']}],
        ):
            with self.subTest(basis=basis):
                payload = json.loads(raw)['payload']
                payload['basis'] = basis
                with self.assertRaises(ValueError):
                    accept_review(offline, seal_payload(payload, version=2))
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_accept_review_undecodable(self):
        offline = self.offline()
        payload = {
            'package_id': 'pkg-crafted',
            'track': 'rig',
            'revision_id': 'rev-crafted',
            'selection': [1],
            'frames': [{
                'number': 1,
                'raw': base64.b64encode(b'["M"]').decode('ascii'),
                'origin': {'export': 'rig.run', 'locator': 'row/1'},
            }],
            'basis': [{'number': 2, 'frame': ['D', '0']}],
        }
        with self.assertRaisesRegex(ValueError, 'anchor'):
            accept_review(offline, seal_payload(payload, version=2))
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_failed_review_intake(self):
        source = self.source()
        _, raw, _ = self.issue_review(source, (b'["A",10,2]', b'["D",0]'), (1, 2))
        source.close()
        offline = self.offline()
        offline.execute('''CREATE TRIGGER reject_intake BEFORE INSERT ON intakes
                           BEGIN SELECT RAISE(ABORT, 'intake storage rejected'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'intake storage rejected'):
            accept_review(offline, raw)
        self.assertEqual(self.audit_counts(offline), (0, 0, 0))

    def test_publish_review_examples(self):
        cases = (
            ((b'["A",10,2]', b'["D",0]', b'["D",0]'), (1, 3), (10, 14),
             (({1: (20, 3)}, (20, 26)),)),
            ((b'["A",10,2]', b'["A",12,2]', b'["D",0]'), (1, 3), (10, 14),
             (({1: (20, 3)}, (20, 14)),)),
            ((b'["A",10,2]', b'["D",0]', b'["A",12,2]', b'["D",0]'), (1, 4), (10, 14),
             (({1: None}, None),)),
            ((b'["A",10,2]', b'["M"]', b'["A",12,2]', b'["D",0]'), (1, 4), (10, 14),
             (({1: None}, (None, 14)),)),
            ((b'["A",10,2]', b'["D",0]'), (1,), (10,), (({1: None}, None),)),
            ((b'["A",10,2]', b'["M"]'), (1,), (10,), (({1: None}, (None,)),)),
            ((b'["A",8,2]', b'["D",1]', b'["A",-4,1]', b'["M"]', b'["D",-2]'), (1, 3, 5), (8, -4, -5),
             (({1: (0, -1), 3: None}, (0, None, -2)), ({1: None, 3: None}, None))),
        )
        source = self.source()
        issued = []
        for index, (raws, selection, original, reviews) in enumerate(cases):
            issued.append((original, reviews, self.issue_review(
                source, raws, selection, track=f'rig-{index}')[1:]))
        source.close()
        offline = self.offline()
        for (original, reviews, (raw, _)) in issued:
            intake = accept_review(offline, raw)
            self.assertEqual(values(intake.readings), list(original))
            for edits, expected in (({}, original), *reviews):
                with self.subTest(raw=raw, edits=edits):
                    if expected is None:
                        with self.assertRaises(ValueError):
                            publish_review(offline, intake.intake_id, edits)
                        continue
                    finding, receipt = publish_review(offline, intake.intake_id, edits)
                    self.assertEqual(finding.intake_id, intake.intake_id)
                    self.assertEqual(finding.edits, edits)
                    self.assertEqual(values(finding.readings), list(expected))
                    valid = [value for value in expected if value is not None]
                    self.assertEqual(finding.metrics, Metrics(len(valid), max(valid, default=None)))
                    self.assertEqual(
                        (receipt.finding_id, receipt.intake_id), (finding.finding_id, intake.intake_id))

    def test_publish_review_edit_validation(self):
        source = self.source()
        _, raw, _ = self.issue_review(source, (b'["A",10,2]', b'["D",0]', b'["D",0]'), (1, 3))
        source.close()
        offline = self.offline()
        intake = accept_review(offline, raw)
        bad_edits = (
            None, 'edits', [(1, (0, 0))],
            {True: (0, 0)}, {'1': (0, 0)},
            {2: (0, 0)}, {3: (0, 0)}, {4: (0, 0)},
            {1: (0, True)}, {1: (True, 0)}, {1: ('0', 0)},
            {1: [0, 0]}, {1: (0, 0, 0)}, {1: 0},
        )
        for edits in bad_edits:
            with self.subTest(edits=edits):
                with self.assertRaises(ValueError):
                    publish_review(offline, intake.intake_id, edits)
        self.assertEqual(self.review_counts(offline), (0, 0))

    def test_publish_review_rejects_v1_intake(self):
        source = self.source()
        frames = source_frames(b'["A",10,2]', b'["D",0]')
        revision = record(source, 'rig', frames)
        v1_raw, _ = dispatch(source, 'rig', revision, (1, 2))
        source.close()
        offline = self.offline()
        intake = accept(offline, v1_raw)
        with self.assertRaises(ValueError):
            publish_review(offline, intake.intake_id, {})
        self.assertEqual(self.review_counts(offline), (0, 0))

    def test_publish_review_unknown_intake(self):
        offline = self.offline()
        with self.assertRaisesRegex(LookupError, 'unknown intake'):
            publish_review(offline, 'absent', {})
        self.assertEqual(self.review_counts(offline), (0, 0))

    def test_review_metrics_zero_and_missing(self):
        source = self.source()
        _, raw, _ = self.issue_review(
            source, (b'["A",5,1]', b'["M"]', b'["A",-3,0]'), (1, 2, 3))
        source.close()
        offline = self.offline()
        intake = accept_review(offline, raw)
        zeroed, _ = publish_review(offline, intake.intake_id, {1: (0, 0), 3: None})
        self.assertEqual(values(zeroed.readings), [0, None, None])
        self.assertEqual(zeroed.metrics, Metrics(1, 0))
        missing, _ = publish_review(offline, intake.intake_id, {1: None, 3: None})
        self.assertEqual(values(missing.readings), [None, None, None])
        self.assertEqual(missing.metrics, Metrics(0, None))

    def test_review_large_integers(self):
        big = 10 ** 4400
        source = self.source()
        _, raw, _ = self.issue_review(source, (b'["A",1,0]', b'["D",0]'), (1, 2))
        source.close()
        offline = self.offline()
        intake = accept_review(offline, raw)
        finding, _ = publish_review(offline, intake.intake_id, {1: (big, 1)})
        self.assertEqual(values(finding.readings), [big, big + 1])
        offline.close()
        archived, _ = fetch_review(self.offline(), finding.finding_id)
        self.assertEqual(archived.edits, {1: (big, 1)})
        self.assertEqual(values(archived.readings), [big, big + 1])
        self.assertEqual(archived.metrics, Metrics(2, big + 1))

    def test_failed_review_publish_rollback(self):
        source = self.source()
        _, raw, _ = self.issue_review(source, (b'["A",10,2]', b'["D",0]'), (1, 2))
        source.close()
        offline = self.offline()
        intake = accept_review(offline, raw)
        old = publish_review(offline, intake.intake_id, {1: (20, 3)})
        offline.execute('''CREATE TRIGGER reject_review_receipt BEFORE INSERT ON review_finding_receipts
                           BEGIN SELECT RAISE(ABORT, 'filing unavailable'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'filing unavailable'):
            publish_review(offline, intake.intake_id, {1: (7, 7)})
        self.assertEqual(self.review_counts(offline), (1, 1))
        offline.close()
        reopened = self.offline()
        self.assertEqual(self.review_counts(reopened), (1, 1))
        self.assertEqual(fetch_review(reopened, old[0].finding_id), old)

    def test_fetch_review_reopen_and_isolation(self):
        source = self.source()
        frames = source_frames(b'["A",10,2]', b'["D",0]', b'["D",0]')
        revision = record(source, 'rig', frames)
        v1_raw, _ = dispatch(source, 'rig', revision, (1, 3))
        v2_raw, _ = dispatch_review(source, 'rig', revision, (1, 3))
        source.close()
        self.source_path.unlink()
        offline = self.offline()
        v1_finding, v1_receipt = publish(offline, accept(offline, v1_raw).intake_id)
        intake = accept_review(offline, v2_raw)
        finding, receipt = publish_review(offline, intake.intake_id, {1: (20, 3)})
        self.assertEqual(values(finding.readings), [20, 26])
        offline.close()
        reopened = self.offline()
        archived, archived_receipt = fetch_review(reopened, finding.finding_id)
        self.assertEqual(archived, finding)
        self.assertEqual(archived_receipt, receipt)
        self.assertEqual(fetch(reopened, v1_finding.finding_id), (v1_finding, v1_receipt))
        with self.assertRaisesRegex(LookupError, 'unknown review finding'):
            fetch_review(reopened, v1_finding.finding_id)
        with self.assertRaisesRegex(LookupError, 'unknown finding'):
            fetch(reopened, finding.finding_id)
        with self.assertRaises(LookupError):
            fetch_review(reopened, 'absent')
        self.assertEqual(self.audit_counts(reopened), (2, 1, 1))
        self.assertEqual(self.review_counts(reopened), (1, 1))
        actual = {
            'values': values(archived.readings),
            'origins': [row.origin.as_dict() for row in archived.readings.frames],
            'valid_count': archived.metrics.valid_count,
            'peak': archived.metrics.peak,
            'same_receipt': archived_receipt == receipt,
        }
        expected = {
            'values': [20, 26],
            'origins': [{'export': 'device.run', 'locator': f'row/{n}'} for n in (1, 3)],
            'valid_count': 2,
            'peak': 26,
            'same_receipt': True,
        }
        self.assertEqual(actual, expected)
        emit_case({
            'case_id': 't7',
            'input': {'raw': [frame.raw.decode('ascii') for frame in frames],
                      'selection': [1, 3], 'edits': {'1': [20, 3]}},
            'expected': expected,
            'actual': actual,
            'code_paths': ['issue/register.py', 'issue/package.py', 'receive/intake.py',
                           'receive/review.py', 'report/publish.py', 'report/store.py',
                           'report/lookup.py'],
            'oracle': '第 1 帧锚点改为 (20,3) 后整轨重解为 20、23、26，取第 1、3 帧并核对重开领取的定稿与回执。',
        })
