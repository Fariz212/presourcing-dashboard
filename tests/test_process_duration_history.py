from datetime import date

from app.routes.dashboard import _process_duration_history, _register_enriched


def test_completed_process_duration_history_uses_recorded_milestones():
    row = {
        "process_status": "ACTIVE",
        "workflow_stage_code": "COMPLETED",
        "current_stage_code": "COMPLETED",
        "lp_stage_key": "completed",
        "request_date": date(2026, 1, 1),
        "dispatch_date": date(2026, 1, 4),
        "boq_confirmation_date": date(2026, 1, 8),
        "negotiation_date": date(2026, 1, 15),
        "final_negotiation_date": date(2026, 1, 20),
        "mi_head_approval_date": date(2026, 1, 22),
        "mi_sm_approval_date": date(2026, 1, 24),
        "mi_gm_approval_date": date(2026, 1, 27),
        "legal_submission_date": date(2026, 1, 30),
        "lp_circulation_start_date": date(2026, 2, 2),
        "lp_contract_team_completion_date": date(2026, 2, 4),
        "lp_junior_manager_approval_date": date(2026, 2, 6),
        "lp_senior_manager_approval_date": date(2026, 2, 8),
        "lp_gm_scm_approval_date": date(2026, 2, 10),
        "lp_completion_date": date(2026, 2, 12),
        "khs_inject_start_date": date(2026, 2, 14),
        "khs_inject_completion_date": date(2026, 2, 20),
        "closure_date": None,
    }
    result = _process_duration_history(row, today=date(2026, 3, 1))
    by_code = {stage["stage_code"]: stage for stage in result["process_duration_history"]}

    assert by_code["DISPATCH"]["duration_days"] == 3
    assert by_code["LP_CONTRACT_TEAM"]["duration_days"] == 2
    assert by_code["KHS_INJECTION"]["duration_days"] == 6
    assert result["total_processing_duration_days"] == 50
    assert result["total_processing_status"] == "completed"
    assert result["lp_circulation_duration_days"] == 10


def test_open_current_stage_is_ongoing_but_missing_history_is_not_estimated():
    row = {
        "process_status": "ACTIVE",
        "workflow_stage_code": "NEGOTIATION",
        "current_stage_code": "NEGOTIATION",
        "lp_stage_key": "not_started",
        "request_date": date(2026, 1, 1),
        "dispatch_date": date(2026, 1, 4),
        "boq_confirmation_date": date(2026, 1, 8),
        "negotiation_date": None,
        "final_negotiation_date": None,
    }
    result = _process_duration_history(row, today=date(2026, 1, 18))
    by_code = {stage["stage_code"]: stage for stage in result["process_duration_history"]}

    assert by_code["NEGOTIATION"]["status"] == "in_progress"
    assert by_code["NEGOTIATION"]["duration_days"] == 10
    assert result["total_processing_duration_days"] == 17
    assert by_code["DISPATCH"]["status"] == "completed"


def test_not_proceeded_stops_current_stage_at_closure_date_and_preserves_prior_history():
    row = {
        "process_status": "NOT_PROCEEDED",
        "workflow_stage_code": "FINAL_NEGOTIATION",
        "current_stage_code": "NOT_PROCEEDED",
        "lp_stage_key": "not_started",
        "request_date": date(2026, 1, 1),
        "dispatch_date": date(2026, 1, 4),
        "boq_confirmation_date": date(2026, 1, 8),
        "negotiation_date": date(2026, 1, 10),
        "closure_date": date(2026, 1, 18),
    }
    result = _process_duration_history(row, today=date(2026, 2, 1))
    by_code = {stage["stage_code"]: stage for stage in result["process_duration_history"]}

    assert by_code["NEGOTIATION"]["status"] == "completed"
    assert by_code["FINAL_NEGOTIATION"]["status"] == "stopped"
    assert by_code["FINAL_NEGOTIATION"]["end_date"] == "2026-01-18"
    assert by_code["FINAL_NEGOTIATION"]["duration_days"] == 8
    assert result["total_processing_duration_days"] == 17
    assert result["total_processing_status"] == "stopped"


def test_register_enrichment_stops_current_stage_age_on_closure_date():
    result = _register_enriched({
        "process_status": "NOT_PROCEEDED",
        "workflow_status": "not_proceeded",
        "workflow_stage_code": "NEGOTIATION",
        "current_stage_code": "NOT_PROCEEDED",
        "current_stage_started_on": date(2026, 1, 10),
        "closure_date": date(2026, 1, 18),
        "lp_circulation_start_date": None,
        "lp_contract_team_completion_date": None,
        "lp_junior_manager_approval_date": None,
        "lp_senior_manager_approval_date": None,
        "lp_gm_scm_approval_date": None,
        "lp_completion_date": None,
        "mi_gm_approval_date": None,
        "legacy_overall_status": None,
        "khs_inject_completion_date": None,
        "contract_start_date": None,
        "contract_end_date": None,
    }, today=date(2026, 2, 1))

    assert result["current_stage_age_days"] == 8
    assert result["current_stage_age_status"] == "stopped"
    assert result["current_stage_started_on"] == "2026-01-10"
