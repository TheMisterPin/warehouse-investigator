import pytest

from warehouse_investigator.models import InvestigationResult


def test_result_rejects_invalid_confidence() -> None:
    payload = {
        "ticket_id": "INC-001",
        "root_cause_code": "TRANSFER_NOT_RECEIVED",
        "summary": "Transfer is in transit.",
        "evidence_ids": ["TR-100"],
        "recommended_action": "Receive the transfer.",
        "confidence": 1.2,
        "requires_escalation": False,
    }
    with pytest.raises(ValueError, match="confidence"):
        InvestigationResult.from_dict(payload)
