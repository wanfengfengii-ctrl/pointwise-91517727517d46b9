import sqlite3

from issue.package import read_package, read_review_package
from receive.evidence import validate_evidence
from receive.register import IntakeRecord, store_intake
from receive.replay import replay
from receive.review import replay_review, validate_review_basis


def accept(connection: sqlite3.Connection, raw: bytes) -> IntakeRecord:
    package = read_package(raw)
    basis = validate_evidence(package)
    readings = replay(package, basis)
    return store_intake(connection, raw, readings)


def accept_review(connection: sqlite3.Connection, raw: bytes) -> IntakeRecord:
    package = read_review_package(raw)
    skeleton = validate_review_basis(package)
    readings = replay_review(package, skeleton, {})
    return store_intake(connection, raw, readings)
