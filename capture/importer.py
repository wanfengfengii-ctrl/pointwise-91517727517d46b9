import sqlite3
from collections.abc import Iterable
from uuid import uuid4

from capture.frames import SourceFrame, collect_frames
from capture.origin import require_text
from capture.revisions import Revision, advance_current, insert_revision, require_current_parent
from capture.store import source_transaction
from wave.track import decode_track


def record(
    connection: sqlite3.Connection,
    track: str,
    frames: Iterable[SourceFrame],
    *,
    parent: str | None = None,
) -> str:
    require_text(track, 'track')
    if parent is not None:
        require_text(parent, 'parent revision')
    snapshot = collect_frames(frames)
    decode_track(snapshot)
    revision = Revision(f'rev-{uuid4().hex}', track, parent, snapshot)
    with source_transaction(connection):
        require_current_parent(connection, track, parent)
        insert_revision(connection, revision)
        advance_current(connection, revision)
    return revision.revision_id
