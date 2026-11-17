from datetime import date

from app.routes.dashboard import (
    _guided_progress_date_error,
    _guided_progress_definition,
    _operations_stage_query,
    _sla_status_for_age,
)


def test_guided_progress_maps_the_next_mi_milestone_only():
    record = {
        "workflow_stage_code": "MI_SM_APPROVAL",
        "current_stage_code": "MI_SM_APPROVAL",
        "mi_head_approval_date": date(2026, 11, 10),
        "mi_sm_approval_date": None,
        "current_stage_started_on": date(2026, 11, 10),
    }
    result = _guided_progress_definition(record)
    assert result["field"] == "mi_sm_approval_date"
    assert result["label"] == "MI Senior Manager approval recorded"
    assert result["previous_milestone"] == "mi_head_approval_date"


def test_guided_progress_maps_lp_and_injection_steps_without_skipping():
    lp_record = {
        "workflow_stage_code": "LP_CIRCULATION",
        "current_stage_code": "LP_CIRCULATION",
        "lp_stage_key": "senior_manager",
        "lp_junior_manager_approval_date": date(2026, 11, 10),
        "lp_senior_manager_approval_date": None,
        "current_stage_started_on": date(2026, 11, 10),
    }
    assert _guided_progress_definition(lp_record)["field"] == "lp_senior_manager_approval_date"

    injection_record = {
        "workflow_stage_code": "KHS_INJECTION",
        "current_stage_code": "KHS_INJECTION",
        "lp_completion_date": date(2026, 11, 10),
        "khs_inject_start_date": None,
        "khs_inject_completion_date": None,
    }
    assert _guided_progress_definition(injection_record)["field"] == "khs_inject_start_date"
    injection_record["khs_inject_start_date"] = date(2026, 11, 12)
    assert _guided_progress_definition(injection_record)["field"] == "khs_inject_completion_date"


def test_guided_progress_is_not_available_for_closed_or_completed_records():
    assert _guided_progress_definition({
        "workflow_stage_code": "COMPLETED",
        "current_stage_code": "COMPLETED",
        "khs_inject_completion_date": date(2026, 11, 10),
    }) is None
    assert _guided_progress_definition({
        "workflow_stage_code": "NEGOTIATION",
        "current_stage_code": "NEGOTIATION",
        "negotiation_date": date(2026, 11, 10),
    }) is None


def test_guided_progress_rejects_chronology_and_lp_gate_violations():
    record = {
        "request_date": date(2026, 11, 10),
        "dispatch_date": None,
    }
    assert _guided_progress_date_error(record, "dispatch_date", date(2026, 11, 9))[0] == "MILESTONE_BEFORE_PREVIOUS"

    lp_record = {
        "mi_gm_approval_date": None,
        "lp_circulation_start_date": None,
        "lp_contract_team_completion_date": None,
        "lp_junior_manager_approval_date": None,
        "lp_senior_manager_approval_date": None,
        "lp_gm_scm_approval_date": None,
        "lp_completion_date": None,
    }
    assert _guided_progress_date_error(lp_record, "lp_circulation_start_date", date(2026, 11, 11))[0] == "MI_GM_REQUIRED"


def test_sla_status_does_not_invent_due_dates_when_policy_is_missing():
    assert _sla_status_for_age(45) == "not_configured"
    assert _sla_status_for_age(None, target_days=10) == "age_unavailable"


def test_sla_status_uses_configured_warning_target_and_escalation_thresholds():
    assert _sla_status_for_age(2, warning_after_days=3, target_days=5, escalation_after_days=8) == "on_track"
    assert _sla_status_for_age(3, warning_after_days=3, target_days=5, escalation_after_days=8) == "due_soon"
    assert _sla_status_for_age(5, warning_after_days=3, target_days=5, escalation_after_days=8) == "overdue"
    assert _sla_status_for_age(8, warning_after_days=3, target_days=5, escalation_after_days=8) == "escalation_due"


def test_operations_aging_query_uses_active_milestone_ages_and_descriptive_buckets():
    query = _operations_stage_query(date(2026, 11, 17))
    assert "register.process_status = 'ACTIVE'" in query
    assert "register.current_stage_started_on" in query
    assert "percentile_disc(0.5)" in query
    assert "percentile_disc(0.9)" in query
    assert "BETWEEN 0 AND 7" in query
    assert "BETWEEN 8 AND 14" in query
    assert "BETWEEN 15 AND 30" in query
    assert "wip.stage_age_days >= COALESCE(policy.target_days, stage.default_sla_days)" in query
    assert "stage.stage_code NOT IN ('COMPLETED', 'NOT_PROCEEDED')" in query
