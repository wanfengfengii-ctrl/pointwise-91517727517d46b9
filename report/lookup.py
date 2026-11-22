import sqlite3

from receive.readings import decode_readings
from report.metrics import Metrics
from report.receipt import FindingReceipt
from report.store import Finding, ReviewFinding, decode_edits
from wave.codec import read_integer


def fetch(connection: sqlite3.Connection, finding_id: str) -> tuple[Finding, FindingReceipt]:
    row = connection.execute(
        '''SELECT f.intake_id, f.readings, f.valid_count, f.peak, r.receipt_id, r.intake_id
           FROM findings AS f
           LEFT JOIN finding_receipts AS r ON r.finding_id = f.finding_id
           WHERE f.finding_id = ?''',
        (finding_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f'unknown finding {finding_id!r}')
    intake_id, readings, count, peak, receipt_id, receipt_intake = row
    if receipt_id is None or receipt_intake != intake_id:
        raise RuntimeError(f'incomplete archived finding {finding_id!r}')
    metrics = Metrics(count, None if peak is None else read_integer(peak))
    finding = Finding(finding_id, intake_id, decode_readings(readings), metrics)
    return finding, FindingReceipt(receipt_id, finding_id, receipt_intake)


def fetch_review(
    connection: sqlite3.Connection, finding_id: str
) -> tuple[ReviewFinding, FindingReceipt]:
    row = connection.execute(
        '''SELECT f.intake_id, f.edits, f.readings, f.valid_count, f.peak,
                  r.receipt_id, r.intake_id
           FROM review_findings AS f
           LEFT JOIN review_finding_receipts AS r ON r.finding_id = f.finding_id
           WHERE f.finding_id = ?''',
        (finding_id,),
    ).fetchone()
    if row is None:
        raise LookupError(f'unknown review finding {finding_id!r}')
    intake_id, edits, readings, count, peak, receipt_id, receipt_intake = row
    if receipt_id is None or receipt_intake != intake_id:
        raise RuntimeError(f'incomplete archived review finding {finding_id!r}')
    metrics = Metrics(count, None if peak is None else read_integer(peak))
    finding = ReviewFinding(
        finding_id, intake_id, decode_edits(edits), decode_readings(readings), metrics
    )
    return finding, FindingReceipt(receipt_id, finding_id, receipt_intake)
