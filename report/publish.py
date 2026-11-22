import sqlite3
from uuid import uuid4

from receive.register import load_intake
from report.metrics import summarize
from report.receipt import FindingReceipt, make_receipt
from report.store import Finding, store_finding


def publish(connection: sqlite3.Connection, intake_id: str) -> tuple[Finding, FindingReceipt]:
    intake = load_intake(connection, intake_id)
    finding = Finding(
        f'finding-{uuid4().hex}', intake.intake_id, intake.readings, summarize(intake.readings)
    )
    receipt = make_receipt(finding.finding_id, finding.intake_id)
    store_finding(connection, finding, receipt)
    return finding, receipt
