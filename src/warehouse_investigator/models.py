from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class InvestigationResult:
    ticket_id: str
    root_cause_code: str
    summary: str
    evidence_ids: list[str]
    recommended_action: str
    confidence: float
    requires_escalation: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "InvestigationResult":
        required = {
            "ticket_id",
            "root_cause_code",
            "summary",
            "evidence_ids",
            "recommended_action",
            "confidence",
            "requires_escalation",
        }
        missing = required - value.keys()
        if missing:
            raise ValueError(f"Final result is missing required fields: {sorted(missing)}")
        if not isinstance(value["evidence_ids"], list) or not all(
            isinstance(item, str) for item in value["evidence_ids"]
        ):
            raise ValueError("evidence_ids must be a list of strings")
        confidence = float(value["confidence"])
        if not 0 <= confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")
        if not isinstance(value["requires_escalation"], bool):
            raise ValueError("requires_escalation must be a boolean")
        return cls(
            ticket_id=str(value["ticket_id"]),
            root_cause_code=str(value["root_cause_code"]),
            summary=str(value["summary"]),
            evidence_ids=value["evidence_ids"],
            recommended_action=str(value["recommended_action"]),
            confidence=confidence,
            requires_escalation=value["requires_escalation"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


RESULT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticket_id": {"type": "string"},
        "root_cause_code": {"type": "string"},
        "summary": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
        "recommended_action": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "requires_escalation": {"type": "boolean"},
    },
    "required": [
        "ticket_id",
        "root_cause_code",
        "summary",
        "evidence_ids",
        "recommended_action",
        "confidence",
        "requires_escalation",
    ],
    "additionalProperties": False,
}
