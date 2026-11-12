from contextlib import contextmanager
from datetime import date

from app.services.import_confirmation import (
    ITEM_FIELDS,
    confirm_import,
    _upsert_entity,
)


class Result:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class FakeConnection:
    def __init__(self, existing, staged=None):
        self.existing = existing
        self.staged = staged or []
        self.queries = []

    @contextmanager
    def transaction(self):
        yield self

    def execute(self, query, params=None):
        self.queries.append((query, params))
        normalized = " ".join(query.split())

        if "FROM khs_items" in normalized and "FOR UPDATE" in normalized:
            return Result(one=self.existing)

        if "FROM khs_requests WHERE request_id" in normalized:
            return Result(one=("REQ-2026-001",))

        if "FROM khs_import_batches" in normalized and "FOR UPDATE" in normalized:
            return Result(one=(77, "PREVIEWED", 1, 0, 0))

        if "FROM khs_import_rows" in normalized and "FOR UPDATE" in normalized:
            return Result(many=self.staged)

        return Result(one=None)


class FakePool:
    def __init__(self, connection):
        self.connection_object = connection

    @contextmanager
    def connection(self):
        yield self.connection_object


def _existing_item_tuple():
    existing = {field: None for field in ITEM_FIELDS}
    existing.update({
        "request_id": "REQ-2026-001",
        "vendor_name": "PT Existing Vendor",
        "lp_completion_date": date(2026, 11, 12),
        "khs_inject_start_date": None,
        "khs_inject_completion_date": None,
    })
    return ("KHS-2026-0001",) + tuple(existing[field] for field in ITEM_FIELDS)


def test_excel_upsert_persists_khs_inject_milestones():
    connection = FakeConnection(existing=_existing_item_tuple())
    record = {
        "khs_id": "KHS-2026-0001",
        "request_id": "REQ-2026-001",
        "vendor_name": "PT Existing Vendor",
        "khs_inject_start_date": date(2026, 11, 13),
        "khs_inject_completion_date": date(2026, 11, 14),
    }

    result = _upsert_entity(connection, "KHS_ITEM", record, batch_id=77)

    assert result == "UPDATED"
    update_query, update_params = next(
        (query, params)
        for query, params in connection.queries
        if "UPDATE khs_items SET" in query
    )
    assert "khs_inject_start_date = %s" in update_query
    assert "khs_inject_completion_date = %s" in update_query
    assert date(2026, 11, 13) in update_params
    assert date(2026, 11, 14) in update_params


def test_excel_partial_khs_update_accepts_parent_request_from_database():
    record = {
        "khs_id": "KHS-2026-0001",
        "request_id": "REQ-2026-001",
        "vendor_name": "PT Existing Vendor",
        "khs_inject_start_date": date(2026, 11, 13),
    }
    staged = [
        (10, "KHS_ITEM", "KHS-2026-0001", "VALID", record)
    ]
    connection = FakeConnection(
        existing=_existing_item_tuple(),
        staged=staged,
    )

    result = confirm_import(FakePool(connection), 77)

    assert result["status"] == "IMPORTED"
    assert result["updated_items"] == 1
    assert any(
        "SELECT 1 FROM khs_requests WHERE request_id" in query
        for query, _ in connection.queries
    )


def test_blank_excel_fields_are_not_added_to_update_payload():
    connection = FakeConnection(existing=_existing_item_tuple())
    record = {
        "khs_id": "KHS-2026-0001",
        "request_id": "REQ-2026-001",
        "vendor_name": "PT Existing Vendor",
        "khs_inject_start_date": date(2026, 11, 13),
        # A blank Excel cell parses as None and is intentionally omitted.
        "dispatch_date": None,
    }

    _upsert_entity(connection, "KHS_ITEM", record, batch_id=77)

    update_query, _ = next(
        (query, params)
        for query, params in connection.queries
        if "UPDATE khs_items SET" in query
    )
    assert "khs_inject_start_date = %s" in update_query
    assert "dispatch_date" not in update_query
