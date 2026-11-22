import sqlite3
from os import PathLike

from archive_db import create_tables, open_database, write_transaction


source_transaction = write_transaction


def open_source(path: str | PathLike[str]) -> sqlite3.Connection:
    return open_database(path)


def initialize_capture(connection: sqlite3.Connection) -> None:
    create_tables(connection, (
        '''CREATE TABLE IF NOT EXISTS revisions (
               revision_id TEXT PRIMARY KEY NOT NULL,
               track TEXT NOT NULL,
               parent_id TEXT,
               UNIQUE (track, revision_id),
               FOREIGN KEY (track, parent_id) REFERENCES revisions (track, revision_id)
           )''',
        '''CREATE TABLE IF NOT EXISTS source_frames (
               revision_id TEXT NOT NULL REFERENCES revisions (revision_id),
               number INTEGER NOT NULL CHECK (number > 0),
               raw BLOB NOT NULL CHECK (length(raw) > 0),
               export TEXT NOT NULL,
               locator TEXT NOT NULL,
               PRIMARY KEY (revision_id, number)
           )''',
        '''CREATE TABLE IF NOT EXISTS current_revisions (
               track TEXT PRIMARY KEY NOT NULL,
               revision_id TEXT NOT NULL,
               FOREIGN KEY (track, revision_id) REFERENCES revisions (track, revision_id)
           )''',
    ))
