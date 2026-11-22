import sqlite3

from issue.package import read_package
from receive.evidence import validate_evidence
from receive.register import IntakeRecord, store_intake
from receive.replay import replay


def accept(connection: sqlite3.Connection, raw: bytes) -> IntakeRecord:
    package = read_package(raw)
    basis = validate_evidence(package)
    readings = replay(package, basis)
    return store_intake(connection, raw, readings)
