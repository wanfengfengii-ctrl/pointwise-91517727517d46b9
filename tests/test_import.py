from dataclasses import replace

from capture.importer import record
from capture.origin import Origin
from capture.revisions import load_current, load_revision
from capture.store import initialize_capture
from tests.support import ArchiveTests, bench_export, emit_case, source_frames
from wave.codec import decode_frame
from wave.predictor import PredictorState, step_frame
from wave.track import inspect


class ImportTests(ArchiveTests):
    def test_anchor_and_delta(self):
        source = self.source()
        frames = source_frames(b'["A",10,2]', b'["D",1]')
        revision = record(source, 'rig', frames)
        readings = inspect(source, 'rig', revision)
        state, _ = step_frame(None, decode_frame(frames[0].raw))
        state, _ = step_frame(state, decode_frame(frames[1].raw))
        actual = {'values': [row.value for row in readings], 'difference': state.difference}
        expected = {'values': [10, 13], 'difference': 3}
        self.assertEqual(actual, expected)
        stored = load_current(source, 'rig')
        downstream = {'current': stored.revision_id == revision, 'originals_preserved': stored.frames == frames}
        downstream_expected = {'current': True, 'originals_preserved': True}
        self.assertEqual(downstream, downstream_expected)
        emit_case({
            'case_id': 't1',
            'input': [frame.raw.decode('ascii') for frame in frames],
            'expected': expected, 'actual': actual,
            'downstream_expected': downstream_expected, 'downstream_actual': downstream,
            'code_paths': ['capture/importer.py', 'capture/revisions.py', 'wave/track.py', 'wave/predictor.py'],
            'oracle': '锚点读 10，原差分 2 加 1 得 3，再加到 10 得 13。',
        })

    def test_signed_missing(self):
        source = self.source()
        frames = source_frames(b'["A",-5,-2]', b'["M"]', b'["D",1]', b'["D",-2]')
        revision = record(source, 'signed', frames)
        rows = inspect(source, 'signed', revision)
        self.assertEqual([row.value for row in rows], [-5, None, -6, -9])
        self.assertEqual(tuple(row.origin for row in rows), tuple(frame.origin for frame in frames))
        state = None
        for frame in frames:
            state, _ = step_frame(state, decode_frame(frame.raw))
        self.assertEqual(state, PredictorState(-9, -3))

    def test_missing_anchor(self):
        source = self.source()
        original = source_frames(b'["A",10,2]', b'["D",1]')
        revision = record(source, 'rig', original)
        with self.assertRaisesRegex(ValueError, 'established anchor'):
            record(source, 'rig', source_frames(b'["D",1]'), parent=revision)
        self.assertEqual(load_current(source, 'rig').revision_id, revision)
        self.assertEqual(load_revision(source, 'rig', revision).frames, original)
        self.assertEqual([row.value for row in inspect(source, 'rig', revision)], [10, 13])
        self.assertEqual(source.execute('SELECT count(*) FROM revisions').fetchone(), (1,))

    def test_leading_missing(self):
        source = self.source()
        good = source_frames(b'["M"]', b'["A",4,2]', b'["D",1]')
        revision = record(source, 'rig', good)
        self.assertEqual([row.value for row in inspect(source, 'rig', revision)], [None, 4, 7])
        with self.assertRaisesRegex(ValueError, 'frame 2'):
            record(source, 'rig', source_frames(b'["M"]', b'["D",1]'), parent=revision)
        self.assertEqual(load_current(source, 'rig').frames, good)
        self.assertEqual(source.execute('SELECT count(*) FROM revisions').fetchone(), (1,))

    def test_revision_isolation(self):
        source = self.source()
        track, frames = bench_export()
        first = record(source, track, frames)
        changed = replace(frames[0], raw=b'["A",11,2]', origin=Origin('corr.run', 'row/1'))
        second = record(source, track, (changed, *frames[1:]), parent=first)
        old = inspect(source, track, first)
        new = inspect(source, track, second)
        self.assertEqual([row.value for row in old], [10, 13, 16, 8, 8])
        self.assertEqual([row.value for row in new], [11, 14, 17, 8, 8])
        self.assertEqual(old[0].origin, Origin('bench-07.run', 'row/1'))
        self.assertEqual(new[0].origin, Origin('corr.run', 'row/1'))
        self.assertEqual(load_revision(source, track, first).frames, frames)
        self.assertEqual(load_current(source, track).parent_id, first)
        self.assertEqual(load_current(source, track).revision_id, second)

    def test_parent_mismatch(self):
        source = self.source()
        frames = source_frames(b'["A",1,0]')
        first = record(source, 'east', frames)
        second = record(source, 'east', source_frames(b'["A",2,0]'), parent=first)
        other = record(source, 'west', source_frames(b'["A",3,0]'))
        for parent in (first, other, None):
            with self.subTest(parent=parent):
                with self.assertRaisesRegex(ValueError, 'current revision'):
                    record(source, 'east', frames, parent=parent)
        with self.assertRaises(LookupError):
            inspect(source, 'east', other)
        self.assertEqual(load_current(source, 'east').revision_id, second)
        self.assertEqual(load_current(source, 'west').revision_id, other)
        self.assertEqual(source.execute('SELECT count(*) FROM revisions').fetchone(), (3,))

    def test_reopen_init(self):
        source = self.source()
        original = source_frames(b'["A",1,0]')
        correction = source_frames(b'["A",2,0]', export='later')
        first = record(source, 'rig', original)
        second = record(source, 'rig', correction, parent=first)
        source.close()
        reopened = self.source()
        initialize_capture(reopened)
        self.assertEqual(load_revision(reopened, 'rig', first).frames, original)
        self.assertEqual(load_revision(reopened, 'rig', second).frames, correction)
        self.assertEqual(load_current(reopened, 'rig').revision_id, second)
        self.assertEqual([row.value for row in inspect(reopened, 'rig', first)], [1])
        self.assertEqual([row.value for row in inspect(reopened, 'rig', second)], [2])

    def test_invalid_originals_leave_no_revision(self):
        source = self.source()
        base = source_frames(b'["A",1,0]')[0]
        invalid = (
            (), (replace(base, number=2),), (replace(base, number=True),),
            (replace(base, origin=Origin('test', ' ')),),
            (replace(base, raw=b'["A",true,0]'),),
            (replace(base, raw=b'["A",1,2.5]'),),
            (base, *source_frames(b'["M",0]')),
            (base, replace(base, number=2, raw=b'["M",0]')),
        )
        for frames in invalid:
            with self.subTest(frames=frames):
                with self.assertRaises(ValueError):
                    record(source, 'rig', frames)
        self.assertEqual(source.execute('SELECT count(*) FROM revisions').fetchone(), (0,))
        self.assertEqual(source.execute('SELECT count(*) FROM source_frames').fetchone(), (0,))
        with self.assertRaises(LookupError):
            load_current(source, 'rig')
