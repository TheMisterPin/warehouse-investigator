"""Deterministic warehouse fixtures used by the local demo tools."""

TICKETS = {
    "INC-001": {
        "id": "INC-001",
        "title": "Destination stock is six units short after replenishment",
        "sku": "SKU-RED-CHAIR",
        "location": "SEA-01",
        "reported_at": "2026-08-27T15:00:00Z",
        "expected_quantity": 100,
        "observed_quantity": 94,
        "document_refs": ["TR-100"],
        "notes": "Receiving team expected the scheduled replenishment from PDX-01.",
    },
    "INC-002": {
        "id": "INC-002",
        "title": "Available quantity remains low after cancelled order",
        "sku": "SKU-BLUE-LAMP",
        "location": "SEA-01",
        "reported_at": "2026-08-27T18:00:00Z",
        "expected_quantity": 50,
        "observed_quantity": 41,
        "document_refs": ["SO-900"],
        "notes": "Physical count is 50; the issue is available-to-promise quantity.",
    },
    "INC-003": {
        "id": "INC-003",
        "title": "Cycle count discrepancy has not reached inventory balance",
        "sku": "SKU-GREEN-DESK",
        "location": "PDX-01",
        "reported_at": "2026-08-27T11:00:00Z",
        "expected_quantity": 97,
        "observed_quantity": 100,
        "document_refs": ["CC-300"],
        "notes": "A cycle count was completed this morning.",
    },
}

LEDGER_EVENTS = [
    {
        "id": "EV-1001",
        "ticket_id": "INC-001",
        "timestamp": "2026-08-27T12:00:00Z",
        "sku": "SKU-RED-CHAIR",
        "location": "PDX-01",
        "event_type": "transfer_shipped",
        "quantity_delta": -6,
        "document_id": "TR-100",
        "state": "posted",
    },
    {
        "id": "EV-1002",
        "ticket_id": "INC-001",
        "timestamp": "2026-08-27T12:00:00Z",
        "sku": "SKU-RED-CHAIR",
        "location": "SEA-01",
        "event_type": "transfer_received",
        "quantity_delta": 0,
        "document_id": "TR-100",
        "state": "pending",
    },
    {
        "id": "EV-2001",
        "ticket_id": "INC-002",
        "timestamp": "2026-08-27T08:00:00Z",
        "sku": "SKU-BLUE-LAMP",
        "location": "SEA-01",
        "event_type": "reservation_created",
        "quantity_delta": -9,
        "document_id": "SO-900",
        "state": "active",
    },
    {
        "id": "EV-2002",
        "ticket_id": "INC-002",
        "timestamp": "2026-08-27T09:00:00Z",
        "sku": "SKU-BLUE-LAMP",
        "location": "SEA-01",
        "event_type": "order_cancelled",
        "quantity_delta": 0,
        "document_id": "SO-900",
        "state": "posted",
    },
    {
        "id": "EV-3001",
        "ticket_id": "INC-003",
        "timestamp": "2026-08-27T10:15:00Z",
        "sku": "SKU-GREEN-DESK",
        "location": "PDX-01",
        "event_type": "cycle_count_completed",
        "quantity_delta": -3,
        "document_id": "CC-300",
        "state": "pending_approval",
    },
]

DOCUMENTS = {
    "TR-100": {
        "id": "TR-100",
        "type": "transfer",
        "status": "in_transit",
        "source_location": "PDX-01",
        "destination_location": "SEA-01",
        "sku": "SKU-RED-CHAIR",
        "quantity": 6,
        "shipped_at": "2026-08-27T12:00:00Z",
        "received_at": None,
    },
    "SO-900": {
        "id": "SO-900",
        "type": "sales_order",
        "status": "cancelled",
        "location": "SEA-01",
        "sku": "SKU-BLUE-LAMP",
        "quantity": 9,
        "cancelled_at": "2026-08-27T09:00:00Z",
        "reservation_release_id": None,
    },
    "CC-300": {
        "id": "CC-300",
        "type": "cycle_count",
        "status": "pending_approval",
        "location": "PDX-01",
        "sku": "SKU-GREEN-DESK",
        "counted_quantity": 97,
        "system_quantity": 100,
    },
}

SNAPSHOTS = [
    {"sku": "SKU-RED-CHAIR", "location": "SEA-01", "physical_quantity": 94, "reserved_quantity": 0, "available_quantity": 94},
    {"sku": "SKU-BLUE-LAMP", "location": "SEA-01", "physical_quantity": 50, "reserved_quantity": 9, "available_quantity": 41},
    {"sku": "SKU-GREEN-DESK", "location": "PDX-01", "physical_quantity": 100, "reserved_quantity": 0, "available_quantity": 100},
]

GROUND_TRUTH = {
    "INC-001": "TRANSFER_NOT_RECEIVED",
    "INC-002": "STALE_RESERVATION",
    "INC-003": "PENDING_CYCLE_COUNT",
}

EVALUATION_CASES = {
    "INC-001": {
        "root_cause_code": "TRANSFER_NOT_RECEIVED",
        "required_evidence_ids": ["TR-100", "EV-1002"],
        "action_keywords": ["receive", "receipt", "receiving"],
        "requires_escalation": False,
    },
    "INC-002": {
        "root_cause_code": "STALE_RESERVATION",
        "required_evidence_ids": ["SO-900", "EV-2001", "EV-2002"],
        "action_keywords": ["release", "reservation", "unreserve"],
        "requires_escalation": False,
    },
    "INC-003": {
        "root_cause_code": "PENDING_CYCLE_COUNT",
        "required_evidence_ids": ["CC-300", "EV-3001"],
        "action_keywords": ["approve", "approval", "post", "adjustment"],
        "requires_escalation": False,
    },
}
