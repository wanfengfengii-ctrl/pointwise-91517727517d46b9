import json
import sqlite3
from dataclasses import dataclass

from archive_db import create_tables, write_transaction
from receive.readings import IntakeReadings, encode_readings
from report.metrics import Metrics
from report.receipt import FindingReceipt
from wave.codec import integer_text, read_integer


@dataclass(frozen=True, slots=True)
class Finding:
    finding_id: str
    intake_id: str
    readings: IntakeReadings
    metrics: Metrics


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    finding_id: str
    intake_id: str
    edits: dict[int, tuple[int, int] | None]
    readings: IntakeReadings
    metrics: Metrics


def initialize_reports(connection: sqlite3.Connection) -> None:
    create_tables(connection, (
        '''CREATE TABLE IF NOT EXISTS findings (
               finding_id TEXT PRIMARY KEY NOT NULL,
               intake_id TEXT NOT NULL REFERENCES intakes (intake_id),
               readings TEXT NOT NULL,
               valid_count INTEGER NOT NULL CHECK (valid_count >= 0),
               peak TEXT,
               CHECK ((valid_count = 0) = (peak IS NULL)),
               UNIQUE (finding_id, intake_id)
           )''',
        '''CREATE TABLE IF NOT EXISTS finding_receipts (
               receipt_id TEXT PRIMARY KEY NOT NULL,
               finding_id TEXT NOT NULL UNIQUE,
               intake_id TEXT NOT NULL,
               FOREIGN KEY (finding_id, intake_id) REFERENCES findings (finding_id, intake_id)
           )''',
        '''CREATE TABLE IF NOT EXISTS review_findings (
               finding_id TEXT PRIMARY KEY NOT NULL,
               intake_id TEXT NOT NULL REFERENCES intakes (intake_id),
               edits TEXT NOT NULL,
               readings TEXT NOT NULL,
               valid_count INTEGER NOT NULL CHECK (valid_count >= 0),
               peak TEXT,
               CHECK ((valid_count = 0) = (peak IS NULL)),
               UNIQUE (finding_id, intake_id)
           )''',
        '''CREATE TABLE IF NOT EXISTS review_finding_receipts (
               receipt_id TEXT PRIMARY KEY NOT NULL,
               finding_id TEXT NOT NULL UNIQUE,
               intake_id TEXT NOT NULL,
               FOREIGN KEY (finding_id, intake_id)
                   REFERENCES review_findings (finding_id, intake_id)
           )''',
    ))


def store_finding(
    connection: sqlite3.Connection, finding: Finding, receipt: FindingReceipt
) -> None:
    if (receipt.finding_id, receipt.intake_id) != (finding.finding_id, finding.intake_id):
        raise ValueError('finding and receipt identities differ')
    peak = finding.metrics.peak
    peak_text = None if peak is None else integer_text(peak)
    encoded = encode_readings(finding.readings)
    with write_transaction(connection):
        connection.execute(
            '''INSERT INTO findings (finding_id, intake_id, readings, valid_count, peak)
               VALUES (?, ?, ?, ?, ?)''',
            (finding.finding_id, finding.intake_id, encoded, finding.metrics.valid_count, peak_text),
        )
        connection.execute(
            'INSERT INTO finding_receipts (receipt_id, finding_id, intake_id) VALUES (?, ?, ?)',
            (receipt.receipt_id, receipt.finding_id, receipt.intake_id),
        )


def encode_edits(edits: dict[int, tuple[int, int] | None]) -> str:
    rows = []
    for number, edit in sorted(edits.items()):
        if edit is None:
            rows.append([number, None])
        else:
            rows.append([number, integer_text(edit[0]), integer_text(edit[1])])
    return json.dumps(rows, ensure_ascii=True, sort_keys=True, separators=(',', ':'))


def decode_edits(encoded: str) -> dict[int, tuple[int, int] | None]:
    edits = {}
    for row in json.loads(encoded):
        edits[row[0]] = None if len(row) == 2 else (read_integer(row[1]), read_integer(row[2]))
    return edits


def store_review_finding(
    connection: sqlite3.Connection, finding: ReviewFinding, receipt: FindingReceipt
) -> None:
    if (receipt.finding_id, receipt.intake_id) != (finding.finding_id, finding.intake_id):
        raise ValueError('finding and receipt identities differ')
    peak = finding.metrics.peak
    peak_text = None if peak is None else integer_text(peak)
    with write_transaction(connection):
        connection.execute(
            '''INSERT INTO review_findings (finding_id, intake_id, edits, readings, valid_count, peak)
               VALUES (?, ?, ?, ?, ?, ?)''',
            (
                finding.finding_id, finding.intake_id, encode_edits(finding.edits),
                encode_readings(finding.readings), finding.metrics.valid_count, peak_text,
            ),
        )
        connection.execute(
            '''INSERT INTO review_finding_receipts (receipt_id, finding_id, intake_id)
               VALUES (?, ?, ?)''',
            (receipt.receipt_id, receipt.finding_id, receipt.intake_id),
        )
