from datetime import date

from app.routes.dashboard import (
    _guided_progress_date_error,
    _guided_progress_definition,
    _operations_stage_query,
    _operations_stage_totals,
    _rank_operations_stages,
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


def test_guided_progress_advances_from_mi_gm_to_legal_submission():
    record = {
        "workflow_stage_code": "LEGAL_SUBMISSION",
        "current_stage_code": "LEGAL_SUBMISSION",
        "mi_sm_approval_date": date(2026, 11, 10),
        "mi_gm_approval_date": date(2026, 11, 11),
        "legal_submission_date": None,
        "current_stage_started_on": date(2026, 11, 11),
    }
    result = _guided_progress_definition(record)
    assert result["field"] == "legal_submission_date"
    assert result["previous_milestone"] == "mi_gm_approval_date"


def test_guided_progress_rejects_a_milestone_that_would_invalidate_a_later_date():
    record = {
        "mi_sm_approval_date": date(2026, 11, 10),
        "mi_gm_approval_date": None,
        "legal_submission_date": date(2026, 11, 12),
    }
    error = _guided_progress_date_error(
        record, "mi_gm_approval_date", date(2026, 11, 13)
    )
    assert error[0] == "MILESTONE_AFTER_NEXT"


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



def test_operations_totals_reconcile_with_stage_age_buckets_including_future_dates():
    # Per-stage age_unavailable includes both missing and future opening dates.
    totals = _operations_stage_totals([
        {
            "wip_count": 3,
            "age_over_30": 2,
            "age_unavailable": 1,
            "overdue_count": 0,
            "escalation_count": 0,
            "target_days": None,
        },
        {
            "wip_count": 4,
            "age_over_30": 1,
            "age_unavailable": 2,
            "overdue_count": 3,
            "escalation_count": 1,
            "target_days": 10,
        },
    ])
    assert totals == {
        "active_wip": 7,
        "older_than_30_days": 3,
        "stage_age_unavailable": 3,
        "sla_overdue_records": 3,
        "escalation_records": 1,
        "sla_not_configured_stages": 1,
    }


def test_bottleneck_ranking_uses_wip_then_p90_then_oldest_and_leaves_empty_stages_unranked():
    rows = [
        {"stage_code": "LOW", "wip_count": 2, "p90_age_days": 40, "oldest_age_days": 50, "sequence_number": 1},
        {"stage_code": "HIGH", "wip_count": 5, "p90_age_days": 10, "oldest_age_days": 20, "sequence_number": 2},
        {"stage_code": "P90", "wip_count": 2, "p90_age_days": 45, "oldest_age_days": 46, "sequence_number": 3},
        {"stage_code": "OLDEST", "wip_count": 2, "p90_age_days": 45, "oldest_age_days": 60, "sequence_number": 4},
        {"stage_code": "EMPTY", "wip_count": 0, "p90_age_days": None, "oldest_age_days": None, "sequence_number": 5},
    ]
    ranked = _rank_operations_stages(rows)
    rank_by_stage = {row["stage_code"]: row["bottleneck_rank"] for row in ranked}
    assert rank_by_stage == {
        "LOW": 4,
        "HIGH": 1,
        "P90": 3,
        "OLDEST": 2,
        "EMPTY": None,
    }
