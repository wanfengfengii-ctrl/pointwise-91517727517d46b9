import sqlite3
from dataclasses import replace

from capture.importer import record
from capture.origin import Origin
from issue.package import read_package
from issue.register import copy, dispatch, initialize_issue
from tests.support import ArchiveTests, bench_export


class IssueTests(ArchiveTests):
    def test_sparse_manifest(self):
        source = self.source()
        track, frames = bench_export()
        revision = record(source, track, frames)
        raw, receipt = dispatch(source, track, revision, (1, 3, 5))
        package = read_package(raw)
        selected = (frames[0], frames[2], frames[4])
        self.assertEqual(package.manifest.selection, (1, 3, 5))
        self.assertEqual(
            [(row.number, row.raw, row.origin) for row in package.manifest.entries],
            [(row.number, row.raw, row.origin) for row in selected],
        )
        self.assertEqual((package.track, package.revision_id), (track, revision))
        self.assertEqual(package.package_id, receipt.package_id)
        self.assertEqual(self.issue_counts(source), (1, 1))
        source.close()
        self.assertEqual(copy(self.source(), receipt.package_id), (raw, receipt))

    def test_entry_basis(self):
        source = self.source()
        track, frames = bench_export()
        revision = record(source, track, frames)
        raw, _ = dispatch(source, track, revision, (1, 3, 5))
        package = read_package(raw)
        self.assertEqual(package.raw_basis, [
            {'start': 3, 'value': '13', 'difference': '3'},
            {'start': 5, 'value': '8', 'difference': '0'},
        ], 'WAVE_ISSUED_ENTRY_BASIS_MISMATCH')
        self.assertEqual(package.manifest.selection, (1, 3, 5))
        self.assertEqual([entry.raw for entry in package.manifest.entries],
                         [frames[index].raw for index in (0, 2, 4)])

    def test_frozen_revision(self):
        source = self.source()
        track, frames = bench_export()
        first = record(source, track, frames)
        old_raw, old_receipt = dispatch(source, track, first, (1, 3, 5))
        changed = replace(frames[0], raw=b'["A",11,2]', origin=Origin('bench.fix', 'row/1'))
        second = record(source, track, (changed, *frames[1:]), parent=first)
        initialize_issue(source)
        self.assertEqual(copy(source, old_receipt.package_id), (old_raw, old_receipt))
        old_again, old_again_receipt = dispatch(source, track, first, (1, 3, 5))
        new_raw, new_receipt = dispatch(source, track, second, (1, 3, 5))
        old_package = read_package(old_again)
        new_package = read_package(new_raw)
        self.assertEqual(old_again_receipt.revision_id, first)
        self.assertEqual(new_receipt.revision_id, second)
        self.assertEqual(old_package.revision_id, first)
        self.assertEqual(new_package.revision_id, second)
        self.assertEqual(old_package.manifest.entries[0].raw, frames[0].raw)
        self.assertEqual(old_package.manifest.entries[0].origin, frames[0].origin)
        self.assertEqual(new_package.manifest.entries[0].raw, changed.raw)
        self.assertEqual(new_package.manifest.entries[0].origin, changed.origin)

    def test_duplicate_selection(self):
        source = self.source()
        track, frames = bench_export()
        revision = record(source, track, frames)
        with self.assertRaisesRegex(ValueError, 'strictly increasing'):
            dispatch(source, track, revision, (1, 3, 3, 5))
        self.assertEqual(self.issue_counts(source), (0, 0))

    def test_selection_bounds(self):
        source = self.source()
        track, frames = bench_export()
        revision = record(source, track, frames)
        for selection in ((3, 1), (1, 6), (), (0,), (True,), ('1',)):
            with self.subTest(selection=selection):
                with self.assertRaises(ValueError):
                    dispatch(source, track, revision, selection)
        with self.assertRaises(LookupError):
            dispatch(source, track, 'unknown-revision', (1,))
        self.assertEqual(self.issue_counts(source), (0, 0))

    def test_unknown_copy(self):
        source = self.source()
        with self.assertRaisesRegex(LookupError, 'unknown package'):
            copy(source, 'unknown')
        self.assertEqual(self.issue_counts(source), (0, 0))

    def test_failed_issue_registration(self):
        source = self.source()
        track, frames = bench_export()
        revision = record(source, track, frames)
        good = dispatch(source, track, revision, (1,))
        source.execute('''CREATE TRIGGER reject_issue BEFORE INSERT ON issues
                          BEGIN SELECT RAISE(ABORT, 'issue storage rejected'); END''')
        with self.assertRaisesRegex(sqlite3.IntegrityError, 'issue storage rejected'):
            dispatch(source, track, revision, (3,))
        source.close()
        reopened = self.source()
        self.assertEqual(self.issue_counts(reopened), (1, 1))
        self.assertEqual(copy(reopened, good[1].package_id), good)
