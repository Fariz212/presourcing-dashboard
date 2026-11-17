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
    assert b"dashboard-studio.css" in response.data
    assert b"dashboard.css" not in response.data
    assert b"dashboard-premium.css" not in response.data
    assert b"dashboard-refresh.css" not in response.data
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
    studio_css = client.get("/static/css/dashboard-studio.css")
    assert studio_css.status_code == 200
    assert b".kpi-grid" in studio_css.data
    assert b".vendor-count-badge" in studio_css.data
    assert b"table-layout: fixed" in studio_css.data
    assert b"--canvas: #f5f3ed" in studio_css.data
    assert b".lp-quality-summary" in studio_css.data
    assert b".filter-more-fields" in studio_css.data
    assert b"@media (max-width: 920px)" in studio_css.data


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
    assert b"languageToggle" in response.data
    assert b"I18N_ID" in javascript.data
    assert b"initLanguageSwitcher" in javascript.data
    assert b"localStorage.setItem(\"khs-dashboard-language\"" in javascript.data

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
    client = flask_app.test_client()
    response = client.get("/dashboard")
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
    assert 'id="quickAddKhs"' not in body
    assert 'id="refreshButton"' in body
    for duplicate_refresh in (
        'id="overviewRefresh"', 'id="workflowRefresh"',
        'id="refreshOperationsButton"', 'id="contractRefresh"',
        'id="activityRefresh"', 'id="refreshHistoryButton"',
    ):
        assert duplicate_refresh not in body
    assert 'id="workflowStageDisclosure"' in body
    assert 'class="operations-summary-table"' in body
    assert 'id="workbench-nav"' in body
    assert "Priority action queue" in body
    assert "REQUEST / KHS" in body
    attention_js = client.get("/static/js/dashboard.js")
    assert attention_js.status_code == 200
    assert b'data-label="REQUEST / KHS"' in attention_js.data
    assert b'aria-label="Open KHS ' in attention_js.data
    assert "LP Circulation" in body
    assert "Contract Lifecycle" in body
    assert "Approval journey" in body
    assert "Contract Lifecycle Watch" in body
    assert "CONTRACT STATUS" in body
    assert "RENEWAL ALERT" in body
    assert "Upcoming contract" in body
    assert 'id="page-lp"' in body
    assert 'id="page-contracts"' in body
    assert "Approval Pipeline" in body
    assert body.index('class="panel attention-panel"') < body.index('class="approval-command"')
    assert 'id="qualityAlert"' not in body
    assert "Memo Internal" in body
    assert "LP Circulation" in body
    assert "Junior Manager" in body
    assert "Senior Manager" in body
    assert "General Manager" in body
    assert "Director" in body
    assert 'data-attention-only="true"' in body
    assert 'data-lp-queue-stage="director"' in body
    assert 'data-lp-queue-stage="contract_team"' in body
    assert "New Request" in body
    assert "Add KHS" in body
    assert "Export KHS CSV" in body
    assert "Download current Excel" in body
    assert "Fully Injected" in body
    assert "REQUEST / VENDOR" in body
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


def test_khs_register_uses_progressive_filter_disclosure(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "dashboard-filter-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    response = flask_app.test_client().get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'class="filter-more"' in body
    assert 'id="searchInput"' in body
    for control in ("statusFilter", "executorFilter", "subtypeFilter", "waitingFilter", "stageFilter"):
        assert f'id="{control}"' in body


def test_lp_summary_separates_live_stages_from_quality_overlays(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "dashboard-lp-summary-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    response = flask_app.test_client().get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'class="lp-stage-main"' in body
    assert 'class="lp-quality-summary"' in body
    assert 'data-lp-stage="prerequisite_exception"' in body
    assert 'data-lp-stage="legacy_unverified"' in body
    assert 'data-lp-stage="legacy_incomplete"' in body



def test_khs_detail_and_form_prioritize_lp_workflow(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "dashboard-lp-first-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    client = flask_app.test_client()

    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'id="lpCurrentStage"' in body
    assert 'id="lpStageAge"' in body
    assert 'id="lpUpcomingStage"' in body
    assert 'role="list" aria-label="LP approval milestones"' in body
    assert 'id="detailGrid" class="detail-groups"' in body

    javascript = client.get("/static/js/dashboard.js")
    assert javascript.status_code == 200
    script = javascript.data
    assert b"renderGroupedKhsFields" in script
    assert b"itemFieldGroups" in script
    assert b"record.lp_stage_age_days" in script
    assert b"record.lp_timeline_gaps" in script
    for field in (
        b"lp_circulation_start_date",
        b"lp_contract_team_completion_date",
        b"lp_junior_manager_approval_date",
        b"lp_senior_manager_approval_date",
        b"lp_gm_scm_approval_date",
        b"lp_completion_date",
    ):
        assert field in script

    stylesheet = client.get("/static/css/dashboard-studio.css")
    assert stylesheet.status_code == 200
    for selector in (
        b".lp-stage-focus",
        b".lp-form-grid",
        b".form-section-lp-circulation",
        b".detail-groups",
        b".lp-timeline-item.gap",
    ):
        assert selector in stylesheet.data



def test_lean_workspace_navigation_responsive_tables_and_activity_filters(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "lean-workspace-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    client = flask_app.test_client()

    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert 'id="mobileNavToggle"' in body
    assert 'id="primarySideNav"' in body
    assert 'id="dataSideNav"' in body
    assert 'id="activeRegisterFilters"' in body
    assert 'register-table-wrap' in body
    assert 'id="activitySearch"' in body
    assert 'id="activityEntityFilter"' in body
    assert 'id="workflowStageSummary"' in body
    assert 'id="workflowEmptyToggle"' in body
    assert 'id="attentionMobileHint"' in body
    assert 'id="quickAddKhs"' not in body
    assert 'id="qualityAlert"' not in body
    assert 'class="overview-grid"' not in body

    javascript = client.get("/static/js/dashboard.js")
    assert javascript.status_code == 200
    script = javascript.data
    for marker in (
        b"function observeResponsiveTables()",
        b"function renderActiveRegisterFilters()",
        b"function currentStageLabel(record)",
        b"function currentStageAgeLabel(record)",
        b"record.current_stage_age_days",
        b"data-workflow-stage",
        b"function renderWorkflowCards()",
        b"state.showEmptyWorkflowStages",
        b"Number(row.total) > 0",
        b"state.activityQuery",
        b"state.saving",
        b"Saving",
        b"syncRefreshVisibility(page)",
    ):
        assert marker in script

    stylesheet = client.get("/static/css/dashboard-studio.css")
    assert stylesheet.status_code == 200
    for selector in (
        b".mobile-nav-toggle",
        b".sidebar.nav-open .side-nav",
        b".table-wrap tbody tr",
        b".workflow-workbench-toolbar",
        b".workflow-empty-toggle",
        b".attention-mobile-hint",
        b".filter-chip",
        b".form-error",
    ):
        assert selector in stylesheet.data

    unsupported_entity = client.get("/api/dashboard/activity?entity_type=IMPORT")
    assert unsupported_entity.status_code == 400
    long_search = client.get("/api/dashboard/activity?q=" + ("x" * 101))
    assert long_search.status_code == 400


def test_lean_work_queue_uses_saved_views_and_separates_action_roles(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "lean-work-queue-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    client = flask_app.test_client()

    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    assert 'id="page-register" data-title="Work Queue"' in body
    for view in ("all", "active", "attention", "lp", "exceptions", "unassigned"):
        assert f'data-work-queue-view="{view}"' in body
    assert 'class="nav-link nav-link-sub" href="#lp" data-page="lp"' in body
    assert "ACTION OWNER" in body
    assert "WAITING ON" in body
    assert "NEXT ACTION / MILESTONE" in body
    assert "LP / INJECTION" in body
    assert 'id="lpWorkStageFilter"' in body

    javascript = client.get("/static/js/dashboard.js")
    assert javascript.status_code == 200
    script = javascript.data.decode("utf-8")
    assert 'p.set("work_view", state.workView || "active")' in script
    assert 'p.set("lp_stage", state.workLpStageFilter)' in script
    assert 'if (page === "lp")' in script
    assert 'r.action_owner || ""' in script
    assert 'r.waiting_for' in script
    assert 'r.guided_progress && r.guided_progress.label' in script
    assert 'state.workView = "active";' in script
    assert 'state.workLpStageFilter = null;' in script

    stylesheet = client.get("/static/css/dashboard-studio.css")
    assert stylesheet.status_code == 200
    assert b".work-queue-views" in stylesheet.data
    assert b".nav-link-sub" in stylesheet.data


def test_overview_prioritizes_actions_without_duplicate_graph_panels(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "dashboard-overview-lean-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    client = flask_app.test_client()
    response = client.get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    assert "Priority action queue" in body
    assert "<th>ACTION OWNER</th>" in body
    assert "<th>WAITING ON / CONTEXT</th>" in body
    assert "Approval Pipeline" in body
    assert "Contract Lifecycle Watch" in body
    assert 'class="overview-grid"' not in body
    assert 'id="qualityAlert"' not in body
    assert body.index('class="panel attention-panel"') < body.index('class="approval-command"')
    assert body.index('class="approval-command"') < body.index('class="contract-watch"')


def test_khs_workbench_uses_progressive_single_panel_navigation(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.init_db_pool",
        lambda _app: DummyPool(),
    )
    flask_app = create_app({
        "TESTING": True,
        "SECRET_KEY": "workbench-progressive-test-secret",
        "DATABASE_URL": "postgresql://test:test@localhost/test",
        "UPLOAD_DIR": tmp_path / "uploads",
    })
    response = flask_app.test_client().get("/dashboard")
    assert response.status_code == 200
    body = response.data.decode("utf-8")

    assert 'id="workbench-nav"' in body
    assert 'data-workbench-panel aria-labelledby="workSummaryTitle"' in body
    for panel_id in (
        "processDurationSection", "lpTimelineSection", "contractDetailSection",
        "detailGrid", "followUpSection", "documentSection",
    ):
        assert f'id="{panel_id}"' in body
        panel_tag = next(
            line for line in body.splitlines() if f'id="{panel_id}"' in line
        )
        assert "data-workbench-panel" in panel_tag
        assert "hidden" in panel_tag
    assert 'id="closureSummary" class="closure-summary" hidden' in body

    script = flask_app.test_client().get("/static/js/dashboard.js").data.decode("utf-8")
    assert "function setWorkbenchPanel(panelId)" in script
    assert 'setWorkbenchPanel("workSummarySection")' in script
    assert 'setWorkbenchPanel("followUpSection")' in script
    assert "target.scrollIntoView" not in script
