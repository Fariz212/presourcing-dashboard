from contextlib import contextmanager
from io import BytesIO

import pytest
from flask import Flask

from app.routes.dashboard import dashboard_bp


class FakeCursor:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.executed_query = None

    def execute(self, query):
        self.executed_query = query
        return FakeCursor(self.row)


class FakePool:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.connection_object = FakeConnection(row)

    @contextmanager
    def connection(self):
        if self.error:
            raise self.error
        yield self.connection_object


@pytest.fixture
def make_client(monkeypatch):
    def _make(pool):
        monkeypatch.setattr(
            "app.routes.dashboard.get_db_pool",
            lambda: pool,
        )

        app = Flask(__name__)
        app.register_blueprint(
            dashboard_bp,
            url_prefix="/api/dashboard",
        )
        app.config["TESTING"] = True
        return app.test_client()

    return _make


def test_dashboard_summary_returns_expected_kpis(make_client):
    # Requests, KHS, LP counts, inject counts, workflow checkpoints and data quality.
    row = (9, 64, 0, 34, 30, 0, 0, 0, 27, 37, 34, 7, 0)
    pool = FakePool(row=row)

    response = make_client(pool).get("/api/dashboard/summary")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["data"]["total_requests"] == 9
    assert payload["data"]["total_khs"] == 64

    assert payload["data"]["lp"] == {
        "completed": 0,
        "in_progress": 34,
        "not_started": 30,
        "completion_rate_percent": 0.0,
    }

    assert payload["data"]["khs_inject"] == {
        "completed": 0,
        "in_progress": 0,
        "pending": 0,
        "completion_rate_percent": 0.0,
    }
    assert payload["data"]["fully_injected"] == 0

    assert payload["data"]["workflow"] == {
        "mi_gm_approved": 27,
        "mi_gm_pending": 37,
        "legal_submitted": 34,
        "awaiting_lp_circulation": 0,
    }

    assert (
        payload["data"]["data_quality"][
            "lp_started_without_mi_gm_approval"
        ]
        == 7
    )

    assert "FROM khs_items" in pool.connection_object.executed_query


def test_dashboard_summary_handles_empty_database(make_client):
    pool = FakePool(row=(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))

    response = make_client(pool).get("/api/dashboard/summary")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["data"]["total_requests"] == 0
    assert payload["data"]["total_khs"] == 0
    assert payload["data"]["lp"]["completion_rate_percent"] == 0.0


def test_dashboard_summary_returns_json_when_database_fails(make_client):
    pool = FakePool(error=RuntimeError("simulated database failure"))

    response = make_client(pool).get("/api/dashboard/summary")

    assert response.status_code == 503
    payload = response.get_json()

    assert payload["success"] is False
    assert payload["code"] == "DASHBOARD_SUMMARY_UNAVAILABLE"


from contextlib import contextmanager
from datetime import date


class RegisterFakeCursor:
    def __init__(self, pool):
        self.pool = pool
        self.result = None
        self.rows = []
        self.query = ""
        self.params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        self.query = query
        self.params = params or []
        self.pool.queries.append((query, self.params))

        if "SELECT COUNT(*) AS total" in query:
            self.result = {"total": self.pool.total}
        else:
            self.rows = self.pool.rows

        return self

    def fetchone(self):
        return self.result

    def fetchall(self):
        return self.rows


class RegisterFakeConnection:
    def __init__(self, pool):
        self.pool = pool

    def cursor(self, row_factory=None):
        return RegisterFakeCursor(self.pool)


class RegisterFakePool:
    def __init__(self, rows=None, total=0, error=None):
        self.rows = rows or []
        self.total = total
        self.error = error
        self.queries = []

    @contextmanager
    def connection(self):
        if self.error:
            raise self.error
        yield RegisterFakeConnection(self)


def test_khs_register_returns_paginated_records(make_client):
    row = {
        "khs_id": "KHS-2026-0008",
        "request_id": "REQ-2026-005",
        "request_date": date(2026, 1, 5),
        "request_subject": "KHS Renewal",
        "requester_owner": "Procurement",
        "vendor_name": "PT Borneo Sarana Teknik",
        "executor_code": "FZK",
        "executor_name": "Farizky Ramadhan",
        "subtype": "Renewal",
        "dispatch_date": date(2026, 1, 6),
        "contract_start_date": None,
        "contract_end_date": None,
        "boq_confirmation_date": None,
        "negotiation_date": None,
        "final_negotiation_date": None,
        "mi_head_approval_date": None,
        "mi_sm_approval_date": None,
        "mi_gm_approval_date": None,
        "legal_submission_date": None,
        "lp_circulation_start_date": date(2026, 2, 1),
        "lp_completion_date": None,
        "waiting_for": None,
        "waiting_reason": None,
        "last_updated_date": None,
        "remarks": None,
        "updated_at": None,
        "lp_status": "in_progress",
        "workflow_status": "in_progress",
        "khs_inject_start_date": None,
        "khs_inject_completion_date": None,
        "current_stage_code": "LP_CIRCULATION",
        "current_stage_name": "LP Circulation",
        "lp_started_without_mi_gm_approval": True,
    }

    pool = RegisterFakePool(rows=[row], total=1)
    client = make_client(pool)

    response = client.get(
        "/api/dashboard/khs?page=2&per_page=10"
        "&q=borneo&lp_status=in_progress"
        "&executor_code=fzk&subtype=Renewal"
        "&stage=lp_circulation"
    )

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["pagination"] == {
        "page": 2,
        "per_page": 10,
        "total_records": 1,
        "total_pages": 1,
        "has_previous": True,
        "has_next": False,
    }

    assert payload["data"][0]["khs_id"] == "KHS-2026-0008"
    assert payload["data"][0]["request_date"] == "2026-01-05"
    assert payload["data"][0]["current_stage_code"] == "LP_CIRCULATION"
    assert payload["data"][0]["workflow_status"] == "in_progress"
    assert payload["data"][0]["lp_started_without_mi_gm_approval"] is True

    # Search and filters must be parameterized, not interpolated into SQL.
    data_query, data_params = pool.queries[1]
    assert "ILIKE %s" in data_query
    assert "%borneo%" in data_params
    assert data_params[-2:] == [10, 10]


def test_khs_register_returns_empty_result(make_client):
    pool = RegisterFakePool(rows=[], total=0)

    response = make_client(pool).get("/api/dashboard/khs")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["data"] == []
    assert payload["pagination"]["total_records"] == 0
    assert payload["pagination"]["total_pages"] == 0


def test_khs_register_rejects_invalid_filters(make_client):
    pool = RegisterFakePool()
    client = make_client(pool)

    response = client.get(
        "/api/dashboard/khs?lp_status=unknown"
    )

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_LP_STATUS"
    assert pool.queries == []


def test_khs_register_rejects_invalid_pagination(make_client):
    pool = RegisterFakePool()
    client = make_client(pool)

    response = client.get("/api/dashboard/khs?per_page=101")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_PAGINATION"
    assert pool.queries == []


def test_khs_register_returns_service_unavailable_on_db_error(make_client):
    pool = RegisterFakePool(error=RuntimeError("simulated DB error"))

    response = make_client(pool).get("/api/dashboard/khs")

    assert response.status_code == 503
    assert (
        response.get_json()["code"]
        == "KHS_REGISTER_UNAVAILABLE"
    )

def test_khs_register_attention_filter_excludes_completed_and_includes_next_action(make_client):
    pool = RegisterFakePool(rows=[], total=0)
    response = make_client(pool).get("/api/dashboard/khs?attention=true")
    assert response.status_code == 200
    count_query, _ = pool.queries[0]
    data_query, _ = pool.queries[1]

    for query in (count_query, data_query):
        assert "register.workflow_status <> 'completed'" in query
        assert "NULLIF(BTRIM(COALESCE(register.waiting_for, '')), '') IS NOT NULL" in query
        assert "NULLIF(BTRIM(COALESCE(register.waiting_reason, '')), '') IS NOT NULL" in query
        assert "register.lp_started_without_mi_gm_approval IS TRUE" in query

    assert "LEFT JOIN khs_executors" in data_query

class ExportCursor:
    def __init__(self):
        self.rows = [{
            "khs_id": "=HYPERLINK(\"https://bad.example\")",
            "request_id": "REQ-2026-001",
            "vendor_name": "Vendor A",
        }]
        self.started = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query):
        self.query = query

    def fetchmany(self, size):
        if self.started:
            return []
        self.started = True
        return self.rows


class ExportConnection:
    @contextmanager
    def transaction(self):
        yield self

    def cursor(self, name=None, row_factory=None):
        return ExportCursor()


class ExportPool:
    @contextmanager
    def connection(self):
        yield ExportConnection()


def test_export_csv_streams_and_guards_spreadsheet_formulas(make_client):
    response = make_client(ExportPool()).get("/api/dashboard/export")
    assert response.status_code == 200
    assert response.content_type.startswith("text/csv")
    assert "attachment;" in response.headers["Content-Disposition"]
    content = response.get_data(as_text=True)
    assert content.startswith("\ufeffKHS ID,")
    assert "'=HYPERLINK(" in content
    assert "Vendor A" in content
    assert response.headers["Cache-Control"] == "no-store"


def test_document_upload_rejects_unsupported_file_extensions(make_client):
    client = make_client(FakePool(row=None))
    response = client.post(
        "/api/dashboard/khs/KHS-2026-0001/documents",
        data={"file": (BytesIO(b"not a supported document"), "payload.exe")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "Supported formats" in response.get_json()["message"]



def test_workflow_overview_returns_role_level_mi_and_lp_queues(make_client):
    pool = FakePool(row=(4, 3, 2, 5, 4, 3, 2, 1, 15))

    response = make_client(pool).get("/api/dashboard/workflow/overview")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["success"] is True
    assert payload["data"]["memo_internal"] == [
        {
            "key": "junior_manager",
            "label": "Junior Manager",
            "count": 4,
            "stage_code": "MI_HEAD_APPROVAL",
        },
        {
            "key": "senior_manager",
            "label": "Senior Manager",
            "count": 3,
            "stage_code": "MI_SM_APPROVAL",
        },
        {
            "key": "general_manager",
            "label": "General Manager",
            "count": 2,
            "stage_code": "MI_GM_APPROVAL",
        },
    ]
    assert [item["count"] for item in payload["data"]["lp"]] == [5, 4, 3, 2]
    assert payload["data"]["lp_active_total"] == 15
    assert payload["data"]["lp_unassigned_or_other"] == 1
    assert "Waiting For" in payload["data"]["lp_count_basis"]

    query = pool.connection_object.executed_query
    assert "mi_head_approval_date" in query
    assert "mi_sm_approval_date" in query
    assert "mi_gm_approval_date" in query
    assert "waiting_for" in query
    assert query.count("ELSE 'unassigned_or_other'") == 1
    assert "WITH active_lp AS" in query
    assert "COUNT(*)::int AS active_total" in query
    # Ordered CASE branches ensure one free-text assignment maps to one LP lane.
    assert query.index("LIKE '%junior manager%'") < query.index("LIKE '%senior manager%'")
    assert query.index("LIKE '%senior manager%'") < query.index("LIKE '%general manager%'")
    assert query.index("LIKE '%general manager%'") < query.index("LIKE '%director%'")


def test_workflow_overview_returns_service_unavailable_on_db_error(make_client):
    pool = FakePool(error=RuntimeError("simulated DB error"))

    response = make_client(pool).get("/api/dashboard/workflow/overview")

    assert response.status_code == 503
    assert response.get_json()["code"] == "WORKFLOW_OVERVIEW_UNAVAILABLE"



def test_khs_register_filters_lp_queue_by_waiting_role(make_client):
    pool = RegisterFakePool(rows=[], total=2)

    response = make_client(pool).get("/api/dashboard/khs?waiting_role=director")

    assert response.status_code == 200
    count_query, _ = pool.queries[0]
    data_query, _ = pool.queries[1]
    for query in (count_query, data_query):
        assert "register.lp_circulation_start_date IS NOT NULL" in query
        assert "register.lp_completion_date IS NULL" in query
        assert "CASE" in query
        assert "lower(trim(COALESCE(register.waiting_for, ''))) LIKE '%director%'" in query
    assert pool.queries[0][1] == ["director"]
    assert pool.queries[1][1][-3:] == ["director", 25, 0]


def test_khs_register_rejects_unknown_waiting_role_without_query(make_client):
    pool = RegisterFakePool()
    response = make_client(pool).get("/api/dashboard/khs?waiting_role=vice_president")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_WAITING_ROLE"
    assert pool.queries == []
