import sqlite3
from dataclasses import dataclass
from os import PathLike
from uuid import uuid4

from archive_db import create_tables, open_database, write_transaction
from receive.readings import IntakeReadings, decode_readings, encode_readings


@dataclass(frozen=True, slots=True)
class IntakeRecord:
    intake_id: str
    original: bytes
    readings: IntakeReadings


def open_offline(path: str | PathLike[str]) -> sqlite3.Connection:
    return open_database(path)


def initialize_intake(connection: sqlite3.Connection) -> None:
    create_tables(connection, (
        '''CREATE TABLE IF NOT EXISTS intakes (
               intake_id TEXT PRIMARY KEY NOT NULL,
               package BLOB NOT NULL,
               readings TEXT NOT NULL
           )''',
    ))


def store_intake(
    connection: sqlite3.Connection, raw: bytes, readings: IntakeReadings
) -> IntakeRecord:
    intake_id = f'intake-{uuid4().hex}'
    encoded = encode_readings(readings)
    with write_transaction(connection):
        connection.execute(
            'INSERT INTO intakes (intake_id, package, readings) VALUES (?, ?, ?)',
            (intake_id, raw, encoded),
        )
    return IntakeRecord(intake_id, raw, readings)


def load_intake(connection: sqlite3.Connection, intake_id: str) -> IntakeRecord:
    row = connection.execute(
        'SELECT package, readings FROM intakes WHERE intake_id = ?', (intake_id,)
    ).fetchone()
    if row is None:
        raise LookupError(f'unknown intake {intake_id!r}')
    return IntakeRecord(intake_id, row[0], decode_readings(row[1]))
