from app import create_app


class DummyPool:
    def close(self):
        pass


def test_root_serves_dashboard_and_static_assets(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )

    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "dashboard-ui-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })

    client = flask_app.test_client()

    response = client.get("/", headers={"Accept": "text/html"})

    assert response.status_code == 200
    assert response.content_type.startswith("text/html")
    assert b"KHS Creation Overview" in response.data
    assert b"dashboard.css" in response.data
    assert b"dashboard.js" in response.data

    # API clients must retain the legacy JSON root response.
    json_response = client.get(
        "/",
        headers={"Accept": "application/json"},
    )
    assert json_response.status_code == 200
    assert json_response.get_json()["status"] == "running"

    # The dashboard also has a dedicated, direct URL.
    dashboard_response = client.get("/dashboard")
    assert dashboard_response.status_code == 200
    assert b"KHS Creation Overview" in dashboard_response.data

    css = client.get("/static/css/dashboard.css")
    assert css.status_code == 200
    assert b".kpi-grid" in css.data

    javascript = client.get("/static/js/dashboard.js")
    assert javascript.status_code == 200
    assert b"/api/dashboard/summary" in javascript.data
    assert b"/api/dashboard/khs" in javascript.data

def test_dashboard_contains_separate_operational_modules(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "dashboard-ui-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    response = flask_app.test_client().get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    for module in (
        'data-page="overview"',
        'data-page="requests"',
        'data-page="register"',
        'data-page="workflow"',
        'data-page="imports"',
        'data-page="activity"',
    ):
        assert module in body
    assert "KHS Creation Overview" in body
    assert "New Request" in body
    assert "Add KHS" in body
    assert "Export KHS CSV" in body
    assert "Fully Injected" in body
    assert "REQUEST SUBJECT / VENDOR" in body
    assert "Evidence Documents" in body
    assert 'id="documentUploadForm"' in body

