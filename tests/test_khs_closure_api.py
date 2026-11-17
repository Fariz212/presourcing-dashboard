from contextlib import contextmanager
from datetime import date

import pytest
from flask import Flask

from app.routes.dashboard import dashboard_bp


class ClosureCursor:
    def __init__(self, row):
        self.row = row
        self.query = None
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params

    def fetchone(self):
        return self.row


class ClosureConnection:
    def __init__(self, row):
        self.row = row
        self.calls = []
        self.cursor_object = ClosureCursor(row)

    @contextmanager
    def transaction(self):
        yield self

    def cursor(self, row_factory=None):
        return self.cursor_object

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self


class ClosurePool:
    def __init__(self, row):
        self.connection_object = ClosureConnection(row)

    @contextmanager
    def connection(self):
        yield self.connection_object


@pytest.fixture
def make_closure_client(monkeypatch):
    def _make(row):
        pool = ClosurePool(row)
        monkeypatch.setattr("app.routes.dashboard.get_db_pool", lambda: pool)
        monkeypatch.setattr("app.routes.dashboard._jakarta_today", lambda: date(2026, 11, 17))
        app = Flask(__name__)
        app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
        app.config["TESTING"] = True
        return app.test_client(), pool
    return _make


def base_khs_row(**overrides):
    row = {
        "khs_id": "KHS-2026-0001",
        "request_id": "REQ-2026-001",
        "parent_request_date": date(2026, 1, 1),
        "process_status": "ACTIVE",
        "closure_date": None,
        "closure_reason_code": None,
        "closure_notes": None,
        "closed_at": None,
        "closed_by": None,
        "reopened_at": None,
        "reopened_by": None,
        "reopen_reason": None,
        "dispatch_date": date(2026, 1, 5),
        "boq_confirmation_date": None,
        "negotiation_date": None,
        "final_negotiation_date": None,
        "mi_head_approval_date": None,
        "mi_sm_approval_date": None,
        "mi_gm_approval_date": None,
        "legal_submission_date": None,
        "lp_circulation_start_date": None,
        "lp_contract_team_completion_date": None,
        "lp_junior_manager_approval_date": None,
        "lp_senior_manager_approval_date": None,
        "lp_gm_scm_approval_date": None,
        "lp_completion_date": None,
        "khs_inject_start_date": None,
        "khs_inject_completion_date": None,
    }
    row.update(overrides)
    return row


def test_close_khs_sets_not_proceeded_and_writes_audit(make_closure_client):
    client, pool = make_closure_client(base_khs_row())
    response = client.post(
        "/api/dashboard/khs/KHS-2026-0001/close",
        json={
            "closure_date": "2026-01-15",
            "closure_reason_code": "NO_MUTUAL_AGREEMENT",
            "closure_notes": "Negotiation did not reach agreement.",
        },
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    updates = [call for call in pool.connection_object.calls if "UPDATE khs_items" in call[0]]
    audits = [call for call in pool.connection_object.calls if "INSERT INTO khs_activity_logs" in call[0]]
    assert len(updates) == 1
    assert updates[0][1][:3] == (
        date(2026, 1, 15), "NO_MUTUAL_AGREEMENT", "Negotiation did not reach agreement."
    )
    assert len(audits) == 1
    assert audits[0][1][2] == "CLOSED_NOT_PROCEEDED"


@pytest.mark.parametrize(
    ("row", "closure_date", "expected_code"),
    [
        (base_khs_row(khs_inject_completion_date=date(2026, 2, 1)), "2026-02-02", "KHS_ALREADY_INJECTED"),
        (base_khs_row(parent_request_date=date(2026, 2, 1)), "2026-01-31", "CLOSURE_DATE_BEFORE_REQUEST"),
        (base_khs_row(dispatch_date=date(2026, 2, 10)), "2026-02-09", "CLOSURE_DATE_BEFORE_LAST_MILESTONE"),
    ],
)
def test_close_khs_rejects_invalid_terminal_transitions(
    make_closure_client, row, closure_date, expected_code
):
    client, pool = make_closure_client(row)
    response = client.post(
        "/api/dashboard/khs/KHS-2026-0001/close",
        json={
            "closure_date": closure_date,
            "closure_reason_code": "NO_MUTUAL_AGREEMENT",
        },
    )

    assert response.status_code == 409 if expected_code == "KHS_ALREADY_INJECTED" else 422
    assert response.get_json()["code"] == expected_code
    assert not any("UPDATE khs_items" in query for query, _ in pool.connection_object.calls)


def test_close_khs_requires_notes_for_other_reason(make_closure_client):
    client, pool = make_closure_client(base_khs_row())
    response = client.post(
        "/api/dashboard/khs/KHS-2026-0001/close",
        json={
            "closure_date": "2026-01-15",
            "closure_reason_code": "OTHER",
        },
    )

    assert response.status_code == 422
    assert response.get_json()["code"] == "CLOSURE_NOTES_REQUIRED"
    assert not any("UPDATE khs_items" in query for query, _ in pool.connection_object.calls)


def test_reopen_khs_preserves_closure_and_adds_reopen_audit(make_closure_client):
    client, pool = make_closure_client(base_khs_row(
        process_status="NOT_PROCEEDED",
        closure_date=date(2026, 1, 15),
        closure_reason_code="NO_MUTUAL_AGREEMENT",
        closed_at="2026-01-15T10:00:00+07:00",
        closed_by="manual-entry",
    ))
    response = client.post(
        "/api/dashboard/khs/KHS-2026-0001/reopen",
        json={"reopen_reason": "The parties agreed to resume negotiations."},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    updates = [call for call in pool.connection_object.calls if "UPDATE khs_items" in call[0]]
    audits = [call for call in pool.connection_object.calls if "INSERT INTO khs_activity_logs" in call[0]]
    assert len(updates) == 1
    assert "process_status='ACTIVE'" in updates[0][0]
    assert updates[0][1][0] == "The parties agreed to resume negotiations."
    assert len(audits) == 1
    assert audits[0][1][2] == "REOPENED"
