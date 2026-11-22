import sqlite3
from dataclasses import dataclass

from capture.frames import SourceFrame
from capture.revisions import load_revision


@dataclass(frozen=True, slots=True)
class FrozenRevision:
    track: str
    revision_id: str
    frames: tuple[SourceFrame, ...]


def freeze_revision(
    connection: sqlite3.Connection, track: str, revision_id: str
) -> FrozenRevision:
    revision = load_revision(connection, track, revision_id)
    return FrozenRevision(revision.track, revision.revision_id, revision.frames)
