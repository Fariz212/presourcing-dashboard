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
    assert b"Contract Monitoring &amp; Tracking" in response.data
    assert b"dashboard.css" in response.data
    assert b"dashboard-premium.css" in response.data
    assert b"dashboard-refresh.css" in response.data
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
    assert b"Contract Monitoring &amp; Tracking" in dashboard_response.data

    css = client.get("/static/css/dashboard.css")
    assert css.status_code == 200
    assert b".kpi-grid" in css.data

    premium_css = client.get("/static/css/dashboard-premium.css")
    assert premium_css.status_code == 200
    assert b".import-guide" in premium_css.data
    assert b".nav-icon" in premium_css.data

    refresh_css = client.get("/static/css/dashboard-refresh.css")
    assert refresh_css.status_code == 200
    assert b".app-shell" in refresh_css.data
    assert b".attention-panel" in refresh_css.data
    assert b"@media (max-width: 680px)" in refresh_css.data

    javascript = client.get("/static/js/dashboard.js")
    assert javascript.status_code == 200
    assert b"/api/dashboard/summary" in javascript.data
    assert b"/api/dashboard/khs" in javascript.data
    assert b"bindImportDropzone" in javascript.data
    assert b"clearRegisterFilters" in javascript.data
    assert b"/api/dashboard/lp-circulation" in javascript.data
    assert b"/api/dashboard/contracts/lifecycle" in javascript.data
    assert b"renderLPTimeline" in javascript.data
    assert b"renderContractDetail" in javascript.data
    assert b"lp_contract_team_completion_date" in javascript.data
    assert b"lp_junior_manager_approval_date" in javascript.data
    assert b"lp_senior_manager_approval_date" in javascript.data
    assert b"lp_gm_scm_approval_date" in javascript.data
    assert b"lp_circulation_start_date" in javascript.data
    assert b"lp_completion_date" in javascript.data

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
        'data-page="lp"',
        'data-page="contracts"',
        'data-page="workflow"',
        'data-page="imports"',
        'data-page="activity"',
    ):
        assert module in body
    assert "Contract Monitoring &amp; Tracking" in body
    assert "LP Circulation" in body
    assert "Contract Lifecycle" in body
    assert "Approval Timeline" in body
    assert "Contract Lifecycle Watch" in body
    assert "CONTRACT STATUS" in body
    assert "RENEWAL ALERT" in body
    assert "Upcoming contract" in body
    assert 'id="page-lp"' in body
    assert 'id="page-contracts"' in body
    assert "Approval Pipeline" in body
    assert body.index('class="attention-panel"') < body.index('class="approval-command"')
    assert body.index('id="qualityAlert"') < body.index('class="approval-command"')
    assert "Memo Internal" in body
    assert "LP Circulation" in body
    assert "Junior Manager" in body
    assert "Senior Manager" in body
    assert "General Manager" in body
    assert "Director" in body
    assert 'data-attention-only="true"' in body
    assert 'data-queue-role="director"' in body
    assert "New Request" in body
    assert "Add KHS" in body
    assert "Export KHS CSV" in body
    assert "Download current Excel" in body
    assert "Fully Injected" in body
    assert "REQUEST SUBJECT / VENDOR" in body
    assert "VENDOR PORTFOLIO" in body
    assert "Evidence Documents" in body
    assert 'id="documentUploadForm"' in body




def test_request_vendor_portfolio_is_compact_and_expandable(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "dashboard-vendor-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    client = flask_app.test_client()

    dashboard = client.get("/dashboard")
    assert dashboard.status_code == 200
    assert b"VENDOR PORTFOLIO" in dashboard.data

    javascript = client.get("/static/js/dashboard.js")
    assert javascript.status_code == 200
    assert b"renderVendorPortfolio" in javascript.data
    assert b"vendor-count-badge" in javascript.data
    assert b"vendor-details" in javascript.data

    css = client.get("/static/css/dashboard-premium.css")
    assert css.status_code == 200
    assert b".vendor-count-badge" in css.data
    assert b".vendor-detail-list" in css.data
    assert b".attention-panel td:nth-child(4)" in css.data
    assert b".page-heading {\n  align-items: flex-start;" in css.data
    assert b"top: 0;\n  z-index: 2;" in css.data
    assert b"vertical-align: middle;" in css.data
    assert b".lp-timeline-item.current" in css.data
    assert b".contract-lifecycle-summary" in css.data
    assert b".contract-watch-grid" in css.data
    assert b".lp-stage-summary" in css.data
    assert b".lp-timeline" in css.data
    assert b".contract-lifecycle-summary" in css.data
