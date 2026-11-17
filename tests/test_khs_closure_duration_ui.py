from app import create_app


class DummyPool:
    def close(self):
        pass


def test_dashboard_exposes_khs_closure_and_process_duration_controls(monkeypatch, tmp_path):
    monkeypatch.setattr("app.init_db_pool", lambda _app: DummyPool())
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "khs-closure-duration-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    client = app.test_client()

    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    for marker in (
        'id="notProceededKhs"',
        'id="processStatusFilter"',
        'id="closureDialog"',
        'id="reopenDialog"',
        'id="closeKhsButton"',
        'id="reopenKhsButton"',
        'id="processDurationHistory"',
        'id="totalProcessingDays"',
        'id="lpProcessingDays"',
    ):
        assert marker in body

    script = client.get("/static/js/dashboard.js")
    assert script.status_code == 200
    for marker in (
        b"/close",
        b"/reopen",
        b"renderProcessDurationHistory",
        b"total_processing_duration_days",
        b"NOT_PROCEEDED",
    ):
        assert marker in script.data

    stylesheet = client.get("/static/css/dashboard-studio.css")
    assert stylesheet.status_code == 200
    for marker in (
        b".process-duration-section",
        b".process-duration-row",
        b".closure-summary",
        b".danger-button",
    ):
        assert marker in stylesheet.data
