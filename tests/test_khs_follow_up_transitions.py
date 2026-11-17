from contextlib import contextmanager

import pytest
from flask import Flask

from app.routes import dashboard as dashboard_module
from app.routes.dashboard import dashboard_bp


class _Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.connection.cursor_queries.append((query, params))
        if "FOR UPDATE OF k" in query:
            self.row = {"khs_id": self.connection.khs_id}
        elif "CROSS JOIN LATERAL" in query:
            self.row = dict(self.connection.current_record)
        elif "SELECT f.*, k.process_status" in query:
            self.row = {
                **self.connection.follow_up,
                "process_status": self.connection.current_record["process_status"],
            }
        else:
            self.row = None

    def fetchone(self):
        return self.row


class _Connection:
    def __init__(self, current_record, follow_up):
        self.current_record = current_record
        self.follow_up = follow_up
        self.khs_id = follow_up["khs_id"]
        self.cursor_queries = []
        self.calls = []

    @contextmanager
    def transaction(self):
        yield self

    def cursor(self, row_factory=None):
        return _Cursor(self)

    def execute(self, query, params=None):
        self.calls.append((query, params))
        return self


class _Pool:
    def __init__(self, connection):
        self.connection_object = connection

    @contextmanager
    def connection(self):
        yield self.connection_object


def _make_client(monkeypatch, current_record, follow_up):
    connection = _Connection(current_record, follow_up)
    monkeypatch.setattr(
        dashboard_module,
        "get_db_pool",
        lambda: _Pool(connection),
    )
    app = Flask(__name__)
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    app.config["TESTING"] = True
    return app.test_client(), connection


def _record(**overrides):
    result = {
        "khs_id": "KHS-FOLLOW-UP-001",
        "process_status": "ACTIVE",
        "workflow_status": "in_progress",
        "workflow_stage_code": "MI_GM_APPROVAL",
        "current_stage_code": "MI_GM_APPROVAL",
        "lp_stage_key": None,
        "khs_inject_start_date": None,
    }
    result.update(overrides)
    return result


def _follow_up(**overrides):
    result = {
        "id": 71,
        "khs_id": "KHS-FOLLOW-UP-001",
        "stage_code": "MI_GM_APPROVAL",
        "stage_key": "MI_GM_APPROVAL",
        "status": "OPEN",
        "due_date": "2026-11-20",
        "follow_up_to": "MI GM",
        "note": "Record MI GM approval.",
    }
    result.update(overrides)
    return result


def test_current_stage_follow_up_can_be_completed(monkeypatch):
    client, connection = _make_client(
        monkeypatch,
        _record(),
        _follow_up(),
    )

    response = client.post(
        "/api/dashboard/operations/follow-ups/71/complete",
        json={},
    )

    assert response.status_code == 200
    assert response.get_json()["data"]["status"] == "COMPLETED"
    assert any(
        "SET status=%s" in query and params == ("COMPLETED", 71)
        for query, params in connection.calls
    )
    assert any(
        "INSERT INTO khs_activity_logs" in query and params[2] == "FOLLOW_UP_COMPLETED"
        for query, params in connection.calls
    )


@pytest.mark.parametrize(
    "current_record",
    [
        _record(workflow_stage_code="LEGAL_SUBMISSION", current_stage_code="LEGAL_SUBMISSION"),
        _record(process_status="NOT_PROCEEDED"),
        _record(workflow_stage_code="COMPLETED", current_stage_code="COMPLETED",
                workflow_status="completed"),
        _record(workflow_stage_code="KHS_INJECTION", current_stage_code="KHS_INJECTION",
                khs_inject_start_date="2026-11-15"),
    ],
)
def test_stale_or_terminal_stage_follow_up_is_superseded_and_cannot_be_completed(
    monkeypatch, current_record
):
    client, connection = _make_client(
        monkeypatch,
        current_record,
        _follow_up(),
    )

    response = client.post(
        "/api/dashboard/operations/follow-ups/71/complete",
        json={},
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "FOLLOW_UP_SUPERSEDED"
    assert any(
        "status='SUPERSEDED'" in query and params == (71,)
        for query, params in connection.calls
    )
    assert any(
        "INSERT INTO khs_activity_logs" in query and params[2] == "FOLLOW_UP_SUPERSEDED"
        for query, params in connection.calls
    )
    assert not any(
        "FOLLOW_UP_COMPLETED" in (params[2] if len(params) > 2 else "")
        for query, params in connection.calls
        if "INSERT INTO khs_activity_logs" in query
    )


def test_stale_follow_up_is_also_superseded_when_user_attempts_to_cancel(monkeypatch):
    client, connection = _make_client(
        monkeypatch,
        _record(workflow_stage_code="LEGAL_SUBMISSION", current_stage_code="LEGAL_SUBMISSION"),
        _follow_up(),
    )

    response = client.post(
        "/api/dashboard/operations/follow-ups/71/cancel",
        json={},
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "FOLLOW_UP_SUPERSEDED"
    assert any("status='SUPERSEDED'" in query for query, _ in connection.calls)
