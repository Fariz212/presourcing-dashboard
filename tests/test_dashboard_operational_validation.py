from datetime import date, datetime

import pytest

from app.routes.dashboard import (
    ITEM_FIELDS,
    REQUEST_FIELDS,
    _json_safe_value,
    _next_generated_id,
    _validate_payload,
)


def test_request_payload_trims_text_and_accepts_iso_date():
    payload = _validate_payload(
        {
            "request_subject": "  Renewal - Vendor A  ",
            "request_date": "2026-11-12",
            "requester_owner": "  Procurement  ",
        },
        REQUEST_FIELDS | {"request_id"},
        {"request_subject"},
    )
    assert payload["request_subject"] == "Renewal - Vendor A"
    assert payload["request_date"] == date(2026, 11, 12)
    assert payload["requester_owner"] == "Procurement"


def test_khs_payload_normalizes_executor_and_rejects_unknown_fields():
    payload = _validate_payload(
        {"request_id": "REQ-2026-005", "vendor_name": " Vendor A ",
         "executor_code": "fzk", "subtype": "Renewal"},
        ITEM_FIELDS | {"khs_id"},
        {"request_id", "vendor_name", "executor_code"},
    )
    assert payload["executor_code"] == "FZK"
    assert payload["vendor_name"] == "Vendor A"

    with pytest.raises(ValueError, match="Unsupported fields"):
        _validate_payload(
            {"request_id": "REQ-2026-005", "vendor_name": "Vendor A",
             "executor_code": "FZK", "password": "not-allowed"},
            ITEM_FIELDS | {"khs_id"},
            {"request_id", "vendor_name", "executor_code"},
        )


def test_payload_requires_nonblank_required_fields_and_valid_dates():
    with pytest.raises(ValueError, match="Required fields"):
        _validate_payload(
            {"request_subject": "   "},
            REQUEST_FIELDS | {"request_id"},
            {"request_subject"},
        )

    with pytest.raises(ValueError, match="YYYY-MM-DD"):
        _validate_payload(
            {"dispatch_date": "12/11/2026"},
            ITEM_FIELDS | {"khs_id"},
            set(),
        )


def test_json_safe_conversion_handles_nested_dates():
    value = {
        "created": date(2026, 11, 12),
        "nested": [{"updated": datetime(2026, 11, 12, 9, 30)}],
    }
    assert _json_safe_value(value) == {
        "created": "2026-11-12",
        "nested": [{"updated": "2026-11-12T09:30:00"}],
    }


def test_khs_injection_dates_are_parsed_as_iso_dates():
    payload = _validate_payload(
        {
            "khs_inject_start_date": "2026-11-20",
            "khs_inject_completion_date": "2026-11-22",
        },
        ITEM_FIELDS | {"khs_id"},
        set(),
    )
    assert payload["khs_inject_start_date"] == date(2026, 11, 20)
    assert payload["khs_inject_completion_date"] == date(2026, 11, 22)


class IdCursor:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class IdConnection:
    def __init__(self, existing):
        self.existing = existing
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if "SELECT request_id" in query or "SELECT khs_id" in query:
            return IdCursor((self.existing,) if self.existing else None)
        return IdCursor()


def test_generated_id_increments_current_year_sequence():
    conn = IdConnection("REQ-2026-005")
    result = _next_generated_id(
        conn, "khs_requests", "request_id", "REQ-2026-", 3
    )
    assert result == "REQ-2026-006"
    assert len(conn.calls) == 2
    assert "pg_advisory_xact_lock" in conn.calls[0][0]


def test_generated_id_starts_at_one_when_no_matching_record_exists():
    conn = IdConnection(None)
    result = _next_generated_id(
        conn, "khs_items", "khs_id", "KHS-2026-", 4
    )
    assert result == "KHS-2026-0001"
