import sqlite3
from dataclasses import dataclass

from capture.frames import SourceFrame
from capture.origin import Origin


@dataclass(frozen=True, slots=True)
class Revision:
    revision_id: str
    track: str
    parent_id: str | None
    frames: tuple[SourceFrame, ...]


def _current_id(connection: sqlite3.Connection, track: str) -> str | None:
    row = connection.execute(
        'SELECT revision_id FROM current_revisions WHERE track = ?', (track,)
    ).fetchone()
    return None if row is None else row[0]


def load_revision(connection: sqlite3.Connection, track: str, revision_id: str) -> Revision:
    row = connection.execute(
        'SELECT parent_id FROM revisions WHERE track = ? AND revision_id = ?',
        (track, revision_id),
    ).fetchone()
    if row is None:
        raise LookupError(f'unknown revision {revision_id!r} for track {track!r}')
    rows = connection.execute(
        '''SELECT number, raw, export, locator
           FROM source_frames WHERE revision_id = ? ORDER BY number''',
        (revision_id,),
    )
    frames = tuple(
        SourceFrame(number, raw, Origin(export, locator))
        for number, raw, export, locator in rows
    )
    return Revision(revision_id, track, row[0], frames)


def load_current(connection: sqlite3.Connection, track: str) -> Revision:
    revision_id = _current_id(connection, track)
    if revision_id is None:
        raise LookupError(f'no current revision for track {track!r}')
    return load_revision(connection, track, revision_id)


def require_current_parent(
    connection: sqlite3.Connection, track: str, parent_id: str | None
) -> None:
    if _current_id(connection, track) != parent_id:
        raise ValueError('parent must match the current revision of this track')


def insert_revision(connection: sqlite3.Connection, revision: Revision) -> None:
    connection.execute(
        'INSERT INTO revisions (revision_id, track, parent_id) VALUES (?, ?, ?)',
        (revision.revision_id, revision.track, revision.parent_id),
    )
    connection.executemany(
        '''INSERT INTO source_frames (revision_id, number, raw, export, locator)
           VALUES (?, ?, ?, ?, ?)''',
        (
            (revision.revision_id, frame.number, frame.raw, frame.origin.export, frame.origin.locator)
            for frame in revision.frames
        ),
    )


def advance_current(connection: sqlite3.Connection, revision: Revision) -> None:
    connection.execute(
        '''INSERT INTO current_revisions (track, revision_id) VALUES (?, ?)
           ON CONFLICT (track) DO UPDATE SET revision_id = excluded.revision_id''',
        (revision.track, revision.revision_id),
    )
