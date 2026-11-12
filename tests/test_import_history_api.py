from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask

from app.routes.imports import imports_bp


class FakeResult:
    def __init__(self, one=None, many=None):
        self.one = one
        self.many = many or []

    def fetchone(self):
        return self.one

    def fetchall(self):
        return self.many


class FakeConnection:
    def __init__(self, pool):
        self.pool = pool

    def execute(self, query, params=None):
        self.pool.queries.append((query, params))

        if "COUNT(*)" in query:
            return FakeResult(one=(self.pool.total,))

        return FakeResult(many=self.pool.rows)


class FakePool:
    def __init__(self, rows=None, total=0, error=None):
        self.rows = rows or []
        self.total = total
        self.error = error
        self.queries = []

    @contextmanager
    def connection(self):
        if self.error:
            raise self.error
        yield FakeConnection(self)


def make_client(monkeypatch, pool):
    monkeypatch.setattr(
        "app.routes.imports.get_db_pool",
        lambda: pool,
    )

    app = Flask(__name__)
    app.register_blueprint(imports_bp, url_prefix="/api/imports")
    app.config["TESTING"] = True
    return app.test_client()


def test_import_history_returns_paginated_batches(monkeypatch):
    uploaded_at = datetime(2026, 11, 11, 8, 30, tzinfo=timezone.utc)

    row = (
        1,
        "KHS_Creation_Monitoring_Template_v2_2.xlsx",
        "IMPORTED",
        73,
        66,
        7,
        0,
        9,
        0,
        0,
        64,
        0,
        0,
        uploaded_at,
        uploaded_at,
    )

    pool = FakePool(rows=[row], total=1)
    client = make_client(monkeypatch, pool)

    response = client.get("/api/imports/history?page=1&per_page=10")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["pagination"]["total_records"] == 1
    assert payload["data"][0]["id"] == 1
    assert payload["data"][0]["status"] == "IMPORTED"
    assert payload["data"][0]["total_rows"] == 73
    assert payload["data"][0]["uploaded_at"] == uploaded_at.isoformat()
    assert payload["data"][0]["inserted_items"] == 64


def test_import_history_returns_empty_list(monkeypatch):
    pool = FakePool(total=0)
    client = make_client(monkeypatch, pool)

    response = client.get("/api/imports/history")

    assert response.status_code == 200
    payload = response.get_json()

    assert payload["success"] is True
    assert payload["data"] == []
    assert payload["pagination"]["total_pages"] == 0


def test_import_history_rejects_invalid_pagination(monkeypatch):
    pool = FakePool()
    client = make_client(monkeypatch, pool)

    response = client.get("/api/imports/history?per_page=101")

    assert response.status_code == 400
    assert response.get_json()["code"] == "INVALID_PAGINATION"
    assert pool.queries == []


def test_import_history_handles_database_error(monkeypatch):
    pool = FakePool(error=RuntimeError("simulated database error"))
    client = make_client(monkeypatch, pool)

    response = client.get("/api/imports/history")

    assert response.status_code == 503
    assert (
        response.get_json()["code"]
        == "IMPORT_HISTORY_UNAVAILABLE"
    )
