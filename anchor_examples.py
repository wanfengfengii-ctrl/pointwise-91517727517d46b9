import argparse
import json
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory

from capture.frames import SourceFrame
from capture.importer import record
from capture.origin import Origin
from capture.store import initialize_capture, open_source
from issue.register import copy, dispatch, initialize_issue
from receive.intake import accept
from receive.register import initialize_intake, open_offline
from report.metrics import Metrics
from report.store import initialize_reports


@dataclass(frozen=True)
class Case:
    name: str
    raw: tuple[bytes, ...]
    selection: tuple[int, ...]
    original: tuple[int | None, ...]
    reviews: tuple[tuple[dict[int, tuple[int, int] | None], tuple[int | None, ...] | None], ...]


CASES = (
    Case("carry", (b"[\"A\", 10, 2]", b"[\"D\",0]", b"[\"D\",0]"),
         (1, 3), (10, 14), (({1: (20, 3)}, (20, 26)),)),
    Case("reset", (b"[\"A\", 10, 2]", b"[\"A\",12,2]", b"[\"D\",0]"),
         (1, 3), (10, 14), (({1: (20, 3)}, (20, 14)),)),
    Case("hidden-delta", (b"[\"A\",10,2]", b"[\"D\",0]", b"[\"A\",12,2]", b"[\"D\",0]"),
         (1, 4), (10, 14), (({1: None}, None),)),
    Case("hidden-missing", (b"[\"A\",10,2]", b"[\"M\"]", b"[\"A\",12,2]", b"[\"D\",0]"),
         (1, 4), (10, 14), (({1: None}, (None, 14)),)),
    Case("tail-delta", (b"[\"A\",10,2]", b"[\"D\",0]"),
         (1,), (10,), (({1: None}, None),)),
    Case("tail-missing", (b"[\"A\",10,2]", b"[\"M\"]"),
         (1,), (10,), (({1: None}, (None,)),)),
    Case("two-anchors", (b"[\"A\",8,2]", b"[\"D\",1]", b"[\"A\",-4,1]", b"[\"M\"]", b"[\"D\",-2]"),
         (1, 3, 5), (8, -4, -5), (({1: (0, -1), 3: None}, (0, None, -2)), ({1: None, 3: None}, None))),
)


def origin(case, number):
    return Origin(f"{case.name}.run", f"frame/{number}")


def prepare(source, issuer):
    initialize_capture(source)
    initialize_issue(source)
    issued = []
    for case in CASES:
        frames = tuple(SourceFrame(n, raw, origin(case, n)) for n, raw in enumerate(case.raw, 1))
        revision = record(source, case.name, frames)
        issued.append((case, issuer(source, case.name, revision, case.selection)))
    return issued


def require_equal(actual, expected):
    if actual != expected:
        raise AssertionError(f"expected {expected!r}, got {actual!r}")


def require_refused(call, *args):
    try:
        call(*args)
    except ValueError:
        return
    raise AssertionError(f"{call.__name__} should reject the example")


def require_readings(readings, case, receipt, expected):
    require_equal((readings.package_id, readings.track, readings.revision_id),
                  (receipt.package_id, case.name, receipt.revision_id))
    require_equal(tuple((row.number, row.origin, row.value) for row in readings.frames),
                  tuple((n, origin(case, n), value) for n, value in zip(case.selection, expected, strict=True)))


def v1_examples():
    with closing(open_source(":memory:")) as source:
        batches = prepare(source, dispatch)
    with closing(open_offline(":memory:")) as offline:
        initialize_intake(offline)
        for case, (raw, receipt) in batches:
            intake = accept(offline, raw)
            require_readings(intake.readings, case, receipt, case.original)
            print(json.dumps({"case": case.name, "v1": [row.value for row in intake.readings.frames]}))


def review_examples():
    from issue.register import dispatch_review
    from receive.intake import accept_review
    from report.lookup import fetch_review
    from report.publish import publish_review

    with TemporaryDirectory(prefix="anchor-review-") as path:
        source_path = Path(path) / "source.sqlite"
        review_path = Path(path) / "review.sqlite"
        with closing(open_source(source_path)) as source:
            batches = prepare(source, dispatch_review)
        with closing(open_source(source_path)) as source:
            for _, (raw, receipt) in batches:
                require_equal(copy(source, receipt.package_id), (raw, receipt))
        source_path.unlink()

        archived = []
        with closing(open_offline(review_path)) as offline:
            initialize_intake(offline)
            initialize_reports(offline)
            for case, (raw, issued) in batches:
                if case.name == "carry":
                    changed = json.loads(raw)
                    changed["sha256"] = "corrupt"
                    require_refused(accept_review, offline, json.dumps(changed).encode("utf-8"))
                intake = accept_review(offline, raw)
                require_equal(intake.original, raw)
                require_readings(intake.readings, case, issued, case.original)
                if case.name == "carry":
                    require_refused(publish_review, offline, intake.intake_id, {3: (0, 0)})
                for edits, expected in (({}, case.original), *case.reviews):
                    if expected is None:
                        require_refused(publish_review, offline, intake.intake_id, edits)
                        print(json.dumps({"case": case.name, "edits": edits, "status": "refused"}))
                        continue
                    finding, receipt = publish_review(offline, intake.intake_id, edits)
                    require_equal((finding.intake_id, finding.edits), (intake.intake_id, edits))
                    require_equal((receipt.finding_id, receipt.intake_id), (finding.finding_id, intake.intake_id))
                    require_readings(finding.readings, case, issued, expected)
                    valid = [value for value in expected if value is not None]
                    require_equal(finding.metrics, Metrics(len(valid), max(valid, default=None)))
                    archived.append((case, finding, receipt))

        with closing(open_offline(review_path)) as offline:
            for case, saved, original_receipt in archived:
                finding, receipt = fetch_review(offline, saved.finding_id)
                require_equal(finding.finding_id, saved.finding_id)
                require_equal(finding.intake_id, saved.intake_id)
                require_equal(finding.edits, saved.edits)
                require_equal(finding.readings, saved.readings)
                require_equal(finding.metrics, saved.metrics)
                require_equal(receipt, original_receipt)
                print(json.dumps({"case": case.name, "edits": finding.edits,
                                  "review": [row.value for row in finding.readings.frames],
                                  "finding_id": finding.finding_id, "receipt_id": receipt.receipt_id}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Check the anchor review handoff examples.")
    parser.add_argument("--review", action="store_true", help="exercise the V2 handoff and reopen its archive")
    if parser.parse_args().review:
        review_examples()
    else:
        v1_examples()
