from dataclasses import dataclass
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class FindingReceipt:
    receipt_id: str
    finding_id: str
    intake_id: str


def make_receipt(finding_id: str, intake_id: str) -> FindingReceipt:
    return FindingReceipt(f'filed-{uuid4().hex}', finding_id, intake_id)
