import sqlite3
from uuid import uuid4

from issue.package import read_review_package
from receive.register import load_intake
from receive.review import replay_review, validate_review_basis, validate_review_edits
from report.metrics import summarize
from report.receipt import FindingReceipt, make_receipt
from report.store import Finding, ReviewFinding, store_finding, store_review_finding


def publish(connection: sqlite3.Connection, intake_id: str) -> tuple[Finding, FindingReceipt]:
    intake = load_intake(connection, intake_id)
    finding = Finding(
        f'finding-{uuid4().hex}', intake.intake_id, intake.readings, summarize(intake.readings)
    )
    receipt = make_receipt(finding.finding_id, finding.intake_id)
    store_finding(connection, finding, receipt)
    return finding, receipt


def publish_review(
    connection: sqlite3.Connection, intake_id: str, edits: dict[int, tuple[int, int] | None]
) -> tuple[ReviewFinding, FindingReceipt]:
    intake = load_intake(connection, intake_id)
    package = read_review_package(intake.original)
    skeleton = validate_review_basis(package)
    validated = validate_review_edits(package, skeleton, edits)
    readings = replay_review(package, skeleton, validated)
    finding = ReviewFinding(
        f'finding-{uuid4().hex}', intake.intake_id, validated, readings, summarize(readings)
    )
    receipt = make_receipt(finding.finding_id, finding.intake_id)
    store_review_finding(connection, finding, receipt)
    return finding, receipt
