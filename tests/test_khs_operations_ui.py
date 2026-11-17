from app import create_app


class DummyPool:
    def close(self):
        pass


def test_dashboard_exposes_operations_analytics_and_workbench_controls(monkeypatch, tmp_path):
    monkeypatch.setattr("app.init_db_pool", lambda _app: DummyPool())
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "khs-operations-ui-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    client = app.test_client()
    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    for marker in (
        'id="operationsAnalytics"',
        'id="operationsStageBody"',
        'id="operationsFollowUpBody"',
        'id="workflowStageDisclosure"',
        "operations-summary-table",
        'data-workbench-panel',
        'id="workbench-nav"',
        'id="progressDialog"',
        'id="progressForm"',
        'id="updateProgressButton"',
        'id="followUpSection"',
        'id="followUpForm"',
    ):
        assert marker in body
    assert body.count('id="workbench-nav"') == 1

    script = client.get("/static/js/dashboard.js")
    assert script.status_code == 200
    for marker in (
        b"/api/dashboard/operations/overview",
        b"/api/dashboard/operations/sla-overview",
        b"/api/dashboard/operations/follow-ups",
        b"/progress",
        b"/follow-ups",
        b"renderOperationsAnalytics",
        b"submitGuidedProgress",
        b"submitWorkbenchFollowUp",
        b"updateFollowUpStatus",
        b"data-operations-age-band",
        b"workflowAgeBandFilter",
        b"age_band",
        b"bottleneck_rank",
        b"stage-detail-disclosure",
        b"setWorkbenchPanel",
        b"data-workbench-panel",
    ):
        assert marker in script.data

    stylesheet = client.get("/static/css/dashboard-studio.css")
    assert stylesheet.status_code == 200
    for marker in (
        b".operations-analytics",
        b".operations-kpi-grid",
        b".workbench-nav",
        b".follow-up-form",
        b".status-sla-escalation_due",
        b".bottleneck-rank",
        b".stage-detail-disclosure",
        b".workflow-stage-disclosure",
        b"[data-workbench-panel][hidden]",
    ):
        assert marker in stylesheet.data
