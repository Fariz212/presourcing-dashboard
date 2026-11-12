from contextlib import contextmanager

from flask import Flask

from app.routes.dashboard import dashboard_bp


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, pool):
        self.pool = pool

    def execute(self, query):
        self.pool.query = query
        if self.pool.error:
            raise self.pool.error
        return FakeResult(self.pool.row)


class FakePool:
    def __init__(self, row=None, error=None):
        self.row = row
        self.error = error
        self.query = None

    @contextmanager
    def connection(self):
        yield FakeConnection(self)


def make_client(monkeypatch, pool):
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


def test_dashboard_filters_returns_master_options(monkeypatch):
    executors = [
        {
            "executor_code": "ALW",
            "display_name": "Adila Darmawan",
        },
        {
            "executor_code": "FZK",
            "display_name": "Farizky Ramadhan",
        },
    ]
    subtypes = ["Kontrak Baru", "Renewal"]
    waiting_for = ["Legal", "Vendor"]
    stages = [
        {
            "stage_code": "REQUEST_RECEIVED",
            "stage_name": "Request Received",
            "sequence_number": 1,
        },
        {
            "stage_code": "LP_CIRCULATION",
            "stage_name": "LP Circulation",
            "sequence_number": 11,
        },
    ]

    pool = FakePool(
        row=(executors, subtypes, waiting_for, stages),
    )
    client = make_client(monkeypatch, pool)

    response = client.get("/api/dashboard/filters")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["data"]["executors"] == executors
    assert payload["data"]["subtypes"] == subtypes
    assert payload["data"]["waiting_for"] == waiting_for
    assert payload["data"]["stages"] == stages
    assert "khs_stage_config" in pool.query
    assert "khs_executors" in pool.query


def test_dashboard_filters_handles_empty_master_options(monkeypatch):
    pool = FakePool(row=([], [], [], []))
    client = make_client(monkeypatch, pool)

    response = client.get("/api/dashboard/filters")

    assert response.status_code == 200
    assert response.get_json()["data"] == {
        "executors": [],
        "subtypes": [],
        "waiting_for": [],
        "stages": [],
    }


def test_dashboard_filters_returns_service_unavailable_on_db_error(monkeypatch):
    pool = FakePool(error=RuntimeError("simulated database failure"))
    client = make_client(monkeypatch, pool)

    response = client.get("/api/dashboard/filters")

    assert response.status_code == 503
    assert (
        response.get_json()["code"]
        == "DASHBOARD_FILTERS_UNAVAILABLE"
    )
