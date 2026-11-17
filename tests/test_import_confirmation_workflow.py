from datetime import date

from app.services import import_confirmation as service


class _Result:
    def __init__(self, row=None, rowcount=0):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return []


class _ReconcileConnection:
    def __init__(self, identity, rowcount=0):
        self.identity = identity
        self.update_rowcount = rowcount
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if query.lstrip().startswith("SELECT"):
            return _Result(row=self.identity)
        if query.lstrip().startswith("UPDATE khs_follow_ups"):
            return _Result(rowcount=self.update_rowcount)
        return _Result(rowcount=1)


class _UpsertConnection:
    def __init__(self, existing):
        self.existing = existing
        self.calls = []

    def execute(self, query, params=None):
        self.calls.append((query, params))
        normalized = query.lstrip()
        if normalized.startswith("SELECT") and "FROM khs_items" in query:
            columns = ("khs_id",) + service.ITEM_FIELDS
            return _Result(row=tuple(self.existing.get(column) for column in columns))
        return _Result(rowcount=1)


def test_import_reconciliation_supersedes_only_reminders_outside_current_stage():
    conn = _ReconcileConnection(
        ("ACTIVE", "LP_CIRCULATION", "contract_team"),
        rowcount=2,
    )

    result = service._reconcile_imported_workflow_follow_ups(
        conn, "KHS-2026-0001", 17
    )

    assert result == 2
    update_query, update_params = next(
        call for call in conn.calls
        if call[0].lstrip().startswith("UPDATE khs_follow_ups")
    )
    assert "status = 'OPEN'" in update_query
    assert "stage_code IS DISTINCT FROM %s" in update_query
    assert "stage_key IS DISTINCT FROM %s" in update_query
    assert update_params == (
        "KHS-2026-0001",
        "ACTIVE",
        "LP_CIRCULATION",
        "LP_CIRCULATION",
        "contract_team",
    )

    audit = next(
        call for call in conn.calls
        if "INSERT INTO khs_activity_logs" in call[0]
    )
    assert audit[1][0:4] == (
        "KHS_ITEM",
        "KHS-2026-0001",
        "FOLLOW_UPS_SUPERSEDED",
        "excel-import",
    )
    assert audit[1][5] == 17


def test_import_reconciliation_supersedes_all_open_reminders_for_non_active_or_completed_khs():
    conn = _ReconcileConnection(
        ("NOT_PROCEEDED", "LP_CIRCULATION", "contract_team"),
        rowcount=3,
    )

    result = service._reconcile_imported_workflow_follow_ups(
        conn, "KHS-2026-0002", 18
    )

    assert result == 3
    update_query, update_params = next(
        call for call in conn.calls
        if call[0].lstrip().startswith("UPDATE khs_follow_ups")
    )
    assert "%s <> 'ACTIVE'" in update_query
    assert update_params[1] == "NOT_PROCEEDED"


def test_import_reconciliation_does_not_write_audit_when_no_reminder_is_stale():
    conn = _ReconcileConnection(
        ("ACTIVE", "NEGOTIATION", "NEGOTIATION"),
        rowcount=0,
    )

    assert service._reconcile_imported_workflow_follow_ups(
        conn, "KHS-2026-0003", 19
    ) == 0
    assert not any("INSERT INTO khs_activity_logs" in query for query, _ in conn.calls)


def test_khs_import_reconciles_follow_ups_when_a_workflow_milestone_changes(monkeypatch):
    columns = ("khs_id",) + service.ITEM_FIELDS
    existing = {column: None for column in columns}
    existing.update({
        "khs_id": "KHS-2026-0004",
        "request_id": "REQ-2026-0004",
        "vendor_name": "Example Vendor",
        "dispatch_date": date(2026, 1, 5),
    })
    conn = _UpsertConnection(existing)
    reconciled = []

    monkeypatch.setattr(
        service,
        "_reconcile_imported_workflow_follow_ups",
        lambda connection, khs_id, batch_id: reconciled.append(
            (connection, khs_id, batch_id)
        ),
    )

    result = service._upsert_entity(
        conn,
        "KHS_ITEM",
        {
            "khs_id": "KHS-2026-0004",
            "request_id": "REQ-2026-0004",
            "vendor_name": "Example Vendor",
            "dispatch_date": date(2026, 1, 6),
        },
        20,
    )

    assert result == "UPDATED"
    assert reconciled == [(conn, "KHS-2026-0004", 20)]


def test_khs_import_does_not_reconcile_follow_ups_for_metadata_only_changes(monkeypatch):
    columns = ("khs_id",) + service.ITEM_FIELDS
    existing = {column: None for column in columns}
    existing.update({
        "khs_id": "KHS-2026-0005",
        "request_id": "REQ-2026-0005",
        "vendor_name": "Old Vendor Name",
    })
    conn = _UpsertConnection(existing)
    reconciled = []

    monkeypatch.setattr(
        service,
        "_reconcile_imported_workflow_follow_ups",
        lambda *args: reconciled.append(args),
    )

    result = service._upsert_entity(
        conn,
        "KHS_ITEM",
        {
            "khs_id": "KHS-2026-0005",
            "request_id": "REQ-2026-0005",
            "vendor_name": "New Vendor Name",
        },
        21,
    )

    assert result == "UPDATED"
    assert reconciled == []
