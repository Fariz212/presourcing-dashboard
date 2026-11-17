import calendar
import csv
from datetime import date, datetime, timedelta
import hashlib
from io import StringIO
import mimetypes
from pathlib import Path
import re
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, current_app, jsonify, request, send_file, stream_with_context
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from werkzeug.utils import secure_filename

from app.db import get_db_pool


dashboard_bp = Blueprint("dashboard", __name__)


SUMMARY_QUERY = """
SELECT
    (SELECT COUNT(*) FROM khs_requests) AS total_requests,
    COUNT(*) AS total_khs,
    COUNT(*) FILTER (WHERE process_status = 'ACTIVE' AND lp_completion_date IS NOT NULL) AS lp_completed,
    COUNT(*) FILTER (
        WHERE process_status = 'ACTIVE'
          AND lp_completion_date IS NULL
          AND (
                lp_circulation_start_date IS NOT NULL
             OR lp_contract_team_completion_date IS NOT NULL
             OR lp_junior_manager_approval_date IS NOT NULL
             OR lp_senior_manager_approval_date IS NOT NULL
             OR lp_gm_scm_approval_date IS NOT NULL
          )
    ) AS lp_in_progress,
    COUNT(*) FILTER (
        WHERE process_status = 'ACTIVE'
          AND lp_circulation_start_date IS NULL
          AND lp_contract_team_completion_date IS NULL
          AND lp_junior_manager_approval_date IS NULL
          AND lp_senior_manager_approval_date IS NULL
          AND lp_gm_scm_approval_date IS NULL
          AND lp_completion_date IS NULL
    ) AS lp_not_started,
    COUNT(*) FILTER (WHERE process_status = 'ACTIVE' AND khs_inject_completion_date IS NOT NULL) AS inject_completed,
    COUNT(*) FILTER (
        WHERE process_status = 'ACTIVE'
          AND khs_inject_start_date IS NOT NULL
          AND khs_inject_completion_date IS NULL
    ) AS inject_in_progress,
    COUNT(*) FILTER (
        WHERE process_status = 'ACTIVE'
          AND lp_completion_date IS NOT NULL
          AND khs_inject_start_date IS NULL
    ) AS inject_pending,
    COUNT(*) FILTER (WHERE process_status = 'ACTIVE' AND mi_gm_approval_date IS NOT NULL) AS mi_gm_approved,
    COUNT(*) FILTER (WHERE process_status = 'ACTIVE' AND mi_gm_approval_date IS NULL) AS mi_gm_pending,
    COUNT(*) FILTER (WHERE process_status = 'ACTIVE' AND legal_submission_date IS NOT NULL) AS legal_submitted,
    COUNT(*) FILTER (
        WHERE process_status = 'ACTIVE'
          AND lp_circulation_start_date IS NOT NULL
          AND (mi_gm_approval_date IS NULL OR lp_circulation_start_date < mi_gm_approval_date)
    ) AS lp_started_without_mi_gm,
    COUNT(*) FILTER (
        WHERE process_status = 'ACTIVE'
          AND mi_gm_approval_date IS NOT NULL
          AND lp_circulation_start_date IS NULL
          AND lp_contract_team_completion_date IS NULL
          AND lp_junior_manager_approval_date IS NULL
          AND lp_senior_manager_approval_date IS NULL
          AND lp_gm_scm_approval_date IS NULL
          AND lp_completion_date IS NULL
    ) AS awaiting_lp_circulation,
    COUNT(*) FILTER (WHERE process_status = 'ACTIVE') AS active_khs_total,
    COUNT(*) FILTER (WHERE process_status = 'NOT_PROCEEDED') AS not_proceeded_khs
FROM khs_items;
"""


@dashboard_bp.get("/summary")
def dashboard_summary():
    try:
        with get_db_pool().connection() as conn:
            row = conn.execute(SUMMARY_QUERY).fetchone()

        if row is None:
            raise RuntimeError("Dashboard aggregate query returned no row.")

    except Exception:
        current_app.logger.exception(
            "Dashboard summary query failed."
        )
        return jsonify({
            "success": False,
            "code": "DASHBOARD_SUMMARY_UNAVAILABLE",
            "message": "Dashboard summary is temporarily unavailable.",
        }), 503

    (
        total_requests,
        total_khs,
        lp_completed,
        lp_in_progress,
        lp_not_started,
        inject_completed,
        inject_in_progress,
        inject_pending,
        mi_gm_approved,
        mi_gm_pending,
        legal_submitted,
        lp_started_without_mi_gm,
        awaiting_lp_circulation,
    ) = row[:13]
    active_khs_total = row[13] if len(row) > 13 else total_khs
    not_proceeded_khs = row[14] if len(row) > 14 else 0
    completion_rate = round((lp_completed / active_khs_total) * 100, 2) if active_khs_total else 0.0

    return jsonify({
        "success": True,
        "data": {
            "total_requests": total_requests,
            "total_khs": total_khs,
            "active_khs": active_khs_total,
            "not_proceeded_khs": not_proceeded_khs,
            "lp": {
                "completed": lp_completed,
                "in_progress": lp_in_progress,
                "not_started": lp_not_started,
                "completion_rate_percent": completion_rate,
            },
            "khs_inject": {
                "completed": inject_completed,
                "in_progress": inject_in_progress,
                "pending": inject_pending,
                "completion_rate_percent": (
                    round((inject_completed / active_khs_total) * 100, 2)
                    if active_khs_total else 0.0
                ),
            },
            "fully_injected": inject_completed,
            "workflow": {
                "mi_gm_approved": mi_gm_approved,
                "mi_gm_pending": mi_gm_pending,
                "legal_submitted": legal_submitted,
                "awaiting_lp_circulation": awaiting_lp_circulation,
            },
            "data_quality": {
                "lp_started_without_mi_gm_approval": (
                    lp_started_without_mi_gm
                ),
            },
        },
    }), 200


@dashboard_bp.get("/filters")
def dashboard_filters():
    """Return active filter options from the current master data."""

    query = """
    SELECT
        COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'executor_code', executor_code,
                        'display_name', display_name
                    )
                    ORDER BY display_name
                )
                FROM khs_executors
                WHERE is_active = TRUE
            ),
            '[]'::jsonb
        ) AS executors,

        COALESCE(
            (
                SELECT jsonb_agg(DISTINCT subtype ORDER BY subtype)
                FROM khs_items
                WHERE subtype IS NOT NULL
                  AND btrim(subtype) <> ''
            ),
            '[]'::jsonb
        ) AS subtypes,

        COALESCE(
            (
                SELECT jsonb_agg(DISTINCT waiting_for ORDER BY waiting_for)
                FROM khs_items
                WHERE waiting_for IS NOT NULL
                  AND btrim(waiting_for) <> ''
            ),
            '[]'::jsonb
        ) AS waiting_for,

        COALESCE(
            (
                SELECT jsonb_agg(
                    jsonb_build_object(
                        'stage_code', stage_code,
                        'stage_name', stage_name,
                        'sequence_number', sequence_number
                    )
                    ORDER BY sequence_number
                )
                FROM khs_stage_config
                WHERE is_active = TRUE
            ),
            '[]'::jsonb
        ) AS stages
    """

    try:
        with get_db_pool().connection() as conn:
            row = conn.execute(query).fetchone()

        if row is None:
            raise RuntimeError("Dashboard filter query returned no row.")

        executors, subtypes, waiting_for, stages = row

    except Exception:
        current_app.logger.exception(
            "Dashboard filter options query failed."
        )
        return jsonify({
            "success": False,
            "code": "DASHBOARD_FILTERS_UNAVAILABLE",
            "message": "Dashboard filter options are temporarily unavailable.",
        }), 503

    return jsonify({
        "success": True,
        "data": {
            "executors": executors or [],
            "subtypes": subtypes or [],
            "waiting_for": waiting_for or [],
            "stages": stages or [],
        },
    }), 200


REGISTER_BASE_QUERY = """
SELECT
    k.khs_id,
    k.request_id,
    r.request_date,
    r.request_subject,
    r.requester_owner,

    k.vendor_name,
    k.executor_code,
    e.display_name AS executor_name,
    k.subtype,

    k.dispatch_date,
    k.contract_start_date,
    k.contract_end_date,
    k.boq_confirmation_date,
    k.negotiation_date,
    k.final_negotiation_date,
    k.mi_head_approval_date,
    k.mi_sm_approval_date,
    k.mi_gm_approval_date,
    k.legal_submission_date,
    k.lp_circulation_start_date,
    k.lp_contract_team_completion_date,
    k.lp_junior_manager_approval_date,
    k.lp_senior_manager_approval_date,
    k.lp_gm_scm_approval_date,
    k.lp_completion_date,
    k.khs_inject_start_date,
    k.khs_inject_completion_date,
    k.action_owner,
    k.process_status,
    k.closure_date,
    k.closure_reason_code,
    k.closure_notes,
    k.closed_at,
    k.closed_by,
    k.reopened_at,
    k.reopened_by,
    k.reopen_reason,

    k.waiting_for,
    k.waiting_reason,
    k.last_updated_date,
    k.remarks,
    k.legacy_overall_status,
    k.legacy_detailed_status,
    k.migration_review,
    k.updated_at,

    derived.lp_status,
    derived.workflow_status,
    CASE WHEN k.process_status = 'NOT_PROCEEDED'
         THEN 'NOT_PROCEEDED' ELSE derived.current_stage_code END AS current_stage_code,
    derived.current_stage_code AS workflow_stage_code,
    stage.stage_name AS current_stage_name,
    derived.lp_stage_key,
    derived.lp_timeline_has_gaps,

    CASE derived.current_stage_code
        WHEN 'REQUEST_RECEIVED' THEN r.request_date
        WHEN 'DISPATCH' THEN r.request_date
        WHEN 'BOQ_CONFIRMATION' THEN k.dispatch_date
        WHEN 'NEGOTIATION' THEN k.boq_confirmation_date
        WHEN 'FINAL_NEGOTIATION' THEN k.negotiation_date
        WHEN 'MI_HEAD_APPROVAL' THEN k.final_negotiation_date
        WHEN 'MI_SM_APPROVAL' THEN k.mi_head_approval_date
        WHEN 'MI_GM_APPROVAL' THEN k.mi_sm_approval_date
        WHEN 'LEGAL_SUBMISSION' THEN k.mi_gm_approval_date
        WHEN 'LEGAL_PROCESSING' THEN k.legal_submission_date
        WHEN 'LP_CIRCULATION' THEN
            CASE derived.lp_stage_key
                WHEN 'contract_team' THEN k.lp_circulation_start_date
                WHEN 'junior_manager' THEN k.lp_contract_team_completion_date
                WHEN 'senior_manager' THEN k.lp_junior_manager_approval_date
                WHEN 'general_manager' THEN k.lp_senior_manager_approval_date
                WHEN 'director' THEN k.lp_gm_scm_approval_date
                ELSE NULL
            END
        WHEN 'KHS_INJECTION' THEN k.lp_completion_date
        ELSE NULL
    END AS current_stage_started_on,

    (
        k.lp_circulation_start_date IS NOT NULL
        AND (
              k.mi_gm_approval_date IS NULL
           OR k.lp_circulation_start_date < k.mi_gm_approval_date
        )
    ) AS lp_started_without_mi_gm_approval

FROM khs_items k

JOIN khs_requests r
    ON r.request_id = k.request_id

LEFT JOIN khs_executors e
    ON e.executor_code = k.executor_code

CROSS JOIN LATERAL (
    SELECT
        CASE
            WHEN k.lp_completion_date IS NOT NULL
                THEN 'completed'
            WHEN k.lp_circulation_start_date IS NOT NULL
              OR k.lp_contract_team_completion_date IS NOT NULL
              OR k.lp_junior_manager_approval_date IS NOT NULL
              OR k.lp_senior_manager_approval_date IS NOT NULL
              OR k.lp_gm_scm_approval_date IS NOT NULL
                THEN 'in_progress'
            ELSE 'not_started'
        END AS lp_status,

        CASE
            WHEN k.process_status = 'NOT_PROCEEDED' THEN 'not_proceeded'
            WHEN k.khs_inject_completion_date IS NOT NULL
                THEN 'completed'
            WHEN k.dispatch_date IS NOT NULL
              OR k.boq_confirmation_date IS NOT NULL
              OR k.negotiation_date IS NOT NULL
              OR k.final_negotiation_date IS NOT NULL
              OR k.mi_head_approval_date IS NOT NULL
              OR k.mi_sm_approval_date IS NOT NULL
              OR k.mi_gm_approval_date IS NOT NULL
              OR k.legal_submission_date IS NOT NULL
              OR k.lp_circulation_start_date IS NOT NULL
              OR k.lp_contract_team_completion_date IS NOT NULL
              OR k.lp_junior_manager_approval_date IS NOT NULL
              OR k.lp_senior_manager_approval_date IS NOT NULL
              OR k.lp_gm_scm_approval_date IS NOT NULL
              OR k.lp_completion_date IS NOT NULL
                THEN 'in_progress'
            ELSE 'not_started'
        END AS workflow_status,

        CASE
            WHEN k.khs_inject_completion_date IS NOT NULL
                THEN 'COMPLETED'
            WHEN k.lp_completion_date IS NOT NULL
                THEN 'KHS_INJECTION'
            WHEN k.lp_circulation_start_date IS NOT NULL
              OR k.lp_contract_team_completion_date IS NOT NULL
              OR k.lp_junior_manager_approval_date IS NOT NULL
              OR k.lp_senior_manager_approval_date IS NOT NULL
              OR k.lp_gm_scm_approval_date IS NOT NULL
                THEN 'LP_CIRCULATION'
            WHEN k.legal_submission_date IS NOT NULL
                THEN 'LEGAL_PROCESSING'
            WHEN k.mi_gm_approval_date IS NOT NULL
                THEN 'LEGAL_SUBMISSION'
            WHEN k.mi_sm_approval_date IS NOT NULL
                THEN 'MI_GM_APPROVAL'
            WHEN k.mi_head_approval_date IS NOT NULL
                THEN 'MI_SM_APPROVAL'
            WHEN k.final_negotiation_date IS NOT NULL
                THEN 'MI_HEAD_APPROVAL'
            WHEN k.negotiation_date IS NOT NULL
                THEN 'FINAL_NEGOTIATION'
            WHEN k.boq_confirmation_date IS NOT NULL
                THEN 'NEGOTIATION'
            WHEN k.dispatch_date IS NOT NULL
                THEN 'BOQ_CONFIRMATION'
            WHEN r.request_date IS NOT NULL
                THEN 'DISPATCH'
            ELSE 'REQUEST_RECEIVED'
        END AS current_stage_code,

        CASE
            WHEN k.lp_completion_date IS NOT NULL
                THEN 'completed'
            WHEN k.lp_circulation_start_date IS NOT NULL
              AND (
                    k.mi_gm_approval_date IS NULL
                 OR k.lp_circulation_start_date < k.mi_gm_approval_date
              )
                THEN 'prerequisite_exception'
            WHEN (
                (k.lp_circulation_start_date IS NULL AND (
                    k.lp_contract_team_completion_date IS NOT NULL
                    OR k.lp_junior_manager_approval_date IS NOT NULL
                    OR k.lp_senior_manager_approval_date IS NOT NULL
                    OR k.lp_gm_scm_approval_date IS NOT NULL
                ))
                OR (k.lp_contract_team_completion_date IS NULL AND (
                    k.lp_junior_manager_approval_date IS NOT NULL
                    OR k.lp_senior_manager_approval_date IS NOT NULL
                    OR k.lp_gm_scm_approval_date IS NOT NULL
                ))
                OR (k.lp_junior_manager_approval_date IS NULL AND (
                    k.lp_senior_manager_approval_date IS NOT NULL
                    OR k.lp_gm_scm_approval_date IS NOT NULL
                ))
                OR (k.lp_senior_manager_approval_date IS NULL
                    AND k.lp_gm_scm_approval_date IS NOT NULL)
            )
                THEN 'legacy_incomplete'
            WHEN k.lp_circulation_start_date IS NOT NULL
              AND k.lp_contract_team_completion_date IS NULL
              AND k.lp_junior_manager_approval_date IS NULL
              AND k.lp_senior_manager_approval_date IS NULL
              AND k.lp_gm_scm_approval_date IS NULL
              AND LOWER(BTRIM(COALESCE(k.legacy_overall_status, '')))
                    IN ('done', 'completed')
                THEN 'legacy_unverified'
            WHEN k.lp_circulation_start_date IS NULL
                THEN 'not_started'
            WHEN k.lp_contract_team_completion_date IS NULL
                THEN 'contract_team'
            WHEN k.lp_junior_manager_approval_date IS NULL
                THEN 'junior_manager'
            WHEN k.lp_senior_manager_approval_date IS NULL
                THEN 'senior_manager'
            WHEN k.lp_gm_scm_approval_date IS NULL
                THEN 'general_manager'
            ELSE 'director'
        END AS lp_stage_key,

        (
            (k.lp_circulation_start_date IS NULL AND (
                k.lp_contract_team_completion_date IS NOT NULL
                OR k.lp_junior_manager_approval_date IS NOT NULL
                OR k.lp_senior_manager_approval_date IS NOT NULL
                OR k.lp_gm_scm_approval_date IS NOT NULL
                OR k.lp_completion_date IS NOT NULL
            ))
            OR (k.lp_contract_team_completion_date IS NULL AND (
                k.lp_junior_manager_approval_date IS NOT NULL
                OR k.lp_senior_manager_approval_date IS NOT NULL
                OR k.lp_gm_scm_approval_date IS NOT NULL
                OR k.lp_completion_date IS NOT NULL
            ))
            OR (k.lp_junior_manager_approval_date IS NULL AND (
                k.lp_senior_manager_approval_date IS NOT NULL
                OR k.lp_gm_scm_approval_date IS NOT NULL
                OR k.lp_completion_date IS NOT NULL
            ))
            OR (k.lp_senior_manager_approval_date IS NULL AND (
                k.lp_gm_scm_approval_date IS NOT NULL
                OR k.lp_completion_date IS NOT NULL
            ))
            OR (k.lp_gm_scm_approval_date IS NULL AND k.lp_completion_date IS NOT NULL)
        ) AS lp_timeline_has_gaps
) AS derived

LEFT JOIN khs_stage_config stage
    ON stage.stage_code = CASE WHEN k.process_status = 'NOT_PROCEEDED'
                               THEN 'NOT_PROCEEDED' ELSE derived.current_stage_code END
"""


ALLOWED_LP_STATUSES = {
    "completed",
    "in_progress",
    "not_started",
}

ALLOWED_SUBTYPES = {
    "Renewal",
    "Kontrak Baru",
}

def _waiting_role_case_sql(column):
    """Map a free-text Waiting For value to one exclusive approval role.

    The column name is supplied only by internal code, never by request input.
    Role precedence prevents compound labels from being counted in multiple
    LP lanes.
    """
    value = f"lower(trim(COALESCE({column}, '')))"
    return f"""
        CASE
            WHEN POSITION('junior manager' IN {value}) > 0
              OR POSITION('jm vendor' IN {value}) > 0
                THEN 'junior_manager'
            WHEN POSITION('senior manager' IN {value}) > 0
                THEN 'senior_manager'
            WHEN POSITION('general manager' IN {value}) > 0
              OR POSITION('gm scm' IN {value}) > 0
                THEN 'general_manager'
            WHEN POSITION('director' IN {value}) > 0
              OR POSITION('direktur' IN {value}) > 0
                THEN 'director'
            ELSE 'unassigned_or_other'
        END
    """


ALLOWED_STAGES = {
    "REQUEST_RECEIVED",
    "DISPATCH",
    "BOQ_CONFIRMATION",
    "NEGOTIATION",
    "FINAL_NEGOTIATION",
    "MI_HEAD_APPROVAL",
    "MI_SM_APPROVAL",
    "MI_GM_APPROVAL",
    "LEGAL_SUBMISSION",
    "LEGAL_PROCESSING",
    "LP_CIRCULATION",
    "KHS_INJECTION",
    "COMPLETED",
    "NOT_PROCEEDED",
}


def _register_positive_int(name, default, maximum=None):
    raw = request.args.get(name)

    if raw is None:
        return default

    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a positive integer.")

    if value < 1:
        raise ValueError(f"'{name}' must be greater than zero.")

    if maximum is not None and value > maximum:
        raise ValueError(f"'{name}' must not exceed {maximum}.")

    return value


def _register_json_safe(row):
    return {
        key: (
            value.isoformat()
            if isinstance(value, (date, datetime))
            else value
        )
        for key, value in row.items()
    }


LP_MILESTONE_ORDER = (
    ("lp_circulation_start_date", "LP Submitted by User"),
    ("lp_contract_team_completion_date", "Tim Kontrak Completed"),
    ("lp_junior_manager_approval_date", "Junior Manager Approved"),
    ("lp_senior_manager_approval_date", "Senior Manager Approved"),
    ("lp_gm_scm_approval_date", "GM SCM Approved"),
    ("lp_completion_date", "Director Signed"),
)
LP_STAGE_LABELS = {
    "not_started": "Not Started",
    "prerequisite_exception": "MI GM Prerequisite Exception",
    "legacy_unverified": "Legacy LP Stage Unverified",
    "legacy_incomplete": "Legacy Timeline Incomplete",
    "contract_team": "Tim Kontrak",
    "junior_manager": "Junior Manager",
    "senior_manager": "Senior Manager",
    "general_manager": "GM SCM",
    "director": "Director / Direktur",
    "completed": "LP Completed",
}
LP_STAGE_FILTERS = set(LP_STAGE_LABELS) - {"not_started"}


def _date_only(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _jakarta_today():
    return datetime.now(ZoneInfo("Asia/Jakarta")).date()


def _lp_timeline_summary(record, today=None):
    """Derive the next LP step while preserving gaps in legacy history."""
    today = today or _jakarta_today()
    values = [_date_only(record.get(field)) for field, _ in LP_MILESTONE_ORDER]
    populated = [index for index, value in enumerate(values) if value is not None]
    last_populated = max(populated) if populated else -1
    gaps = [
        LP_MILESTONE_ORDER[index][0]
        for index in range(last_populated + 1)
        if values[index] is None
    ]
    has_gaps = bool(gaps)
    start_date = values[0]
    completion_date = values[-1]
    mi_gm_date = _date_only(record.get("mi_gm_approval_date"))
    legacy_status = str(record.get("legacy_overall_status") or "").strip().casefold()
    prerequisite_exception = bool(
        start_date and (mi_gm_date is None or start_date < mi_gm_date)
    )
    legacy_unverified = bool(
        start_date
        and not any(values[1:])
        and legacy_status in {"done", "completed"}
    )

    if completion_date is not None:
        stage_key = "completed"
        stage_started = None
        stage_age = None
    elif prerequisite_exception:
        stage_key = "prerequisite_exception"
        stage_started = None
        stage_age = None
    elif has_gaps:
        # A later milestone exists after a missing earlier date. The current
        # owner/stage cannot be inferred reliably from milestone dates alone.
        stage_key = "legacy_incomplete"
        stage_started = None
        stage_age = None
    elif legacy_unverified:
        # Legacy "Done" is not proof of Director sign-off under the current
        # LP completion rule. Keep it out of active approver lanes until verified.
        stage_key = "legacy_unverified"
        stage_started = None
        stage_age = None
    elif start_date is None:
        stage_key = "not_started"
        stage_started = None
        stage_age = None
    else:
        next_index = next(
            (index for index in range(1, len(values)) if values[index] is None),
            len(values) - 1,
        )
        stage_keys = (
            None,
            "contract_team",
            "junior_manager",
            "senior_manager",
            "general_manager",
            "director",
        )
        stage_key = stage_keys[next_index]
        prior_dates = [value for value in values[:next_index] if value is not None]
        stage_started = prior_dates[-1] if prior_dates else start_date
        stage_age = max((today - stage_started).days, 0) if stage_started else None

    if has_gaps:
        data_status = "legacy_incomplete"
    elif stage_key == "completed":
        data_status = "complete"
    elif stage_key == "prerequisite_exception":
        data_status = "prerequisite_exception"
    elif stage_key == "legacy_unverified":
        data_status = "legacy_unverified"
    elif stage_key == "not_started":
        data_status = "not_started"
    else:
        data_status = "in_progress"

    return {
        "lp_stage_key": stage_key,
        "lp_stage_label": LP_STAGE_LABELS[stage_key],
        "lp_stage_started_date": stage_started.isoformat() if stage_started else None,
        "lp_stage_age_days": stage_age,
        "lp_timeline_has_gaps": has_gaps,
        "lp_timeline_gaps": gaps,
        "lp_timeline_data_status": data_status,
        "lp_prerequisite_exception": prerequisite_exception,
        "lp_legacy_unverified": legacy_unverified,
    }


def _add_calendar_months(value, months):
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _contract_term(start, end):
    if not start or not end or end < start:
        return None, None
    duration_days = (end - start).days + 1
    exclusive_end = end + timedelta(days=1)
    months = (exclusive_end.year - start.year) * 12 + exclusive_end.month - start.month
    while months > 0 and _add_calendar_months(start, months) > exclusive_end:
        months -= 1
    while _add_calendar_months(start, months + 1) <= exclusive_end:
        months += 1
    remaining_days = (exclusive_end - _add_calendar_months(start, months)).days
    years, month_remainder = divmod(months, 12)
    parts = []
    if years:
        parts.append(f"{years} year" + ("s" if years != 1 else ""))
    if month_remainder:
        parts.append(f"{month_remainder} month" + ("s" if month_remainder != 1 else ""))
    if remaining_days:
        parts.append(f"{remaining_days} day" + ("s" if remaining_days != 1 else ""))
    return duration_days, " ".join(parts) or "1 day"


CONTRACT_ALERT_LABELS = {
    "missing_dates": "Missing Contract Dates",
    "invalid_dates": "Invalid Contract Dates",
    "expired": "Expired",
    "critical_7d": "Final Warning · 7 Days",
    "urgent_14d": "Urgent · 14 Days",
    "urgent_1m": "Action Required · 1 Month",
    "watch_3m": "Renewal Watch · 3 Months",
    "prep_6m": "Renewal Preparation · 6 Months",
    "active": "Active",
    "not_fully_injected": "Not Fully Injected",
}

CONTRACT_OPERATIONAL_LABELS = {
    "missing_dates": "Missing Contract Dates",
    "invalid_dates": "Invalid Contract Dates",
    "expired": "Expired",
    "upcoming": "Upcoming",
    "active": "Active",
    "not_fully_injected": "Not Fully Injected",
}


def _contract_lifecycle_data(record, today=None):
    """Return operational contract state separately from renewal urgency."""
    today = today or _jakarta_today()
    fully_injected = _date_only(record.get("khs_inject_completion_date"))
    start = _date_only(record.get("contract_start_date"))
    end = _date_only(record.get("contract_end_date"))

    if not fully_injected:
        status = "not_fully_injected"
    elif start is None or end is None:
        status = "missing_dates"
    elif end < start:
        status = "invalid_dates"
    elif end < today:
        status = "expired"
    else:
        days_remaining = (end - today).days
        if days_remaining <= 7:
            status = "critical_7d"
        elif days_remaining <= 14:
            status = "urgent_14d"
        elif end <= _add_calendar_months(today, 1):
            status = "urgent_1m"
        elif end <= _add_calendar_months(today, 3):
            status = "watch_3m"
        elif end <= _add_calendar_months(today, 6):
            status = "prep_6m"
        else:
            status = "active"

    if not fully_injected:
        operational_status = "not_fully_injected"
    elif start is None or end is None:
        operational_status = "missing_dates"
    elif end < start:
        operational_status = "invalid_dates"
    elif end < today:
        operational_status = "expired"
    elif start > today:
        operational_status = "upcoming"
    else:
        operational_status = "active"

    duration_days, duration_label = _contract_term(start, end)
    days_remaining = (end - today).days if end else None
    return {
        "contract_lifecycle_status": status,
        "contract_lifecycle_label": CONTRACT_ALERT_LABELS[status],
        "contract_renewal_alert_status": status,
        "contract_renewal_alert_label": CONTRACT_ALERT_LABELS[status],
        "contract_operational_status": operational_status,
        "contract_operational_status_label": CONTRACT_OPERATIONAL_LABELS[operational_status],
        "contract_days_remaining": days_remaining,
        "contract_duration_days": duration_days,
        "contract_duration_label": duration_label,
        "contract_lifecycle_as_of": today.isoformat(),
    }



PROCESS_DURATION_STAGES = (
    ("DISPATCH", "Dispatch", "request_date", "dispatch_date"),
    ("BOQ_CONFIRMATION", "BOQ Confirmation", "dispatch_date", "boq_confirmation_date"),
    ("NEGOTIATION", "Negotiation", "boq_confirmation_date", "negotiation_date"),
    ("FINAL_NEGOTIATION", "Final Negotiation", "negotiation_date", "final_negotiation_date"),
    ("MI_HEAD_APPROVAL", "MI Head Approval", "final_negotiation_date", "mi_head_approval_date"),
    ("MI_SM_APPROVAL", "MI Senior Manager Approval", "mi_head_approval_date", "mi_sm_approval_date"),
    ("MI_GM_APPROVAL", "MI General Manager Approval", "mi_sm_approval_date", "mi_gm_approval_date"),
    ("LEGAL_SUBMISSION", "Legal Submission", "mi_gm_approval_date", "legal_submission_date"),
    ("LEGAL_PROCESSING", "Legal Processing", "legal_submission_date", "lp_circulation_start_date"),
    ("LP_CONTRACT_TEAM", "LP Contract Team", "lp_circulation_start_date", "lp_contract_team_completion_date"),
    ("LP_JUNIOR_MANAGER", "LP Junior Manager", "lp_contract_team_completion_date", "lp_junior_manager_approval_date"),
    ("LP_SENIOR_MANAGER", "LP Senior Manager", "lp_junior_manager_approval_date", "lp_senior_manager_approval_date"),
    ("LP_GM_SCM", "LP GM SCM", "lp_senior_manager_approval_date", "lp_gm_scm_approval_date"),
    ("LP_DIRECTOR", "LP Director Sign-off", "lp_gm_scm_approval_date", "lp_completion_date"),
    ("INJECTION_PREPARATION", "Injection Preparation", "lp_completion_date", "khs_inject_start_date"),
    ("KHS_INJECTION", "KHS Injection", "khs_inject_start_date", "khs_inject_completion_date"),
)


def _duration_stage_is_current(stage_code, record):
    workflow_stage = record.get("workflow_stage_code") or record.get("current_stage_code")
    lp_stage_map = {
        "LP_CONTRACT_TEAM": "contract_team",
        "LP_JUNIOR_MANAGER": "junior_manager",
        "LP_SENIOR_MANAGER": "senior_manager",
        "LP_GM_SCM": "general_manager",
        "LP_DIRECTOR": "director",
    }
    if stage_code in lp_stage_map:
        return workflow_stage == "LP_CIRCULATION" and record.get("lp_stage_key") == lp_stage_map[stage_code]
    if stage_code == "INJECTION_PREPARATION":
        return workflow_stage == "KHS_INJECTION" and not _date_only(record.get("khs_inject_start_date"))
    if stage_code == "KHS_INJECTION":
        return workflow_stage == "KHS_INJECTION" and _date_only(record.get("khs_inject_start_date")) is not None
    return workflow_stage == stage_code


def _process_duration_history(record, today=None):
    """Calculate calendar-day durations from business milestone dates only."""
    today = today or _jakarta_today()
    process_status = record.get("process_status") or "ACTIVE"
    closure_date = _date_only(record.get("closure_date"))
    stages = []
    for stage_code, label, start_field, end_field in PROCESS_DURATION_STAGES:
        start, end = _date_only(record.get(start_field)), _date_only(record.get(end_field))
        is_current = _duration_stage_is_current(stage_code, record)
        if not start and not end and not is_current:
            continue
        status, duration_days, display_end = "history_incomplete", None, end
        if start and end:
            if end < start:
                status = "invalid_chronology"
            else:
                status, duration_days = "completed", (end - start).days
        elif start and is_current and process_status == "NOT_PROCEEDED":
            display_end = closure_date
            if closure_date and closure_date >= start:
                status, duration_days = "stopped", (closure_date - start).days
            else:
                status = "invalid_chronology" if closure_date else "date_unavailable"
        elif start and is_current and process_status == "ACTIVE":
            display_end = today
            if today >= start:
                status, duration_days = "in_progress", (today - start).days
            else:
                status = "invalid_chronology"
        elif not start and not end and is_current:
            status = "date_unavailable"
        stages.append({
            "stage_code": stage_code, "stage_label": label,
            "start_date": start.isoformat() if start else None,
            "end_date": display_end.isoformat() if display_end else None,
            "duration_days": duration_days, "status": status,
        })

    request_date = _date_only(record.get("request_date"))
    injected_date = _date_only(record.get("khs_inject_completion_date"))
    if injected_date:
        process_end, total_status = injected_date, "completed"
    elif process_status == "NOT_PROCEEDED":
        process_end, total_status = closure_date, "stopped" if closure_date else "date_unavailable"
    else:
        process_end, total_status = today, "in_progress"
    total_days = None
    if request_date and process_end:
        if process_end >= request_date:
            total_days = (process_end - request_date).days
        else:
            total_status = "invalid_chronology"

    lp_start, lp_end = _date_only(record.get("lp_circulation_start_date")), _date_only(record.get("lp_completion_date"))
    lp_status, lp_days = "not_started", None
    if lp_start and lp_end:
        if lp_end >= lp_start:
            lp_status, lp_days = "completed", (lp_end - lp_start).days
        else:
            lp_status = "invalid_chronology"
    elif lp_start and process_status == "NOT_PROCEEDED":
        if closure_date and closure_date >= lp_start:
            lp_status, lp_days = "stopped", (closure_date - lp_start).days
        else:
            lp_status = "date_unavailable"
    elif lp_start:
        lp_status, lp_days = "in_progress", (today - lp_start).days if today >= lp_start else None

    return {
        "process_duration_history": stages,
        "total_processing_duration_days": total_days,
        "total_processing_status": total_status if request_date else "date_unavailable",
        "total_processing_start_date": request_date.isoformat() if request_date else None,
        "total_processing_end_date": process_end.isoformat() if process_end else None,
        "lp_circulation_duration_days": lp_days,
        "lp_circulation_duration_status": lp_status,
    }


def _register_enriched(row, today=None, include_duration_history=False):
    today = today or _jakarta_today()
    record = _register_json_safe(row)
    record.update(_lp_timeline_summary(row, today=today))
    stage_started = _date_only(row.get("current_stage_started_on"))
    if row.get("workflow_status") == "completed":
        stage_started = None
    record["current_stage_started_on"] = stage_started.isoformat() if stage_started else None
    age_end = _date_only(row.get("closure_date")) if row.get("process_status") == "NOT_PROCEEDED" else today
    record["current_stage_age_days"] = (
        (age_end - stage_started).days
        if stage_started and age_end and age_end >= stage_started else None
    )
    record["current_stage_age_status"] = (
        "stopped" if row.get("process_status") == "NOT_PROCEEDED"
        else "completed" if row.get("workflow_status") == "completed" else "in_progress"
    )
    record["contract_lifecycle"] = _contract_lifecycle_data(row, today=today)
    if include_duration_history:
        record.update(_process_duration_history(row, today=today))
    record["guided_progress"] = (
        None if record.get("process_status") == "NOT_PROCEEDED"
        or record.get("workflow_status") == "completed"
        else _guided_progress_definition(record)
    )
    return record



GUIDED_MILESTONE_LABELS = {
    "dispatch_date": "Dispatch completed",
    "boq_confirmation_date": "BOQ confirmed",
    "negotiation_date": "Negotiation completed",
    "final_negotiation_date": "Final negotiation completed",
    "mi_head_approval_date": "MI Head approval recorded",
    "mi_sm_approval_date": "MI Senior Manager approval recorded",
    "mi_gm_approval_date": "MI GM approval recorded",
    "legal_submission_date": "Legal submission recorded",
    "lp_circulation_start_date": "LP submitted by User",
    "lp_contract_team_completion_date": "Contract Team completed",
    "lp_junior_manager_approval_date": "Junior Manager approval recorded",
    "lp_senior_manager_approval_date": "Senior Manager approval recorded",
    "lp_gm_scm_approval_date": "GM SCM approval recorded",
    "lp_completion_date": "Director sign-off recorded",
    "khs_inject_start_date": "KHS injection started",
    "khs_inject_completion_date": "KHS fully injected",
}
GUIDED_STAGE_FIELD = {
    "DISPATCH": "dispatch_date",
    "BOQ_CONFIRMATION": "boq_confirmation_date",
    "NEGOTIATION": "negotiation_date",
    "FINAL_NEGOTIATION": "final_negotiation_date",
    "MI_HEAD_APPROVAL": "mi_head_approval_date",
    "MI_SM_APPROVAL": "mi_sm_approval_date",
    "MI_GM_APPROVAL": "mi_gm_approval_date",
    "LEGAL_SUBMISSION": "legal_submission_date",
    "LEGAL_PROCESSING": "lp_circulation_start_date",
}


def _guided_progress_definition(record):
    stage = record.get("workflow_stage_code") or record.get("current_stage_code")
    field = GUIDED_STAGE_FIELD.get(stage)
    lp_fields = {
        "contract_team": "lp_contract_team_completion_date",
        "junior_manager": "lp_junior_manager_approval_date",
        "senior_manager": "lp_senior_manager_approval_date",
        "general_manager": "lp_gm_scm_approval_date",
        "director": "lp_completion_date",
    }
    if stage == "LP_CIRCULATION":
        field = lp_fields.get(record.get("lp_stage_key"))
    elif stage == "KHS_INJECTION":
        field = "khs_inject_completion_date" if _date_only(record.get("khs_inject_start_date")) else "khs_inject_start_date"
    if not field or record.get(field) is not None:
        return None
    previous = {
        "dispatch_date": "request_date",
        "boq_confirmation_date": "dispatch_date",
        "negotiation_date": "boq_confirmation_date",
        "final_negotiation_date": "negotiation_date",
        "mi_head_approval_date": "final_negotiation_date",
        "mi_sm_approval_date": "mi_head_approval_date",
        "mi_gm_approval_date": "mi_sm_approval_date",
        "legal_submission_date": "mi_gm_approval_date",
        "lp_circulation_start_date": "legal_submission_date",
        "lp_contract_team_completion_date": "lp_circulation_start_date",
        "lp_junior_manager_approval_date": "lp_contract_team_completion_date",
        "lp_senior_manager_approval_date": "lp_junior_manager_approval_date",
        "lp_gm_scm_approval_date": "lp_senior_manager_approval_date",
        "lp_completion_date": "lp_gm_scm_approval_date",
        "khs_inject_start_date": "lp_completion_date",
        "khs_inject_completion_date": "khs_inject_start_date",
    }.get(field)
    started = _date_only(record.get("current_stage_started_on"))
    return {
        "field": field,
        "label": GUIDED_MILESTONE_LABELS[field],
        "stage_code": stage,
        "previous_milestone": previous,
        "current_stage_started_on": started.isoformat() if started else None,
    }


def _guided_progress_date_error(record, field, value):
    previous_fields = {
        "dispatch_date": "request_date",
        "boq_confirmation_date": "dispatch_date",
        "negotiation_date": "boq_confirmation_date",
        "final_negotiation_date": "negotiation_date",
        "mi_head_approval_date": "final_negotiation_date",
        "mi_sm_approval_date": "mi_head_approval_date",
        "mi_gm_approval_date": "mi_sm_approval_date",
        "legal_submission_date": "mi_gm_approval_date",
        "lp_circulation_start_date": "legal_submission_date",
        "lp_contract_team_completion_date": "lp_circulation_start_date",
        "lp_junior_manager_approval_date": "lp_contract_team_completion_date",
        "lp_senior_manager_approval_date": "lp_junior_manager_approval_date",
        "lp_gm_scm_approval_date": "lp_senior_manager_approval_date",
        "lp_completion_date": "lp_gm_scm_approval_date",
        "khs_inject_start_date": "lp_completion_date",
        "khs_inject_completion_date": "khs_inject_start_date",
    }
    following_fields = {previous: next_field for next_field, previous in previous_fields.items()}
    previous = previous_fields.get(field)
    next_field = following_fields.get(field)
    previous_date = _date_only(record.get(previous)) if previous else None
    next_date = _date_only(record.get(next_field)) if next_field else None
    if previous_date and value < previous_date:
        return "MILESTONE_BEFORE_PREVIOUS", f"{field} cannot precede {previous}."
    if next_date and value > next_date:
        return "MILESTONE_AFTER_NEXT", f"{field} cannot follow {next_field}."
    if field == "lp_circulation_start_date" and not record.get("mi_gm_approval_date"):
        return "MI_GM_REQUIRED", "LP circulation cannot start before GM SCM MI approval."
    if field.startswith("lp_"):
        error = _lp_milestone_update_error(record, {field: value})
        if error:
            return error
    return None


def _lp_date_order_error(record):
    populated = [
        (field, _date_only(record.get(field)))
        for field, _ in LP_MILESTONE_ORDER
        if _date_only(record.get(field)) is not None
    ]
    for previous, current in zip(populated, populated[1:]):
        if current[1] < previous[1]:
            return current[0]
    return None


def _lp_milestone_update_error(before, changes):
    """Validate changed LP milestones without locking incomplete legacy records.

    Existing records may have historical intermediate dates without a recorded
    circulation start. Unrelated metadata edits remain possible; changing any LP
    milestone still requires a complete, chronological update.
    """
    merged = {**before, **changes}
    intermediate_fields = (
        "lp_contract_team_completion_date",
        "lp_junior_manager_approval_date",
        "lp_senior_manager_approval_date",
        "lp_gm_scm_approval_date",
    )
    milestone_fields = (
        "lp_circulation_start_date",
        *intermediate_fields,
        "lp_completion_date",
    )
    milestones_changed = any(
        field in changes and changes[field] != before.get(field)
        for field in milestone_fields
    )
    legacy_intermediate_without_start = (
        not before.get("lp_circulation_start_date")
        and any(before.get(field) for field in intermediate_fields)
    )

    if (
        any(merged.get(field) for field in intermediate_fields)
        and not merged.get("lp_circulation_start_date")
        and (not legacy_intermediate_without_start or milestones_changed)
    ):
        return (
            "LP_START_REQUIRED",
            "LP milestone dates require an LP circulation start date.",
        )

    out_of_order_field = _lp_date_order_error(merged)
    if out_of_order_field and milestones_changed:
        return (
            "LP_MILESTONE_CHRONOLOGY",
            f"{out_of_order_field} cannot precede an earlier LP milestone.",
        )

    if (
        merged.get("lp_completion_date")
        and not merged.get("lp_circulation_start_date")
        and milestones_changed
    ):
        return (
            "LP_START_REQUIRED",
            "LP completion requires circulation start.",
        )

    if (
        merged.get("lp_completion_date")
        and merged.get("lp_circulation_start_date")
        and merged["lp_completion_date"] < merged["lp_circulation_start_date"]
        and milestones_changed
    ):
        return (
            "LP_DATE_ORDER",
            "LP completion cannot precede circulation start.",
        )

    return None


@dashboard_bp.get("/khs")
def khs_register():
    # Pagination validation.
    try:
        page = _register_positive_int("page", 1)
        per_page = _register_positive_int(
            "per_page",
            25,
            maximum=100,
        )
    except ValueError as exc:
        return jsonify({
            "success": False,
            "code": "INVALID_PAGINATION",
            "message": str(exc),
        }), 400

    # Filter validation.
    search = request.args.get("q", "").strip()
    if len(search) > 100:
        return jsonify({
            "success": False,
            "code": "INVALID_SEARCH",
            "message": "Search query must not exceed 100 characters.",
        }), 400

    lp_status = request.args.get("lp_status", "").strip()
    if lp_status and lp_status not in ALLOWED_LP_STATUSES:
        return jsonify({
            "success": False,
            "code": "INVALID_LP_STATUS",
            "message": "Unsupported LP status filter.",
        }), 400

    executor_code = request.args.get(
        "executor_code",
        "",
    ).strip().upper()

    if len(executor_code) > 32:
        return jsonify({
            "success": False,
            "code": "INVALID_EXECUTOR",
            "message": "Executor code is too long.",
        }), 400

    subtype = request.args.get("subtype", "").strip()
    if subtype and subtype not in ALLOWED_SUBTYPES:
        return jsonify({
            "success": False,
            "code": "INVALID_SUBTYPE",
            "message": "Unsupported subtype filter.",
        }), 400

    stage = request.args.get("stage", "").strip().upper()
    if stage and stage not in ALLOWED_STAGES:
        return jsonify({
            "success": False,
            "code": "INVALID_STAGE",
            "message": "Unsupported workflow stage filter.",
        }), 400

    waiting_role = request.args.get("waiting_role", "").strip().lower()
    allowed_waiting_roles = {
        "junior_manager", "senior_manager", "general_manager", "director"
    }
    if waiting_role and waiting_role not in allowed_waiting_roles:
        return jsonify({
            "success": False,
            "code": "INVALID_WAITING_ROLE",
            "message": "Unsupported LP approval role filter.",
        }), 400

    process_status = request.args.get("process_status", "").strip().upper()
    if process_status and process_status not in {"ACTIVE", "NOT_PROCEEDED"}:
        return jsonify({"success": False, "code": "INVALID_PROCESS_STATUS",
                        "message": "Unsupported KHS process status."}), 400

    waiting_for = request.args.get("waiting_for", "").strip()
    if len(waiting_for) > 100:
        return jsonify({
            "success": False,
            "code": "INVALID_WAITING_FOR",
            "message": "Waiting-for filter is too long.",
        }), 400

    # Construct parameterized filters.
    filters = []
    params = []

    if search:
        filters.append("""
            (
                register.khs_id ILIKE %s
                OR register.request_id ILIKE %s
                OR register.vendor_name ILIKE %s
                OR COALESCE(register.request_subject, '') ILIKE %s
                OR COALESCE(register.requester_owner, '') ILIKE %s
            )
        """)
        pattern = f"%{search}%"
        params.extend([pattern] * 5)

    if lp_status:
        filters.append("register.lp_status = %s")
        params.append(lp_status)

    if executor_code:
        filters.append("register.executor_code = %s")
        params.append(executor_code)

    if subtype:
        filters.append("register.subtype = %s")
        params.append(subtype)

    if stage:
        filters.append("register.current_stage_code = %s")
        params.append(stage)

    if waiting_role:
        filters.append(
            "((register.lp_circulation_start_date IS NOT NULL "
            "OR register.lp_contract_team_completion_date IS NOT NULL "
            "OR register.lp_junior_manager_approval_date IS NOT NULL "
            "OR register.lp_senior_manager_approval_date IS NOT NULL "
            "OR register.lp_gm_scm_approval_date IS NOT NULL) "
            "AND register.lp_completion_date IS NULL "
            "AND " + _waiting_role_case_sql("register.waiting_for") + " = %s)"
        )
        params.append(waiting_role)

    if waiting_for:
        filters.append("register.waiting_for = %s")
        params.append(waiting_for)
    if process_status:
        filters.append("register.process_status = %s")
        params.append(process_status)

    attention = request.args.get("attention", "").strip().lower() in {"1", "true", "yes"}
    if attention:
        filters.append("""
            (
                register.workflow_status <> 'completed'
                AND register.process_status = 'ACTIVE'
                AND (
                    NULLIF(BTRIM(COALESCE(register.waiting_for, '')), '') IS NOT NULL
                    OR NULLIF(BTRIM(COALESCE(register.waiting_reason, '')), '') IS NOT NULL
                    OR register.lp_started_without_mi_gm_approval IS TRUE
                    OR register.lp_stage_key IN (
                        'prerequisite_exception',
                        'legacy_unverified',
                        'legacy_incomplete'
                    )
                    OR register.lp_timeline_has_gaps IS TRUE
                )
            )
        """)

    where_sql = (
        "WHERE " + " AND ".join(filters)
        if filters
        else ""
    )

    offset = (page - 1) * per_page

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM ({REGISTER_BASE_QUERY}) AS register
        {where_sql}
    """

    data_query = f"""
        SELECT *
        FROM ({REGISTER_BASE_QUERY}) AS register
        {where_sql}
        ORDER BY register.lp_started_without_mi_gm_approval DESC,
                 register.current_stage_started_on ASC NULLS LAST,
                 (register.waiting_for IS NOT NULL) DESC,
                 register.updated_at ASC NULLS FIRST,
                 register.dispatch_date DESC NULLS LAST,
                 register.khs_id ASC
        LIMIT %s OFFSET %s
    """

    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(count_query, params)
                total = cursor.fetchone()["total"]

                cursor.execute(
                    data_query,
                    [*params, per_page, offset],
                )
                rows = cursor.fetchall()

    except Exception:
        current_app.logger.exception(
            "KHS register query failed."
        )
        return jsonify({
            "success": False,
            "code": "KHS_REGISTER_UNAVAILABLE",
            "message": "KHS register is temporarily unavailable.",
        }), 503

    total_pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return jsonify({
        "success": True,
        "data": [_register_enriched(row) for row in rows],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_records": total,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        },
        "filters": {
            "q": search or None,
            "lp_status": lp_status or None,
            "executor_code": executor_code or None,
            "subtype": subtype or None,
            "stage": stage or None,
            "waiting_for": waiting_for or None,
            "waiting_role": waiting_role or None,
            "process_status": process_status or None,
        },
    }), 200


@dashboard_bp.get("/lp-circulation")
def lp_circulation_register():
    """Return all KHS records with an LP milestone, including legacy partial histories."""
    try:
        page = _register_positive_int("page", 1)
        per_page = _register_positive_int("per_page", 25, maximum=100)
    except ValueError as exc:
        return jsonify(success=False, code="INVALID_PAGINATION", message=str(exc)), 400

    search = request.args.get("q", "").strip()
    if len(search) > 100:
        return jsonify(success=False, code="INVALID_SEARCH", message="Search query must not exceed 100 characters."), 400

    stage = request.args.get("stage", "").strip().lower()
    if stage and stage not in LP_STAGE_FILTERS:
        return jsonify(success=False, code="INVALID_LP_STAGE", message="Unsupported LP circulation stage."), 400

    lp_record_condition = """
        (
            register.lp_circulation_start_date IS NOT NULL
            OR register.lp_contract_team_completion_date IS NOT NULL
            OR register.lp_junior_manager_approval_date IS NOT NULL
            OR register.lp_senior_manager_approval_date IS NOT NULL
            OR register.lp_gm_scm_approval_date IS NOT NULL
            OR register.lp_completion_date IS NOT NULL
        )
    """
    filters = [lp_record_condition]
    params = []
    if stage == "legacy_incomplete":
        # This is a history-quality filter, not an operational stage. Include
        # completed legacy records whose intermediate dates were never captured.
        filters.append("register.lp_timeline_has_gaps IS TRUE")
    elif stage == "prerequisite_exception":
        # Include Director-signed and active LPs with a missing/late MI GM date.
        filters.append("register.lp_started_without_mi_gm_approval IS TRUE")
    elif stage:
        filters.append("register.lp_stage_key = %s")
        params.append(stage)
    if search:
        filters.append("""
            (
                register.khs_id ILIKE %s
                OR register.request_id ILIKE %s
                OR register.vendor_name ILIKE %s
                OR COALESCE(register.request_subject, '') ILIKE %s
            )
        """)
        params.extend([f"%{search}%"] * 4)

    where_sql = "WHERE " + " AND ".join(filters)
    offset = (page - 1) * per_page

    count_query = f"""
        SELECT COUNT(*) AS total
        FROM ({REGISTER_BASE_QUERY}) AS register
        {where_sql}
    """
    data_query = f"""
        SELECT *
        FROM ({REGISTER_BASE_QUERY}) AS register
        {where_sql}
        ORDER BY
            CASE register.lp_stage_key
                WHEN 'prerequisite_exception' THEN 0
                WHEN 'legacy_unverified' THEN 1
                WHEN 'legacy_incomplete' THEN 2
                WHEN 'contract_team' THEN 3
                WHEN 'junior_manager' THEN 4
                WHEN 'senior_manager' THEN 5
                WHEN 'general_manager' THEN 6
                WHEN 'director' THEN 7
                WHEN 'completed' THEN 8
                ELSE 9
            END,
            register.lp_circulation_start_date ASC NULLS FIRST,
            register.khs_id
        LIMIT %s OFFSET %s
    """
    summary_query = f"""
        SELECT
            register.lp_stage_key,
            COUNT(*)::int AS total,
            COUNT(*) FILTER (WHERE register.lp_timeline_has_gaps)::int AS timeline_gaps,
            COUNT(*) FILTER (
                WHERE register.lp_started_without_mi_gm_approval IS TRUE
            )::int AS prerequisite_exceptions
        FROM ({REGISTER_BASE_QUERY}) AS register
        WHERE {lp_record_condition}
          AND register.process_status = 'ACTIVE'
        GROUP BY register.lp_stage_key
    """

    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(count_query, params)
                total = cursor.fetchone()["total"]
                cursor.execute(data_query, [*params, per_page, offset])
                rows = cursor.fetchall()
                cursor.execute(summary_query)
                summary_rows = cursor.fetchall()

        stage_counts = {key: 0 for key in LP_STAGE_FILTERS}
        for row in summary_rows:
            stage_counts[row["lp_stage_key"]] = row["total"]
        # Count every timeline with missing historical milestones, including
        # completed records. This is a data-quality overlay, not a workflow stage.
        legacy_count = sum(row["timeline_gaps"] for row in summary_rows)
        prerequisite_count = sum(row["prerequisite_exceptions"] for row in summary_rows)
        stage_counts["legacy_incomplete"] = legacy_count
        total_pages = (total + per_page - 1) // per_page if total else 0
        return jsonify(
            success=True,
            data=[_register_enriched(row) for row in rows],
            summary={
                "total_lp_records": total,
                "by_stage": stage_counts,
                "legacy_timeline_gaps": legacy_count,
                "prerequisite_exceptions": prerequisite_count,
            },
            pagination={
                "page": page,
                "per_page": per_page,
                "total_records": total,
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
        ), 200
    except Exception:
        current_app.logger.exception("LP circulation register query failed.")
        return jsonify(
            success=False,
            code="LP_CIRCULATION_UNAVAILABLE",
            message="LP circulation data is temporarily unavailable.",
        ), 503


@dashboard_bp.get("/contracts/lifecycle")
def contract_lifecycle_register():
    """Monitor expiry only after a KHS has been fully injected."""
    try:
        page = _register_positive_int("page", 1)
        per_page = _register_positive_int("per_page", 25, maximum=100)
    except ValueError as exc:
        return jsonify(success=False, code="INVALID_PAGINATION", message=str(exc)), 400

    search = request.args.get("q", "").strip()
    if len(search) > 100:
        return jsonify(success=False, code="INVALID_SEARCH", message="Search query must not exceed 100 characters."), 400

    status = request.args.get("status", "").strip().lower()
    alert_statuses = set(CONTRACT_ALERT_LABELS) - {"not_fully_injected"}
    grouped_statuses = {
        "within_6m": {"prep_6m", "watch_3m", "urgent_1m", "urgent_14d", "critical_7d"},
        "within_3m": {"watch_3m", "urgent_1m", "urgent_14d", "critical_7d"},
        "within_1m": {"urgent_1m", "urgent_14d", "critical_7d"},
        "missing_dates": {"missing_dates", "invalid_dates"},
    }
    allowed_statuses = alert_statuses | set(grouped_statuses) | {"upcoming"}
    if status and status not in allowed_statuses:
        return jsonify(success=False, code="INVALID_CONTRACT_ALERT", message="Unsupported contract alert filter."), 400

    today = _jakarta_today()
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
                    SELECT
                        k.khs_id,
                        k.request_id,
                        r.request_subject,
                        k.vendor_name,
                        k.executor_code,
                        e.display_name AS executor_name,
                        k.contract_start_date,
                        k.contract_end_date,
                        k.khs_inject_completion_date
                    FROM khs_items k
                    JOIN khs_requests r ON r.request_id = k.request_id
                    LEFT JOIN khs_executors e ON e.executor_code = k.executor_code
                    WHERE k.khs_inject_completion_date IS NOT NULL
                      AND k.process_status = 'ACTIVE'
                    ORDER BY k.contract_end_date ASC NULLS FIRST, k.khs_id
                    """
                )
                source_rows = cursor.fetchall()

        records = []
        for row in source_rows:
            record = _row_dict(row)
            record.update(_contract_lifecycle_data(row, today))
            records.append(record)

        counts = {
            key: sum(1 for row in records if row["contract_lifecycle_status"] == key)
            for key in allowed_statuses
        }
        expiring_6m = {"prep_6m", "watch_3m", "urgent_1m", "urgent_14d", "critical_7d"}
        expiring_3m = {"watch_3m", "urgent_1m", "urgent_14d", "critical_7d"}
        expiring_1m = {"urgent_1m", "urgent_14d", "critical_7d"}
        summary = {
            "as_of_date": today.isoformat(),
            "total_fully_injected": len(records),
            "expiring_within_6_months": sum(counts[key] for key in expiring_6m),
            "expiring_within_3_months": sum(counts[key] for key in expiring_3m),
            "expiring_within_1_month": sum(counts[key] for key in expiring_1m),
            "urgent_within_14_days": counts["urgent_14d"] + counts["critical_7d"],
            "critical_within_7_days": counts["critical_7d"],
            "expired": counts["expired"],
            "upcoming_contracts": sum(1 for row in records if row["contract_operational_status"] == "upcoming"),
            "active_contracts": sum(1 for row in records if row["contract_operational_status"] == "active"),
            "missing_contract_dates": counts["missing_dates"] + counts["invalid_dates"],
            "active_over_6_months": counts["active"],
            "by_status": counts,
        }

        filtered = records
        if status == "upcoming":
            filtered = [
                row for row in filtered
                if row["contract_operational_status"] == "upcoming"
            ]
        elif status:
            accepted_statuses = grouped_statuses.get(status, {status})
            filtered = [
                row for row in filtered
                if row["contract_lifecycle_status"] in accepted_statuses
            ]
        if search:
            needle = search.casefold()
            filtered = [
                row for row in filtered
                if needle in str(row.get("khs_id") or "").casefold()
                or needle in str(row.get("request_id") or "").casefold()
                or needle in str(row.get("request_subject") or "").casefold()
                or needle in str(row.get("vendor_name") or "").casefold()
            ]

        priority = {
            "expired": 0, "critical_7d": 1, "urgent_14d": 2, "urgent_1m": 3,
            "watch_3m": 4, "prep_6m": 5, "missing_dates": 6,
            "invalid_dates": 7, "active": 8,
        }
        filtered.sort(key=lambda row: (
            priority.get(row["contract_lifecycle_status"], 9),
            row.get("contract_end_date") or "9999-12-31",
            row.get("khs_id") or "",
        ))
        total = len(filtered)
        total_pages = (total + per_page - 1) // per_page if total else 0
        start = (page - 1) * per_page
        return jsonify(
            success=True,
            data=filtered[start:start + per_page],
            summary=summary,
            pagination={
                "page": page,
                "per_page": per_page,
                "total_records": total,
                "total_pages": total_pages,
                "has_previous": page > 1,
                "has_next": page < total_pages,
            },
        ), 200
    except Exception:
        current_app.logger.exception("Contract lifecycle query failed.")
        return jsonify(
            success=False,
            code="CONTRACT_LIFECYCLE_UNAVAILABLE",
            message="Contract lifecycle data is temporarily unavailable.",
        ), 503


# ----------------------- Operational management API -----------------------

REQUEST_FIELDS = {"request_date", "request_subject", "requester_owner"}
ITEM_FIELDS = {
    "request_id", "vendor_name", "executor_code", "subtype",
    "dispatch_date", "contract_start_date", "contract_end_date",
    "boq_confirmation_date", "negotiation_date", "final_negotiation_date",
    "mi_head_approval_date", "mi_sm_approval_date", "mi_gm_approval_date",
    "legal_submission_date", "lp_circulation_start_date",
    "lp_contract_team_completion_date", "lp_junior_manager_approval_date",
    "lp_senior_manager_approval_date", "lp_gm_scm_approval_date", "lp_completion_date",
    "khs_inject_start_date", "khs_inject_completion_date",
    "waiting_for", "waiting_reason", "action_owner", "last_updated_date", "remarks",
}
DATE_FIELDS = {
    "request_date", "dispatch_date", "contract_start_date", "contract_end_date",
    "boq_confirmation_date", "negotiation_date", "final_negotiation_date",
    "mi_head_approval_date", "mi_sm_approval_date", "mi_gm_approval_date",
    "legal_submission_date", "lp_circulation_start_date",
    "lp_contract_team_completion_date", "lp_junior_manager_approval_date",
    "lp_senior_manager_approval_date", "lp_gm_scm_approval_date", "lp_completion_date",
    "khs_inject_start_date", "khs_inject_completion_date",
    "last_updated_date", "closure_date", "milestone_date", "due_date",
}
TEXT_LIMITS = {
    "request_id": 64, "request_subject": 300, "requester_owner": 160,
    "khs_id": 64, "vendor_name": 240, "executor_code": 32, "waiting_for": 160,
    "waiting_reason": 1000, "action_owner": 160, "remarks": 2000,
    "note": 1000, "follow_up_to": 160,
    "closure_reason_code": 64, "closure_notes": 2000, "reopen_reason": 1000,
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{1,63}$")


def _body_object():
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return None
    return body


def _validate_payload(data, allowed, required):
    if not isinstance(data, dict):
        raise ValueError("A JSON object is required.")
    unknown = set(data) - allowed
    if unknown:
        raise ValueError(f"Unsupported fields: {', '.join(sorted(unknown))}.")
    normalized = {}
    for key, value in data.items():
        if key in DATE_FIELDS:
            if value in (None, ""):
                normalized[key] = None
            else:
                try:
                    normalized[key] = date.fromisoformat(str(value))
                except (TypeError, ValueError):
                    raise ValueError(f"{key} must use YYYY-MM-DD.")
        elif key in TEXT_LIMITS:
            if value is None:
                normalized[key] = None
                continue
            if not isinstance(value, str):
                raise ValueError(f"{key} must be text.")
            value = value.strip()
            if len(value) > TEXT_LIMITS[key]:
                raise ValueError(f"{key} exceeds {TEXT_LIMITS[key]} characters.")
            normalized[key] = value or None
        else:
            normalized[key] = value
    missing = [field for field in required if not normalized.get(field)]
    if missing:
        raise ValueError(f"Required fields: {', '.join(missing)}.")
    for key in ("request_id", "khs_id"):
        if key in normalized and normalized[key] and not ID_PATTERN.fullmatch(normalized[key]):
            raise ValueError(f"{key} contains unsupported characters.")
    if "executor_code" in normalized and normalized["executor_code"]:
        normalized["executor_code"] = normalized["executor_code"].upper()
    if "subtype" in normalized and normalized["subtype"] not in (None, "Renewal", "Kontrak Baru"):
        raise ValueError("Subtype must be Renewal or Kontrak Baru.")
    return normalized


def _json_safe_value(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return value


def _audit(conn, entity_type, entity_id, action, before, after):
    changes = {}
    for key in sorted(set(before or {}) | set(after or {})):
        old = _json_safe_value((before or {}).get(key))
        new = _json_safe_value((after or {}).get(key))
        if old != new:
            changes[key] = {"before": old, "after": new}
    if action == "CREATED":
        changes = {"after": _json_safe_value(after or {})}
    if not changes and action != "CREATED":
        return False
    conn.execute(
        """INSERT INTO khs_activity_logs
           (entity_type, entity_id, action, actor, changes)
           VALUES (%s, %s, %s, %s, %s)""",
        (entity_type, entity_id, action, "manual-entry", Jsonb(changes)),
    )
    return True


def _row_dict(row):
    return {key: _json_safe_value(value) for key, value in row.items()}


def _next_generated_id(conn, table, column, prefix, width):
    # Table and column are internal constants, never request input.
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (prefix,))
    row = conn.execute(
        f"SELECT {column} FROM {table} WHERE {column} LIKE %s ORDER BY {column} DESC LIMIT 1",
        (prefix + "%",),
    ).fetchone()
    number = 1
    if row:
        try:
            number = int(str(row[0]).rsplit("-", 1)[-1]) + 1
        except (TypeError, ValueError):
            raise RuntimeError("Unable to generate a safe record identifier.")
    return prefix + str(number).zfill(width)


@dashboard_bp.get("/requests")
def request_register():
    try:
        page = _register_positive_int("page", 1)
        per_page = _register_positive_int("per_page", 25, maximum=100)
    except ValueError as exc:
        return jsonify(success=False, code="INVALID_PAGINATION", message=str(exc)), 400

    q = request.args.get("q", "").strip()
    if len(q) > 100:
        return jsonify(success=False, code="INVALID_SEARCH", message="Search query is too long."), 400

    where = ""
    params = []
    if q:
        where = """
            WHERE (
                r.request_id ILIKE %s
                OR r.request_subject ILIKE %s
                OR COALESCE(r.requester_owner, '') ILIKE %s
                OR EXISTS (
                    SELECT 1 FROM khs_items search_item
                    WHERE search_item.request_id = r.request_id
                      AND search_item.vendor_name ILIKE %s
                )
            )
        """
        params = [f"%{q}%"] * 4

    try:
        with get_db_pool().connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM khs_requests r {where}", params
            ).fetchone()[0]
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    f"""
                    SELECT
                        r.request_id,
                        r.request_date,
                        r.request_subject,
                        r.requester_owner,
                        COUNT(k.khs_id)::int AS total_khs,
                        COUNT(k.khs_id) FILTER (
                            WHERE k.khs_inject_completion_date IS NOT NULL
                        )::int AS completed_khs,
                        COUNT(k.khs_id) FILTER (
                            WHERE k.process_status = 'ACTIVE'
                              AND k.khs_inject_completion_date IS NULL
                        )::int AS open_khs,
                        COUNT(k.khs_id) FILTER (
                            WHERE k.process_status = 'NOT_PROCEEDED'
                        )::int AS not_proceeded_khs,
                        COALESCE(
                            string_agg(DISTINCT k.vendor_name, ' · ' ORDER BY k.vendor_name)
                                FILTER (WHERE k.vendor_name IS NOT NULL),
                            ''
                        ) AS vendor_summary,
                        COALESCE(
                            array_agg(DISTINCT k.vendor_name ORDER BY k.vendor_name)
                                FILTER (WHERE k.vendor_name IS NOT NULL),
                            ARRAY[]::text[]
                        ) AS vendors,
                        r.created_at,
                        r.updated_at
                    FROM khs_requests r
                    LEFT JOIN khs_items k ON k.request_id = r.request_id
                    {where}
                    GROUP BY r.request_id
                    ORDER BY r.request_date DESC NULLS LAST, r.request_subject
                    LIMIT %s OFFSET %s
                    """,
                    [*params, per_page, (page - 1) * per_page],
                )
                rows = cursor.fetchall()

        return jsonify(
            success=True,
            data=[_row_dict(x) for x in rows],
            pagination={
                "page": page,
                "per_page": per_page,
                "total_records": total,
                "total_pages": (total + per_page - 1) // per_page if total else 0,
            },
        ), 200
    except Exception:
        current_app.logger.exception("Request register query failed.")
        return jsonify(
            success=False,
            code="REQUEST_REGISTER_UNAVAILABLE",
            message="Request register is temporarily unavailable.",
        ), 503


@dashboard_bp.post("/requests")
def create_request():
    body = _body_object()
    if body is None:
        return jsonify(success=False, message="A JSON object is required."), 400
    try:
        data = _validate_payload(body, REQUEST_FIELDS | {"request_id"}, {"request_subject"})
        with get_db_pool().connection() as conn, conn.transaction():
            if not data.get("request_id"):
                data["request_id"] = _next_generated_id(
                    conn, "khs_requests", "request_id", f"REQ-{datetime.now(ZoneInfo('Asia/Jakarta')).year}-", 3
                )
            row = conn.execute(
                """INSERT INTO khs_requests(request_id,request_date,request_subject,requester_owner)
                   VALUES(%s,%s,%s,%s)
                   RETURNING request_id,request_date,request_subject,requester_owner""",
                (data["request_id"],data.get("request_date"),data["request_subject"],data.get("requester_owner")),
            ).fetchone()
            _audit(conn,"REQUEST",data["request_id"],"CREATED",{},data)
        return jsonify(success=True,data=_row_dict(dict(zip(("request_id","request_date","request_subject","requester_owner"),row)))),201
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    except Exception as exc:
        if "unique" in str(exc).lower():
            return jsonify(success=False,code="REQUEST_EXISTS",message="Request ID already exists."),409
        current_app.logger.exception("Request creation failed.")
        return jsonify(success=False,message="Unable to create request."),500


@dashboard_bp.patch("/requests/<path:request_id>")
def update_request(request_id):
    body = _body_object()
    if body is None:
        return jsonify(success=False,message="A JSON object is required."),400
    try:
        data = _validate_payload(body,REQUEST_FIELDS, set())
        if not data:
            return jsonify(success=False,message="No fields to update."),400
        if "request_subject" in data and not data["request_subject"]:
            return jsonify(success=False,message="Request subject cannot be blank."),400
        with get_db_pool().connection() as conn, conn.transaction():
            cols = tuple(data)
            oldrow = conn.execute("SELECT request_date,request_subject,requester_owner FROM khs_requests WHERE request_id=%s FOR UPDATE",(request_id,)).fetchone()
            if oldrow is None:
                return jsonify(success=False,message="Request not found."),404
            before=dict(zip(("request_date", "request_subject", "requester_owner"),oldrow))
            conn.execute("UPDATE khs_requests SET "+", ".join(f"{c}=%s" for c in cols)+", updated_at=NOW() WHERE request_id=%s",
                         [data[c] for c in cols]+[request_id])
            after={**before,**data}
            changed=_audit(conn,"REQUEST",request_id,"UPDATED",before,after)
        return jsonify(success=True,changed=changed),200
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    except Exception:
        current_app.logger.exception("Request update failed.")
        return jsonify(success=False,message="Unable to update request."),500


@dashboard_bp.post("/khs")
def create_khs():
    body = _body_object()
    if body is None:
        return jsonify(success=False,message="A JSON object is required."),400
    try:
        data=_validate_payload(body,ITEM_FIELDS|{"khs_id"},{"request_id","vendor_name","executor_code"})
        with get_db_pool().connection() as conn, conn.transaction():
            if not data.get("khs_id"):
                data["khs_id"] = _next_generated_id(
                    conn, "khs_items", "khs_id", f"KHS-{datetime.now(ZoneInfo('Asia/Jakarta')).year}-", 4
                )
            exists=conn.execute("SELECT 1 FROM khs_requests WHERE request_id=%s",(data["request_id"],)).fetchone()
            if not exists:
                return jsonify(success=False,code="PARENT_REQUEST_NOT_FOUND",message="Create the parent request first."),422
            executor=conn.execute("SELECT 1 FROM khs_executors WHERE executor_code=%s AND is_active=TRUE",(data["executor_code"],)).fetchone()
            if not executor:
                return jsonify(success=False,code="INVALID_EXECUTOR",message="Select an active executor."),422
            if data.get("lp_circulation_start_date") and not data.get("mi_gm_approval_date"):
                return jsonify(success=False,code="MI_GM_REQUIRED",message="LP circulation cannot start before GM SCM MI approval."),422
            intermediate_lp_dates = (
                "lp_contract_team_completion_date",
                "lp_junior_manager_approval_date",
                "lp_senior_manager_approval_date",
                "lp_gm_scm_approval_date",
            )
            if any(data.get(field) for field in intermediate_lp_dates) and not data.get("lp_circulation_start_date"):
                return jsonify(success=False,code="LP_START_REQUIRED",message="LP milestone dates require an LP circulation start date."),422
            out_of_order_lp_field = _lp_date_order_error(data)
            if out_of_order_lp_field:
                return jsonify(success=False,code="LP_MILESTONE_CHRONOLOGY",message=f"{out_of_order_lp_field} cannot precede an earlier LP milestone."),422
            if data.get("lp_completion_date") and not data.get("lp_circulation_start_date"):
                return jsonify(success=False,code="LP_START_REQUIRED",message="LP completion requires circulation start."),422
            if data.get("lp_completion_date") and data.get("lp_circulation_start_date") and data["lp_completion_date"] < data["lp_circulation_start_date"]:
                return jsonify(success=False,code="LP_DATE_ORDER",message="LP completion cannot precede circulation start."),422
            if data.get("khs_inject_start_date") and not data.get("lp_completion_date"):
                return jsonify(success=False,code="LP_COMPLETION_REQUIRED",message="KHS injection can only start after LP completion."),422
            if data.get("khs_inject_start_date") and data.get("lp_completion_date") and data["khs_inject_start_date"] < data["lp_completion_date"]:
                return jsonify(success=False,code="INJECT_DATE_ORDER",message="KHS injection start cannot precede LP completion."),422
            if data.get("khs_inject_completion_date") and not data.get("khs_inject_start_date"):
                return jsonify(success=False,code="INJECT_START_REQUIRED",message="Fully injected completion requires an injection start date."),422
            if data.get("khs_inject_completion_date") and data.get("khs_inject_start_date") and data["khs_inject_completion_date"] < data["khs_inject_start_date"]:
                return jsonify(success=False,code="INJECT_COMPLETION_ORDER",message="KHS injection completion cannot precede injection start."),422
            if data.get("contract_start_date") and data.get("contract_end_date") and data["contract_end_date"] < data["contract_start_date"]:
                return jsonify(success=False,code="CONTRACT_DATE_ORDER",message="Contract end date cannot precede contract start date."),422
            cols=tuple(data)
            conn.execute("INSERT INTO khs_items("+", ".join(cols)+") VALUES("+", ".join(["%s"]*len(cols))+")",
                         [data[c] for c in cols])
            _audit(conn,"KHS_ITEM",data["khs_id"],"CREATED",{},data)
        return jsonify(success=True,data={"khs_id":data["khs_id"]}),201
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    except Exception as exc:
        if "unique" in str(exc).lower():
            return jsonify(success=False,code="KHS_EXISTS",message="KHS ID already exists."),409
        current_app.logger.exception("KHS creation failed.")
        return jsonify(success=False,message="Unable to create KHS."),500


@dashboard_bp.get("/khs/<path:khs_id>")
def khs_detail(khs_id):
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(REGISTER_BASE_QUERY + " WHERE k.khs_id=%s", (khs_id,))
                item = cur.fetchone()
                if item is None:
                    return jsonify(success=False, message="KHS not found."), 404

                cur.execute(
                    """SELECT id, entity_type, entity_id, action, actor, changes, occurred_at
                       FROM khs_activity_logs
                       WHERE entity_type='KHS_ITEM' AND entity_id=%s
                       ORDER BY occurred_at DESC, id DESC LIMIT 50""",
                    (khs_id,),
                )
                history = cur.fetchall()

                cur.execute(
                    """SELECT id, stage_code, due_date, follow_up_to, note, status,
                              created_at, created_by, completed_at, completed_by
                       FROM khs_follow_ups
                       WHERE khs_id=%s
                       ORDER BY CASE WHEN status='OPEN' THEN 0 ELSE 1 END,
                                due_date ASC, id DESC""",
                    (khs_id,),
                )
                follow_ups = cur.fetchall()

                cur.execute(
                    """SELECT id, document_type, original_file_name, mime_type,
                              uploaded_by, uploaded_at
                       FROM khs_documents
                       WHERE khs_id=%s
                       ORDER BY uploaded_at DESC, id DESC""",
                    (khs_id,),
                )
                documents = cur.fetchall()

        document_rows = []
        for document in documents:
            row = _row_dict(document)
            row["download_url"] = f"/api/dashboard/documents/{row['id']}/download"
            document_rows.append(row)

        return jsonify(
            success=True,
            data=_register_enriched(item, include_duration_history=True),
            history=[_row_dict(x) for x in history],
            follow_ups=[_row_dict(x) for x in follow_ups],
            documents=document_rows,
        ), 200
    except Exception:
        current_app.logger.exception("KHS detail query failed.")
        return jsonify(success=False, message="Unable to load KHS detail."), 503


ALLOWED_DOCUMENT_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"
}


@dashboard_bp.post("/khs/<path:khs_id>/documents")
def upload_khs_document(khs_id):
    uploaded = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return jsonify(success=False, message="Choose a document to upload."), 400

    original_name = secure_filename(Path(uploaded.filename.replace("\\", "/")).name)
    extension = Path(original_name).suffix.lower()
    if not original_name or extension not in ALLOWED_DOCUMENT_EXTENSIONS:
        return jsonify(
            success=False,
            message="Supported formats: PDF, DOC/DOCX, XLS/XLSX, PNG, JPG, JPEG.",
        ), 400

    document_type = (request.form.get("document_type") or "KHS Evidence").strip()
    if not document_type or len(document_type) > 80:
        return jsonify(success=False, message="Document type must be 1–80 characters."), 400

    max_bytes = int(current_app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))
    payload = uploaded.stream.read(max_bytes + 1)
    if not payload:
        return jsonify(success=False, message="The uploaded file is empty."), 400
    if len(payload) > max_bytes:
        return jsonify(success=False, message="File exceeds the permitted upload size."), 413

    upload_root = Path(current_app.config["UPLOAD_DIR"]).resolve()
    storage_key = (Path("khs-documents") / f"{uuid4().hex}{extension}").as_posix()
    target = (upload_root / storage_key).resolve()
    if not target.is_relative_to(upload_root):
        return jsonify(success=False, message="Invalid storage location."), 400

    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    target.parent.chmod(0o700)
    digest = hashlib.sha256(payload).hexdigest()
    mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    target.write_bytes(payload)
    target.chmod(0o600)

    try:
        with get_db_pool().connection() as conn, conn.transaction():
            exists = conn.execute(
                "SELECT 1 FROM khs_items WHERE khs_id=%s",
                (khs_id,),
            ).fetchone()
            if not exists:
                target.unlink(missing_ok=True)
                return jsonify(success=False, message="KHS not found."), 404

            document = conn.execute(
                """INSERT INTO khs_documents (
                       khs_id, document_type, original_file_name, storage_key,
                       mime_type, file_sha256, uploaded_by
                   )
                   VALUES (%s, %s, %s, %s, %s, %s, %s)
                   RETURNING id, document_type, original_file_name, mime_type, uploaded_at""",
                (khs_id, document_type, original_name, storage_key, mime_type, digest, "manual-entry"),
            ).fetchone()

            document_id, saved_type, saved_name, saved_mime, uploaded_at = document
            _audit(
                conn,
                "KHS_ITEM",
                khs_id,
                "DOCUMENT_UPLOADED",
                {},
                {"document_id": document_id, "document_type": saved_type, "file_name": saved_name},
            )
        return jsonify(
            success=True,
            data={
                "id": document_id,
                "document_type": saved_type,
                "original_file_name": saved_name,
                "mime_type": saved_mime,
                "uploaded_at": uploaded_at.isoformat(),
                "download_url": f"/api/dashboard/documents/{document_id}/download",
            },
        ), 201
    except Exception:
        target.unlink(missing_ok=True)
        current_app.logger.exception("KHS document upload failed.")
        return jsonify(success=False, message="Unable to save KHS evidence document."), 500


@dashboard_bp.get("/documents/<int:document_id>/download")
def download_khs_document(document_id):
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """SELECT original_file_name, storage_key, mime_type
                       FROM khs_documents WHERE id=%s""",
                    (document_id,),
                )
                document = cursor.fetchone()
        if document is None:
            return jsonify(success=False, message="Document not found."), 404

        upload_root = Path(current_app.config["UPLOAD_DIR"]).resolve()
        file_path = (upload_root / document["storage_key"]).resolve()
        if not file_path.is_relative_to(upload_root) or not file_path.is_file():
            return jsonify(success=False, message="Stored document is unavailable."), 404

        response = send_file(
            file_path,
            mimetype=document["mime_type"] or "application/octet-stream",
            as_attachment=True,
            download_name=document["original_file_name"],
            conditional=True,
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception:
        current_app.logger.exception("KHS document download failed.")
        return jsonify(success=False, message="Unable to download KHS document."), 500


@dashboard_bp.patch("/khs/<path:khs_id>")
def update_khs(khs_id):
    body=_body_object()
    if body is None:
        return jsonify(success=False,message="A JSON object is required."),400
    try:
        data=_validate_payload(body,ITEM_FIELDS,set())
        if not data:
            return jsonify(success=False,message="No fields to update."),400
        if "vendor_name" in data and not data["vendor_name"]:
            return jsonify(success=False,message="Vendor name cannot be blank."),400
        with get_db_pool().connection() as conn, conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM khs_items WHERE khs_id=%s FOR UPDATE",(khs_id,))
                before=cur.fetchone()
                if before is None:
                    return jsonify(success=False,message="KHS not found."),404
                before=dict(before)
                cur.execute(REGISTER_BASE_QUERY + " WHERE k.khs_id=%s", (khs_id,))
                before_derived = cur.fetchone()
            if before.get("process_status") == "NOT_PROCEEDED":
                return jsonify(success=False, code="KHS_CLOSED",
                               message="Reopen this KHS before editing its milestones."),409
            merged={**before,**data}
            if "request_id" in data:
                parent = conn.execute("SELECT 1 FROM khs_requests WHERE request_id=%s", (data["request_id"],)).fetchone()
                if not parent:
                    return jsonify(success=False,code="PARENT_REQUEST_NOT_FOUND",message="Parent request does not exist."),422
            historic_lp_exception = bool(before.get("lp_circulation_start_date") and not before.get("mi_gm_approval_date"))
            lp_start_changed = ("lp_circulation_start_date" in data and data["lp_circulation_start_date"] != before.get("lp_circulation_start_date"))
            gm_approval_cleared = ("mi_gm_approval_date" in data and data["mi_gm_approval_date"] is None)
            if merged.get("lp_circulation_start_date") and not merged.get("mi_gm_approval_date") and (not historic_lp_exception or lp_start_changed or gm_approval_cleared):
                return jsonify(success=False,code="MI_GM_REQUIRED",message="LP circulation cannot start before GM SCM MI approval."),422
            lp_update_error = _lp_milestone_update_error(before, data)
            if lp_update_error:
                code, message = lp_update_error
                return jsonify(success=False, code=code, message=message), 422
            if merged.get("khs_inject_start_date") and not merged.get("lp_completion_date"):
                return jsonify(success=False,code="LP_COMPLETION_REQUIRED",message="KHS injection can only start after LP completion."),422
            if merged.get("khs_inject_start_date") and merged.get("lp_completion_date") and merged["khs_inject_start_date"] < merged["lp_completion_date"]:
                return jsonify(success=False,code="INJECT_DATE_ORDER",message="KHS injection start cannot precede LP completion."),422
            if merged.get("khs_inject_completion_date") and not merged.get("khs_inject_start_date"):
                return jsonify(success=False,code="INJECT_START_REQUIRED",message="Fully injected completion requires an injection start date."),422
            if merged.get("khs_inject_completion_date") and merged.get("khs_inject_start_date") and merged["khs_inject_completion_date"] < merged["khs_inject_start_date"]:
                return jsonify(success=False,code="INJECT_COMPLETION_ORDER",message="KHS injection completion cannot precede injection start."),422
            contract_dates_changed = any(
                field in data and data[field] != before.get(field)
                for field in ("contract_start_date", "contract_end_date")
            )
            if contract_dates_changed and merged.get("contract_start_date") and merged.get("contract_end_date") and merged["contract_end_date"] < merged["contract_start_date"]:
                return jsonify(success=False,code="CONTRACT_DATE_ORDER",message="Contract end date cannot precede contract start date."),422
            if "executor_code" in data:
                active=conn.execute("SELECT 1 FROM khs_executors WHERE executor_code=%s AND is_active=TRUE",(data["executor_code"],)).fetchone()
                if not active:
                    return jsonify(success=False,code="INVALID_EXECUTOR",message="Select an active executor."),422
            cols=tuple(data)
            conn.execute("UPDATE khs_items SET "+", ".join(f"{c}=%s" for c in cols)+", updated_at=NOW(),last_updated_date=CURRENT_DATE WHERE khs_id=%s",
                         [data[c] for c in cols]+[khs_id])
            after={**before,**data}
            _audit(conn,"KHS_ITEM",khs_id,"UPDATED",before,after)
            if before_derived:
                cur.execute(REGISTER_BASE_QUERY + " WHERE k.khs_id=%s", (khs_id,))
                after_derived = cur.fetchone()
                if after_derived and before_derived["workflow_stage_code"] != after_derived["workflow_stage_code"]:
                    conn.execute(
                        """UPDATE khs_follow_ups
                           SET status='SUPERSEDED', cancelled_at=NOW(), cancelled_by='system'
                           WHERE khs_id=%s AND stage_code=%s AND status='OPEN'""",
                        (khs_id, before_derived["workflow_stage_code"]),
                    )
        return jsonify(success=True,message="KHS updated."),200
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    except Exception:
        current_app.logger.exception("KHS update failed.")
        return jsonify(success=False,message="Unable to update KHS."),500




@dashboard_bp.post("/khs/<path:khs_id>/progress")
def update_khs_guided_progress(khs_id):
    body = _body_object()
    if body is None:
        return jsonify(success=False, message="A JSON object is required."),400
    try:
        payload = _validate_payload(body, {"milestone_date", "note"}, {"milestone_date"})
        milestone_date = payload["milestone_date"]
        if milestone_date > _jakarta_today():
            return jsonify(success=False, code="FUTURE_MILESTONE_DATE",
                           message="Milestone date cannot be in the future."),422
        with get_db_pool().connection() as conn, conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT process_status FROM khs_items WHERE khs_id=%s FOR UPDATE", (khs_id,))
                locked = cur.fetchone()
                if locked is None:
                    return jsonify(success=False, message="KHS not found."),404
                if locked["process_status"] != "ACTIVE":
                    return jsonify(success=False, code="KHS_NOT_ACTIVE",
                                   message="Only active KHS records can receive progress updates."),409
                cur.execute(REGISTER_BASE_QUERY + " WHERE k.khs_id=%s", (khs_id,))
                record = cur.fetchone()
                if record is None:
                    return jsonify(success=False, message="KHS not found."),404
                record = dict(record)
            definition = _guided_progress_definition(record)
            if not definition:
                return jsonify(success=False, code="NO_GUIDED_MILESTONE",
                               message="There is no pending guided milestone for this KHS."),409
            field = definition["field"]
            chronology_error = _guided_progress_date_error(record, field, milestone_date)
            if chronology_error:
                code, message = chronology_error
                return jsonify(success=False, code=code, message=message),422
            conn.execute(
                f"UPDATE khs_items SET {field}=%s, updated_at=NOW(), last_updated_date=CURRENT_DATE WHERE khs_id=%s",
                (milestone_date, khs_id),
            )
            after = {**record, field: milestone_date}
            if payload.get("note"):
                after["_progress_note"] = payload["note"]
            _audit(conn, "KHS_ITEM", khs_id, "PROGRESS_UPDATED", record, after)
            conn.execute(
                """UPDATE khs_follow_ups
                   SET status='SUPERSEDED', cancelled_at=NOW(), cancelled_by='system'
                   WHERE khs_id=%s AND stage_code=%s AND status='OPEN'""",
                (khs_id, definition["stage_code"]),
            )
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(REGISTER_BASE_QUERY + " WHERE k.khs_id=%s", (khs_id,))
                updated = cur.fetchone()
        return jsonify(success=True, message="Progress updated.",
                       data=_register_enriched(updated, include_duration_history=True)),200
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)),400
    except Exception:
        current_app.logger.exception("Guided KHS progress update failed.")
        return jsonify(success=False, code="GUIDED_PROGRESS_UNAVAILABLE",
                       message="Unable to update KHS progress."),500


KHS_CLOSURE_REASON_CODES = {
    "NO_MUTUAL_AGREEMENT", "REQUESTER_WITHDRAWAL", "VENDOR_DECLINED",
    "INTERNAL_REJECTION", "DUPLICATE", "OTHER",
}


@dashboard_bp.post("/khs/<path:khs_id>/close")
def close_khs(khs_id):
    body = _body_object()
    if body is None:
        return jsonify(success=False, message="A JSON object is required."),400
    try:
        data = _validate_payload(body, {"closure_date", "closure_reason_code", "closure_notes"},
                                 {"closure_date", "closure_reason_code"})
        reason_code = data["closure_reason_code"].upper()
        if reason_code not in KHS_CLOSURE_REASON_CODES:
            return jsonify(success=False, code="INVALID_CLOSURE_REASON",
                           message="Select a supported closure reason."),422
        closure_date = data["closure_date"]
        if closure_date > _jakarta_today():
            return jsonify(success=False, code="FUTURE_CLOSURE_DATE",
                           message="Closure date cannot be in the future."),422
        if reason_code == "OTHER" and not data.get("closure_notes"):
            return jsonify(success=False, code="CLOSURE_NOTES_REQUIRED",
                           message="Add a note when selecting Other."),422
        milestone_fields = (
            "dispatch_date", "boq_confirmation_date", "negotiation_date",
            "final_negotiation_date", "mi_head_approval_date", "mi_sm_approval_date",
            "mi_gm_approval_date", "legal_submission_date", "lp_circulation_start_date",
            "lp_contract_team_completion_date", "lp_junior_manager_approval_date",
            "lp_senior_manager_approval_date", "lp_gm_scm_approval_date",
            "lp_completion_date", "khs_inject_start_date",
        )
        with get_db_pool().connection() as conn, conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT k.*, r.request_date AS parent_request_date
                       FROM khs_items k
                       JOIN khs_requests r ON r.request_id = k.request_id
                       WHERE k.khs_id=%s
                       FOR UPDATE OF k""",
                    (khs_id,),
                )
                before = cur.fetchone()
                if before is None:
                    return jsonify(success=False, message="KHS not found."),404
                before = dict(before)
            if before.get("process_status") == "NOT_PROCEEDED":
                return jsonify(success=False, code="KHS_ALREADY_CLOSED",
                               message="This KHS is already marked as Not Proceeded."),409
            if before.get("khs_inject_completion_date"):
                return jsonify(success=False, code="KHS_ALREADY_INJECTED",
                               message="A fully injected KHS cannot be closed as Not Proceeded."),409
            parent_request_date = _date_only(before.get("parent_request_date"))
            if parent_request_date and closure_date < parent_request_date:
                return jsonify(success=False, code="CLOSURE_DATE_BEFORE_REQUEST",
                               message="Closure date cannot precede the original request date."),422
            recorded_dates = [_date_only(before.get(field)) for field in milestone_fields]
            recorded_dates = [value for value in recorded_dates if value is not None]
            if recorded_dates and closure_date < max(recorded_dates):
                return jsonify(success=False, code="CLOSURE_DATE_BEFORE_LAST_MILESTONE",
                               message="Closure date cannot precede the latest recorded milestone."),422
            after = {**before, "process_status": "NOT_PROCEEDED",
                     "closure_date": closure_date, "closure_reason_code": reason_code,
                     "closure_notes": data.get("closure_notes"), "closed_by": "manual-entry"}
            conn.execute(
                """UPDATE khs_items SET process_status='NOT_PROCEEDED', closure_date=%s,
                   closure_reason_code=%s, closure_notes=%s, closed_at=NOW(),
                   closed_by='manual-entry', updated_at=NOW(), last_updated_date=CURRENT_DATE
                   WHERE khs_id=%s""",
                (closure_date, reason_code, data.get("closure_notes"), khs_id),
            )
            conn.execute(
                """UPDATE khs_follow_ups
                   SET status='SUPERSEDED', cancelled_at=NOW(), cancelled_by='system'
                   WHERE khs_id=%s AND status='OPEN'""",
                (khs_id,),
            )
            _audit(conn, "KHS_ITEM", khs_id, "CLOSED_NOT_PROCEEDED", before, after)
        return jsonify(success=True, message="KHS closed as Not Proceeded."),200
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)),400
    except Exception:
        current_app.logger.exception("KHS closure failed.")
        return jsonify(success=False, code="KHS_CLOSURE_UNAVAILABLE",
                       message="Unable to close KHS."),500


@dashboard_bp.post("/khs/<path:khs_id>/reopen")
def reopen_khs(khs_id):
    body = _body_object()
    if body is None:
        return jsonify(success=False, message="A JSON object is required."),400
    try:
        data = _validate_payload(body, {"reopen_reason"}, {"reopen_reason"})
        with get_db_pool().connection() as conn, conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT * FROM khs_items WHERE khs_id=%s FOR UPDATE", (khs_id,))
                before = cur.fetchone()
                if before is None:
                    return jsonify(success=False, message="KHS not found."),404
                before = dict(before)
            if before.get("process_status") != "NOT_PROCEEDED":
                return jsonify(success=False, code="KHS_NOT_CLOSED",
                               message="Only a Not Proceeded KHS can be reopened."),409
            after = {**before, "process_status": "ACTIVE",
                     "reopen_reason": data["reopen_reason"], "reopened_by": "manual-entry"}
            conn.execute(
                """UPDATE khs_items SET process_status='ACTIVE', reopened_at=NOW(),
                   reopened_by='manual-entry', reopen_reason=%s,
                   updated_at=NOW(), last_updated_date=CURRENT_DATE WHERE khs_id=%s""",
                (data["reopen_reason"], khs_id),
            )
            _audit(conn, "KHS_ITEM", khs_id, "REOPENED", before, after)
        return jsonify(success=True, message="KHS reopened."),200
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)),400
    except Exception:
        current_app.logger.exception("KHS reopening failed.")
        return jsonify(success=False, code="KHS_REOPEN_UNAVAILABLE",
                       message="Unable to reopen KHS."),500


@dashboard_bp.get("/workflow")
def workflow_monitoring():
    # Use the Jakarta-local date so stage age is not affected by the database
    # server timezone. Each age is anchored to the milestone that opened the
    # current workflow stage; updated_at is deliberately not used as a proxy.
    as_of = _jakarta_today().isoformat()
    as_of_sql = f"DATE '{as_of}'"
    query = """
        WITH register_state AS (
            SELECT
                derived_register.*,
                derived_register.current_stage_started_on AS stage_started_on
            FROM (""" + REGISTER_BASE_QUERY + """) AS derived_register
        )
        SELECT
            stage.stage_code,
            stage.stage_name,
            stage.sequence_number,
            COUNT(register.khs_id)::int AS total,
            COUNT(register.khs_id) FILTER (
                WHERE register.workflow_status = 'completed'
            )::int AS completed,
            MAX(
                CASE
                    WHEN register.process_status = 'ACTIVE'
                     AND register.stage_started_on <= """ + as_of_sql + """
                    THEN """ + as_of_sql + """ - register.stage_started_on
                    ELSE NULL
                END
            )::int AS oldest_stage_age_days,
            COUNT(register.khs_id) FILTER (
                WHERE stage.stage_code NOT IN ('COMPLETED', 'NOT_PROCEEDED')
                  AND register.process_status = 'ACTIVE'
                  AND (
                      register.stage_started_on IS NULL
                      OR register.stage_started_on > """ + as_of_sql + """
                  )
            )::int AS stage_age_unavailable
        FROM khs_stage_config stage
        LEFT JOIN register_state AS register
          ON register.current_stage_code = stage.stage_code
        WHERE stage.is_active = TRUE
        GROUP BY stage.stage_code, stage.stage_name, stage.sequence_number
        ORDER BY stage.sequence_number
    """
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
        return jsonify(success=True, data=[_row_dict(x) for x in rows]), 200
    except Exception:
        current_app.logger.exception("Workflow summary query failed.")
        return jsonify(success=False, message="Workflow data unavailable."), 503


WORKFLOW_OVERVIEW_QUERY = f"""
WITH register_state AS (
    SELECT *
    FROM ({REGISTER_BASE_QUERY}) AS register
),
active_lp AS (
    SELECT *
    FROM register_state
    WHERE process_status = 'ACTIVE'
      AND lp_completion_date IS NULL
      AND (
            lp_circulation_start_date IS NOT NULL
         OR lp_contract_team_completion_date IS NOT NULL
         OR lp_junior_manager_approval_date IS NOT NULL
         OR lp_senior_manager_approval_date IS NOT NULL
         OR lp_gm_scm_approval_date IS NOT NULL
      )
),
mi_queue AS (
    SELECT
        COUNT(*) FILTER (
            WHERE final_negotiation_date IS NOT NULL
              AND mi_head_approval_date IS NULL
              AND mi_sm_approval_date IS NULL
              AND mi_gm_approval_date IS NULL
        )::int AS junior_manager,
        COUNT(*) FILTER (
            WHERE mi_head_approval_date IS NOT NULL
              AND mi_sm_approval_date IS NULL
              AND mi_gm_approval_date IS NULL
        )::int AS senior_manager,
        COUNT(*) FILTER (
            WHERE mi_sm_approval_date IS NOT NULL
              AND mi_gm_approval_date IS NULL
        )::int AS general_manager
    FROM khs_items
    WHERE process_status = 'ACTIVE'
),
lp_queue AS (
    SELECT
        COUNT(*) FILTER (WHERE lp_stage_key = 'contract_team')::int AS contract_team,
        COUNT(*) FILTER (WHERE lp_stage_key = 'junior_manager')::int AS junior_manager,
        COUNT(*) FILTER (WHERE lp_stage_key = 'senior_manager')::int AS senior_manager,
        COUNT(*) FILTER (WHERE lp_stage_key = 'general_manager')::int AS general_manager,
        COUNT(*) FILTER (WHERE lp_stage_key = 'director')::int AS director,
        COUNT(*) FILTER (WHERE lp_stage_key IN (
            'contract_team', 'junior_manager', 'senior_manager',
            'general_manager', 'director'
        ))::int AS active_total,
        COUNT(*)::int AS records_in_circulation
    FROM active_lp
),
lp_quality AS (
    -- Data-quality exceptions are counted across the whole KHS portfolio,
    -- including LPs already signed by the Director.
    SELECT
        COUNT(*) FILTER (
            WHERE lp_started_without_mi_gm_approval IS TRUE
        )::int AS prerequisite_exceptions,
        COUNT(*) FILTER (
            WHERE lp_stage_key = 'legacy_unverified'
        )::int AS legacy_unverified,
        COUNT(*) FILTER (
            WHERE lp_timeline_has_gaps IS TRUE
        )::int AS timeline_gaps
    FROM register_state
)
SELECT
    mi_queue.junior_manager,
    mi_queue.senior_manager,
    mi_queue.general_manager,
    lp_queue.contract_team,
    lp_queue.junior_manager,
    lp_queue.senior_manager,
    lp_queue.general_manager,
    lp_queue.director,
    lp_queue.active_total,
    lp_queue.records_in_circulation,
    lp_quality.prerequisite_exceptions,
    lp_quality.legacy_unverified,
    lp_quality.timeline_gaps
FROM mi_queue
CROSS JOIN lp_queue
CROSS JOIN lp_quality;
"""


@dashboard_bp.get("/workflow/overview")
def workflow_overview():
    """Return role-level queues from the same milestone-derived state as LP Circulation.

    LP lane counts never depend on the optional free-text Waiting For field.
    Records with invalid prerequisites or unverifiable legacy status are
    reported separately and excluded from normal approval lanes.
    """
    try:
        with get_db_pool().connection() as conn:
            row = conn.execute(WORKFLOW_OVERVIEW_QUERY).fetchone()

        if row is None:
            raise RuntimeError("Workflow overview query returned no row.")

        (
            mi_junior,
            mi_senior,
            mi_general,
            lp_contract_team,
            lp_junior,
            lp_senior,
            lp_general,
            lp_director,
            lp_active,
            lp_records,
            lp_prerequisite,
            lp_legacy,
            lp_gaps,
        ) = row

        mi = [
            {"key": "junior_manager", "label": "Junior Manager", "count": mi_junior, "stage_code": "MI_HEAD_APPROVAL"},
            {"key": "senior_manager", "label": "Senior Manager", "count": mi_senior, "stage_code": "MI_SM_APPROVAL"},
            {"key": "general_manager", "label": "General Manager", "count": mi_general, "stage_code": "MI_GM_APPROVAL"},
        ]
        lp = [
            {"key": "contract_team", "label": "Tim Kontrak", "count": lp_contract_team},
            {"key": "junior_manager", "label": "Junior Manager Vendor Management", "count": lp_junior},
            {"key": "senior_manager", "label": "Senior Manager Strategic Sourcing", "count": lp_senior},
            {"key": "general_manager", "label": "GM SCM", "count": lp_general},
            {"key": "director", "label": "Director / Direktur", "count": lp_director},
        ]

        return jsonify(
            success=True,
            data={
                "memo_internal": mi,
                "lp": lp,
                "lp_active_total": lp_active,
                "lp_records_in_circulation": lp_records,
                "lp_prerequisite_exceptions": lp_prerequisite,
                "lp_legacy_unverified": lp_legacy,
                "lp_timeline_gaps": lp_gaps,
                "lp_count_basis": (
                    "LP role counts are derived from the six ordered LP milestone dates. "
                    "Waiting For is descriptive metadata and does not determine the current stage."
                ),
            },
        ), 200
    except Exception:
        current_app.logger.exception("Workflow overview query failed.")
        return jsonify(
            success=False,
            code="WORKFLOW_OVERVIEW_UNAVAILABLE",
            message="Approval workflow overview is temporarily unavailable.",
        ), 503



def _sla_status_for_age(age_days, warning_after_days=None, target_days=None, escalation_after_days=None):
    if age_days is None or target_days is None:
        return "not_configured" if target_days is None else "age_unavailable"
    if escalation_after_days is not None and age_days >= escalation_after_days:
        return "escalation_due"
    if age_days >= target_days:
        return "overdue"
    if warning_after_days is not None and age_days >= warning_after_days:
        return "due_soon"
    return "on_track"


def _operations_stage_query(as_of):
    as_of_sql = f"DATE '{as_of.isoformat()}'"
    return """
        WITH register_state AS (
            SELECT *
            FROM (""" + REGISTER_BASE_QUERY + """) AS register
        ),
        active_wip AS (
            SELECT
                register.*,
                CASE
                    WHEN register.current_stage_started_on IS NOT NULL
                     AND register.current_stage_started_on <= """ + as_of_sql + """
                    THEN (""" + as_of_sql + """ - register.current_stage_started_on)::int
                    ELSE NULL
                END AS stage_age_days
            FROM register_state AS register
            WHERE register.process_status = 'ACTIVE'
              AND register.workflow_status <> 'completed'
              AND register.current_stage_code NOT IN ('COMPLETED', 'NOT_PROCEEDED')
        )
        SELECT
            stage.stage_code,
            stage.stage_name,
            stage.sequence_number,
            COUNT(wip.khs_id)::int AS wip_count,
            COUNT(wip.khs_id) FILTER (WHERE wip.stage_age_days BETWEEN 0 AND 7)::int AS age_0_7,
            COUNT(wip.khs_id) FILTER (WHERE wip.stage_age_days BETWEEN 8 AND 14)::int AS age_8_14,
            COUNT(wip.khs_id) FILTER (WHERE wip.stage_age_days BETWEEN 15 AND 30)::int AS age_15_30,
            COUNT(wip.khs_id) FILTER (WHERE wip.stage_age_days > 30)::int AS age_over_30,
            COUNT(wip.khs_id) FILTER (WHERE wip.khs_id IS NOT NULL AND wip.stage_age_days IS NULL)::int AS age_unavailable,
            (percentile_disc(0.5) WITHIN GROUP (ORDER BY wip.stage_age_days)
                FILTER (WHERE wip.stage_age_days IS NOT NULL))::int AS median_age_days,
            (percentile_disc(0.9) WITHIN GROUP (ORDER BY wip.stage_age_days)
                FILTER (WHERE wip.stage_age_days IS NOT NULL))::int AS p90_age_days,
            MAX(wip.stage_age_days)::int AS oldest_age_days,
            policy.warning_after_days,
            COALESCE(policy.target_days, stage.default_sla_days) AS target_days,
            policy.escalation_after_days,
            COUNT(wip.khs_id) FILTER (
                WHERE COALESCE(policy.target_days, stage.default_sla_days) IS NOT NULL
                  AND wip.stage_age_days >= COALESCE(policy.target_days, stage.default_sla_days)
            )::int AS overdue_count,
            COUNT(wip.khs_id) FILTER (
                WHERE policy.escalation_after_days IS NOT NULL
                  AND wip.stage_age_days >= policy.escalation_after_days
            )::int AS escalation_count
        FROM khs_stage_config AS stage
        LEFT JOIN active_wip AS wip ON wip.current_stage_code = stage.stage_code
        LEFT JOIN khs_stage_sla_policies AS policy ON policy.stage_code = stage.stage_code
        WHERE stage.is_active = TRUE
          AND stage.stage_code NOT IN ('COMPLETED', 'NOT_PROCEEDED')
        GROUP BY stage.stage_code, stage.stage_name, stage.sequence_number, stage.default_sla_days,
                 policy.warning_after_days, policy.target_days, policy.escalation_after_days
        ORDER BY stage.sequence_number
    """



@dashboard_bp.get("/operations/overview")
def operations_overview():
    today = _jakarta_today()
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_operations_stage_query(today))
                stage_rows = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """SELECT COUNT(*)::int AS total_open,
                              COUNT(*) FILTER (WHERE due_date < %s)::int AS overdue,
                              COUNT(*) FILTER (WHERE due_date = %s)::int AS due_today,
                              COUNT(*) FILTER (WHERE due_date > %s)::int AS upcoming
                       FROM khs_follow_ups f
                       JOIN khs_items k ON k.khs_id=f.khs_id
                       WHERE f.status='OPEN' AND k.process_status='ACTIVE'""",
                    (today, today, today),
                )
                follow_up_summary = dict(cur.fetchone())
                cur.execute(
                    """WITH register_state AS (
                           SELECT * FROM (""" + REGISTER_BASE_QUERY + """) AS register
                       )
                       SELECT COUNT(*)::int AS total
                       FROM register_state
                       WHERE process_status='ACTIVE'
                         AND workflow_status <> 'completed'
                         AND current_stage_code NOT IN ('COMPLETED','NOT_PROCEEDED')
                         AND current_stage_started_on IS NULL"""
                )
                unknown_age = cur.fetchone()["total"]

        for row in stage_rows:
            age = row["oldest_age_days"]
            row["sla_status"] = _sla_status_for_age(
                age,
                row.get("warning_after_days"),
                row.get("target_days"),
                row.get("escalation_after_days"),
            )
            row["sla_configured"] = row.get("target_days") is not None
        active_wip = sum(row["wip_count"] for row in stage_rows)
        older_than_30 = sum(row["age_over_30"] for row in stage_rows)
        overdue = sum(row["overdue_count"] for row in stage_rows)
        escalations = sum(row["escalation_count"] for row in stage_rows)
        return jsonify(
            success=True,
            as_of_date=today.isoformat(),
            data={
                "summary": {
                    "active_wip": active_wip,
                    "older_than_30_days": older_than_30,
                    "stage_age_unavailable": unknown_age,
                    "sla_not_configured_stages": sum(1 for row in stage_rows if not row["sla_configured"]),
                    "sla_overdue_records": overdue,
                    "escalation_records": escalations,
                    "follow_ups_open": follow_up_summary["total_open"],
                    "follow_ups_due_today": follow_up_summary["due_today"],
                    "follow_ups_overdue": follow_up_summary["overdue"],
                    "follow_ups_upcoming": follow_up_summary["upcoming"],
                },
                "stages": [_row_dict(row) for row in stage_rows],
                "follow_ups": follow_up_summary,
                "aging_bucket_note": "Aging buckets (0-7, 8-14, 15-30, 31+ days) are descriptive, not SLA targets.",
            },
        ),200
    except Exception:
        current_app.logger.exception("Operations overview query failed.")
        return jsonify(success=False, code="OPERATIONS_OVERVIEW_UNAVAILABLE",
                       message="Operations analytics are temporarily unavailable."),503


@dashboard_bp.get("/operations/follow-ups")
def list_khs_follow_ups():
    status = request.args.get("status", "OPEN").strip().upper()
    if status not in {"OPEN", "COMPLETED", "CANCELLED", "SUPERSEDED", "ALL"}:
        return jsonify(success=False, code="INVALID_FOLLOW_UP_STATUS",
                       message="Unsupported follow-up status."),400
    today = _jakarta_today()
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """WITH register_state AS (
                           SELECT * FROM (""" + REGISTER_BASE_QUERY + """) AS register
                       )
                       SELECT
                           f.id, f.khs_id, f.stage_code, sc.stage_name,
                           f.due_date, f.follow_up_to, f.note, f.status,
                           f.created_at, f.created_by, f.completed_at,
                           k.vendor_name, k.action_owner,
                           register.current_stage_code,
                           (f.stage_code <> register.workflow_stage_code) AS stage_changed,
                           (%s - f.due_date)::int AS days_from_due
                       FROM khs_follow_ups f
                       JOIN khs_items k ON k.khs_id=f.khs_id
                       JOIN khs_stage_config sc ON sc.stage_code=f.stage_code
                       JOIN register_state register ON register.khs_id=f.khs_id
                       WHERE (%s='ALL' OR f.status=%s)
                       ORDER BY
                           CASE WHEN f.status='OPEN' AND f.due_date < %s THEN 0
                                WHEN f.status='OPEN' AND f.due_date = %s THEN 1
                                WHEN f.status='OPEN' THEN 2 ELSE 3 END,
                           f.due_date ASC, f.id DESC
                       LIMIT 200""",
                    (today, status, status, today, today),
                )
                rows = [_row_dict(dict(row)) for row in cur.fetchall()]
        return jsonify(success=True, as_of_date=today.isoformat(), data=rows),200
    except Exception:
        current_app.logger.exception("KHS follow-up list failed.")
        return jsonify(success=False, code="FOLLOW_UP_LIST_UNAVAILABLE",
                       message="Follow-up reminders are temporarily unavailable."),503


@dashboard_bp.get("/khs/<path:khs_id>/follow-ups")
def list_khs_record_follow_ups(khs_id):
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """SELECT id, khs_id, stage_code, due_date, follow_up_to, note,
                              status, created_at, created_by, completed_at, completed_by,
                              cancelled_at, cancelled_by
                       FROM khs_follow_ups
                       WHERE khs_id=%s
                       ORDER BY CASE WHEN status='OPEN' THEN 0 ELSE 1 END,
                                due_date ASC, id DESC""",
                    (khs_id,),
                )
                rows = [_row_dict(dict(row)) for row in cur.fetchall()]
        return jsonify(success=True, data=rows),200
    except Exception:
        current_app.logger.exception("KHS record follow-up query failed.")
        return jsonify(success=False, message="Unable to load KHS follow-ups."),503


@dashboard_bp.post("/khs/<path:khs_id>/follow-ups")
def create_khs_follow_up(khs_id):
    body = _body_object()
    if body is None:
        return jsonify(success=False, message="A JSON object is required."),400
    try:
        data = _validate_payload(body, {"due_date", "follow_up_to", "note"},
                                 {"due_date", "note"})
        with get_db_pool().connection() as conn, conn.transaction():
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT process_status FROM khs_items WHERE khs_id=%s FOR UPDATE", (khs_id,))
                locked = cur.fetchone()
                if locked is None:
                    return jsonify(success=False, message="KHS not found."),404
                if locked["process_status"] != "ACTIVE":
                    return jsonify(success=False, code="KHS_NOT_ACTIVE",
                                   message="Follow-ups can only be scheduled for active KHS records."),409
                cur.execute(REGISTER_BASE_QUERY + " WHERE k.khs_id=%s", (khs_id,))
                record = cur.fetchone()
                if record is None:
                    return jsonify(success=False, message="KHS not found."),404
                record = dict(record)
            stage_code = record.get("workflow_stage_code")
            if stage_code in (None, "COMPLETED", "NOT_PROCEEDED"):
                return jsonify(success=False, code="NO_ACTIVE_STAGE",
                               message="This KHS has no active workflow stage."),409
            cur.execute(
                """INSERT INTO khs_follow_ups
                   (khs_id, stage_code, due_date, follow_up_to, note)
                   VALUES (%s,%s,%s,%s,%s)
                   RETURNING id, khs_id, stage_code, due_date, follow_up_to, note, status, created_at""",
                (khs_id, stage_code, data["due_date"], data.get("follow_up_to"), data["note"]),
            )
            follow_up = _row_dict(dict(cur.fetchone()))
            if data.get("follow_up_to"):
                conn.execute(
                    "UPDATE khs_items SET action_owner=%s, updated_at=NOW(), last_updated_date=CURRENT_DATE WHERE khs_id=%s",
                    (data["follow_up_to"], khs_id),
                )
                after = {**record, "action_owner": data["follow_up_to"]}
                _audit(conn, "KHS_ITEM", khs_id, "ACTION_OWNER_UPDATED", record, after)
            _audit(conn, "KHS_ITEM", khs_id, "FOLLOW_UP_SCHEDULED", {},
                   {"follow_up": follow_up})
        return jsonify(success=True, data=follow_up),201
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)),400
    except Exception:
        current_app.logger.exception("KHS follow-up scheduling failed.")
        return jsonify(success=False, code="FOLLOW_UP_CREATE_UNAVAILABLE",
                       message="Unable to schedule the follow-up."),500


def _set_follow_up_status(follow_up_id, status):
    with get_db_pool().connection() as conn, conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT f.*, k.process_status
                   FROM khs_follow_ups f JOIN khs_items k ON k.khs_id=f.khs_id
                   WHERE f.id=%s FOR UPDATE OF f""",
                (follow_up_id,),
            )
            before = cur.fetchone()
            if before is None:
                return None
            before = dict(before)
        if before["status"] != "OPEN":
            return {"conflict": True}
        actor_field = "completed_by" if status == "COMPLETED" else "cancelled_by"
        time_field = "completed_at" if status == "COMPLETED" else "cancelled_at"
        conn.execute(
            f"UPDATE khs_follow_ups SET status=%s, {time_field}=NOW(), {actor_field}='manual-entry' WHERE id=%s",
            (status, follow_up_id),
        )
        after = {**before, "status": status, actor_field: "manual-entry"}
        _audit(conn, "KHS_ITEM", before["khs_id"],
               "FOLLOW_UP_" + status, before, after)
        return {"id": follow_up_id, "khs_id": before["khs_id"], "status": status}


@dashboard_bp.post("/operations/follow-ups/<int:follow_up_id>/complete")
def complete_khs_follow_up(follow_up_id):
    try:
        result = _set_follow_up_status(follow_up_id, "COMPLETED")
        if result is None:
            return jsonify(success=False, message="Follow-up not found."),404
        if result.get("conflict"):
            return jsonify(success=False, code="FOLLOW_UP_NOT_OPEN",
                           message="Only open follow-ups can be completed."),409
        return jsonify(success=True, data=result),200
    except Exception:
        current_app.logger.exception("Follow-up completion failed.")
        return jsonify(success=False, message="Unable to complete follow-up."),503


@dashboard_bp.post("/operations/follow-ups/<int:follow_up_id>/cancel")
def cancel_khs_follow_up(follow_up_id):
    try:
        result = _set_follow_up_status(follow_up_id, "CANCELLED")
        if result is None:
            return jsonify(success=False, message="Follow-up not found."),404
        if result.get("conflict"):
            return jsonify(success=False, code="FOLLOW_UP_NOT_OPEN",
                           message="Only open follow-ups can be cancelled."),409
        return jsonify(success=True, data=result),200
    except Exception:
        current_app.logger.exception("Follow-up cancellation failed.")
        return jsonify(success=False, message="Unable to cancel follow-up."),503


@dashboard_bp.get("/activity")
def activity_log():
    try:
        page = _register_positive_int("page", 1)
        per_page = _register_positive_int("per_page", 25, maximum=100)
    except ValueError as exc:
        return jsonify(success=False, message=str(exc)), 400

    search = request.args.get("q", "").strip()
    if len(search) > 100:
        return jsonify(success=False, code="INVALID_SEARCH",
                       message="Activity search must not exceed 100 characters."), 400

    entity_type = request.args.get("entity_type", "").strip().upper()
    if entity_type and entity_type not in {"REQUEST", "KHS_ITEM"}:
        return jsonify(success=False, code="INVALID_ENTITY_TYPE",
                       message="Unsupported activity entity filter."), 400

    filters = []
    params = []
    if entity_type:
        filters.append("entity_type = %s")
        params.append(entity_type)
    if search:
        pattern = f"%{search}%"
        filters.append("""
            (
                entity_id ILIKE %s
                OR entity_type ILIKE %s
                OR action ILIKE %s
                OR actor ILIKE %s
                OR COALESCE(changes::text, '') ILIKE %s
            )
        """)
        params.extend([pattern] * 5)
    where_sql = "WHERE " + " AND ".join(filters) if filters else ""
    offset = (page - 1) * per_page

    try:
        with get_db_pool().connection() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM khs_activity_logs {where_sql}",
                params,
            ).fetchone()[0]
            rows = conn.execute(
                f"""SELECT id, entity_type, entity_id, action, actor, changes, occurred_at
                    FROM khs_activity_logs
                    {where_sql}
                    ORDER BY occurred_at DESC, id DESC
                    LIMIT %s OFFSET %s""",
                [*params, per_page, offset],
            ).fetchall()
        return jsonify(
            success=True,
            data=[_row_dict(dict(zip(
                ("id", "entity_type", "entity_id", "action", "actor", "changes", "occurred_at"),
                row,
            ))) for row in rows],
            pagination={
                "page": page,
                "per_page": per_page,
                "total_records": total,
                "total_pages": (total + per_page - 1) // per_page if total else 0,
                "has_previous": page > 1,
                "has_next": page < ((total + per_page - 1) // per_page if total else 0),
            },
        ), 200
    except Exception:
        current_app.logger.exception("Activity query failed.")
        return jsonify(success=False, message="Activity log unavailable."), 503


@dashboard_bp.get("/export")
def export_khs_csv():
    """Stream a complete register export without loading the entire file in memory."""
    columns = [
        ("khs_id", "KHS ID"), ("request_id", "Request ID"),
        ("request_date", "Request Date"), ("request_subject", "Request Subject"),
        ("requester_owner", "Requester / Owner"), ("vendor_name", "Vendor"),
        ("executor_code", "Executor Code"), ("executor_name", "Executor"),
        ("subtype", "Contract Type"), ("current_stage_name", "Current Stage"),
        ("lp_status", "LP Status"), ("dispatch_date", "Dispatch Date"),
        ("contract_start_date", "Contract Start"), ("contract_end_date", "Contract End"),
        ("boq_confirmation_date", "BOQ Confirmation"), ("negotiation_date", "Negotiation"),
        ("final_negotiation_date", "Final Negotiation"), ("mi_head_approval_date", "MI Head Approval"),
        ("mi_sm_approval_date", "MI SM Approval"), ("mi_gm_approval_date", "MI GM Approval"),
        ("legal_submission_date", "Legal Submission"), ("lp_circulation_start_date", "LP Circulation Start"),
        ("lp_contract_team_completion_date", "LP Contract Team Completion"),
        ("lp_junior_manager_approval_date", "LP Junior Manager Approval"),
        ("lp_senior_manager_approval_date", "LP Senior Manager Approval"),
        ("lp_gm_scm_approval_date", "LP GM SCM Approval"),
        ("lp_completion_date", "LP Director Sign-off"),
        ("khs_inject_start_date", "KHS Injection Start"),
        ("khs_inject_completion_date", "KHS Fully Injected"),
        ("workflow_status", "Workflow Status"),
        ("waiting_for", "Waiting For"),
        ("waiting_reason", "Waiting Reason"), ("last_updated_date", "Last Updated"),
        ("remarks", "Remarks")
    ]
    query = "SELECT * FROM (" + REGISTER_BASE_QUERY + ") AS register ORDER BY register.dispatch_date DESC NULLS LAST, register.khs_id"

    def generate():
        with get_db_pool().connection() as conn:
            with conn.transaction():
                with conn.cursor(name="khs_export", row_factory=dict_row) as cursor:
                    cursor.execute(query)
                    buffer = StringIO()
                    writer = csv.writer(buffer)
                    yield "\ufeff"
                    writer.writerow([label for _, label in columns])
                    yield buffer.getvalue()
                    while True:
                        rows = cursor.fetchmany(500)
                        if not rows:
                            break
                        buffer.seek(0)
                        buffer.truncate(0)
                        writer.writerows([
                            [
                                ("'" + value if isinstance(value, str)
                                 and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r"))
                                 else value)
                                for value in [_json_safe_value(row.get(key)) for key, _ in columns]
                            ]
                            for row in rows
                        ])
                        yield buffer.getvalue()

    filename = "khs-register-" + datetime.now(ZoneInfo("Asia/Jakarta")).date().isoformat() + ".csv"
    return Response(
        stream_with_context(generate()),
        content_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="' + filename + '"',
            "Cache-Control": "no-store"
        }
    )
