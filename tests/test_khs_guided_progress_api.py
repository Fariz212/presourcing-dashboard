from contextlib import contextmanager
from copy import deepcopy
from datetime import date
import re

import pytest
from flask import Flask

from app.routes import dashboard as dashboard_module
from app.routes.dashboard import dashboard_bp


class ProgressCursor:
    def __init__(self, connection):
        self.connection = connection
        self.row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.connection.queries.append((query, params))
        if "SELECT process_status FROM khs_items" in query:
            self.row = {"process_status": self.connection.record["process_status"]}
        elif "WHERE k.khs_id=%s" in query:
            self.row = deepcopy(self.connection.record)
        else:
            self.row = None

    def fetchone(self):
        return deepcopy(self.row)


class ProgressConnection:
    def __init__(self, record):
        self.record = record
        self.queries = []
        self.cursor_object = ProgressCursor(self)

    @contextmanager
    def transaction(self):
        yield self

    def cursor(self, row_factory=None):
        return self.cursor_object

    def execute(self, query, params=None):
        self.queries.append((query, params))
        if query.startswith("UPDATE khs_items SET"):
            field = re.search(r"SET\s+([a-z_]+)=", query).group(1)
            self.record[field] = params[0]
        return self


class ProgressPool:
    def __init__(self, record):
        self.record = record
        self.connections = []

    @contextmanager
    def connection(self):
        connection = ProgressConnection(self.record)
        self.connections.append(connection)
        yield connection


def _progress_record(**overrides):
    record = {
        "khs_id": "KHS-PROGRESS-001",
        "request_id": "REQ-PROGRESS-001",
        "process_status": "ACTIVE",
        "workflow_status": "in_progress",
        "workflow_stage_code": "MI_GM_APPROVAL",
        "current_stage_code": "MI_GM_APPROVAL",
        "current_stage_started_on": date(2026, 11, 10),
        "request_date": date(2026, 11, 1),
        "dispatch_date": date(2026, 11, 3),
        "boq_confirmation_date": date(2026, 11, 4),
        "negotiation_date": date(2026, 11, 5),
        "final_negotiation_date": date(2026, 11, 6),
        "mi_head_approval_date": date(2026, 11, 7),
        "mi_sm_approval_date": date(2026, 11, 10),
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
        "lp_stage_key": None,
        "closure_date": None,
    }
    record.update(overrides)
    return record


@pytest.fixture
def make_progress_client(monkeypatch):
    def _make(record):
        pool = ProgressPool(record)
        monkeypatch.setattr(dashboard_module, "get_db_pool", lambda: pool)
        monkeypatch.setattr(dashboard_module, "_jakarta_today", lambda: date(2026, 11, 17))
        monkeypatch.setattr(
            dashboard_module,
            "_register_enriched",
            lambda row, **kwargs: {**row, "enriched_for_test": True},
        )
        app = Flask(__name__)
        app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
        app.config["TESTING"] = True
        return app.test_client(), pool
    return _make


def _api_calls(pool):
    return [call for connection in pool.connections for call in connection.queries]


def test_guided_progress_updates_only_the_current_next_milestone_and_audits_it(make_progress_client):
    client, pool = make_progress_client(_progress_record())
    response = client.post(
        "/api/dashboard/khs/KHS-PROGRESS-001/progress",
        json={"milestone_date": "2026-11-11", "note": "GM approval evidenced."},
    )

    assert response.status_code == 200
    assert response.get_json()["success"] is True
    assert pool.record["mi_gm_approval_date"] == date(2026, 11, 11)
    updates = [query for query, _ in _api_calls(pool) if query.startswith("UPDATE khs_items SET")]
    assert len(updates) == 1
    assert "mi_gm_approval_date" in updates[0]
    audits = [params for query, params in _api_calls(pool) if "INSERT INTO khs_activity_logs" in query]
    assert len(audits) == 1
    assert audits[0][2] == "PROGRESS_UPDATED"
    superseded = [
        params for query, params in _api_calls(pool)
        if "UPDATE khs_follow_ups" in query and "SUPERSEDED" in query
    ]
    assert len(superseded) == 1
    assert superseded[0] == ("KHS-PROGRESS-001", "MI_GM_APPROVAL", "MI_GM_APPROVAL")


@pytest.mark.parametrize(
    ("milestone_date", "expected_code", "expected_status"),
    [
        ("2026-11-09", "MILESTONE_BEFORE_PREVIOUS", 422),
        ("2026-11-18", "FUTURE_MILESTONE_DATE", 422),
    ],
)
def test_guided_progress_rejects_out_of_order_and_future_dates_without_writing(
    make_progress_client, milestone_date, expected_code, expected_status
):
    client, pool = make_progress_client(_progress_record())
    response = client.post(
        "/api/dashboard/khs/KHS-PROGRESS-001/progress",
        json={"milestone_date": milestone_date},
    )

    assert response.status_code == expected_status
    assert response.get_json()["code"] == expected_code
    assert not any(query.startswith("UPDATE khs_items SET") for query, _ in _api_calls(pool))
    assert not any("INSERT INTO khs_activity_logs" in query for query, _ in _api_calls(pool))


def test_guided_progress_rejects_a_closed_khs_before_reading_or_writing_milestones(make_progress_client):
    client, pool = make_progress_client(_progress_record(process_status="NOT_PROCEEDED"))
    response = client.post(
        "/api/dashboard/khs/KHS-PROGRESS-001/progress",
        json={"milestone_date": "2026-11-11"},
    )

    assert response.status_code == 409
    assert response.get_json()["code"] == "KHS_NOT_ACTIVE"
    assert not any(query.startswith("UPDATE khs_items SET") for query, _ in _api_calls(pool))
    assert not any("INSERT INTO khs_activity_logs" in query for query, _ in _api_calls(pool))


def test_guided_progress_requires_a_predecessor_milestone_even_if_current_stage_is_inconsistent(make_progress_client):
    record = _progress_record(mi_sm_approval_date=None)
    client, pool = make_progress_client(record)
    response = client.post(
        "/api/dashboard/khs/KHS-PROGRESS-001/progress",
        json={"milestone_date": "2026-11-11"},
    )

    assert response.status_code == 422
    assert response.get_json()["code"] == "PREVIOUS_MILESTONE_REQUIRED"
    assert not any(query.startswith("UPDATE khs_items SET") for query, _ in _api_calls(pool))
