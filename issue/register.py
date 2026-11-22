import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import uuid4

from archive_db import create_tables
from capture.store import source_transaction
from issue.freeze import freeze_revision
from issue.package import build_package, build_review_package


@dataclass(frozen=True, slots=True)
class IssueReceipt:
    receipt_id: str
    package_id: str
    track: str
    revision_id: str


def initialize_issue(connection: sqlite3.Connection) -> None:
    create_tables(connection, (
        '''CREATE TABLE IF NOT EXISTS issues (
               package_id TEXT PRIMARY KEY NOT NULL,
               receipt_id TEXT NOT NULL UNIQUE,
               track TEXT NOT NULL,
               revision_id TEXT NOT NULL,
               package BLOB NOT NULL,
               FOREIGN KEY (track, revision_id) REFERENCES revisions (track, revision_id)
           )''',
    ))


def dispatch(
    connection: sqlite3.Connection, track: str, revision_id: str, numbers: Iterable[int]
) -> tuple[bytes, IssueReceipt]:
    frozen = freeze_revision(connection, track, revision_id)
    package_id = f'pkg-{uuid4().hex}'
    raw = build_package(frozen, numbers, package_id)
    receipt = IssueReceipt(f'issued-{uuid4().hex}', package_id, frozen.track, frozen.revision_id)
    with source_transaction(connection):
        connection.execute(
            '''INSERT INTO issues (package_id, receipt_id, track, revision_id, package)
               VALUES (?, ?, ?, ?, ?)''',
            (package_id, receipt.receipt_id, receipt.track, receipt.revision_id, raw),
        )
    return raw, receipt


def copy(connection: sqlite3.Connection, package_id: str) -> tuple[bytes, IssueReceipt]:
    row = connection.execute(
        'SELECT package, receipt_id, track, revision_id FROM issues WHERE package_id = ?',
        (package_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f'unknown package {package_id!r}')
    raw, receipt_id, track, revision_id = row
    return raw, IssueReceipt(receipt_id, package_id, track, revision_id)


def dispatch_review(
    connection: sqlite3.Connection, track: str, revision_id: str, numbers: Iterable[int]
) -> tuple[bytes, IssueReceipt]:
    frozen = freeze_revision(connection, track, revision_id)
    package_id = f'pkg-{uuid4().hex}'
    raw = build_review_package(frozen, numbers, package_id)
    receipt = IssueReceipt(f'issued-{uuid4().hex}', package_id, frozen.track, frozen.revision_id)
    with source_transaction(connection):
        connection.execute(
            '''INSERT INTO issues (package_id, receipt_id, track, revision_id, package)
               VALUES (?, ?, ?, ?, ?)''',
            (package_id, receipt.receipt_id, receipt.track, receipt.revision_id, raw),
        )
    return raw, receipt
