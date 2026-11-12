import csv
from datetime import date, datetime
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

    COUNT(*) FILTER (WHERE lp_completion_date IS NOT NULL) AS lp_completed,
    COUNT(*) FILTER (
        WHERE lp_circulation_start_date IS NOT NULL
          AND lp_completion_date IS NULL
    ) AS lp_in_progress,
    COUNT(*) FILTER (
        WHERE lp_circulation_start_date IS NULL
    ) AS lp_not_started,

    COUNT(*) FILTER (
        WHERE khs_inject_completion_date IS NOT NULL
    ) AS inject_completed,
    COUNT(*) FILTER (
        WHERE khs_inject_start_date IS NOT NULL
          AND khs_inject_completion_date IS NULL
    ) AS inject_in_progress,
    COUNT(*) FILTER (
        WHERE lp_completion_date IS NOT NULL
          AND khs_inject_start_date IS NULL
    ) AS inject_pending,

    COUNT(*) FILTER (WHERE mi_gm_approval_date IS NOT NULL) AS mi_gm_approved,
    COUNT(*) FILTER (WHERE mi_gm_approval_date IS NULL) AS mi_gm_pending,
    COUNT(*) FILTER (WHERE legal_submission_date IS NOT NULL) AS legal_submitted,
    COUNT(*) FILTER (
        WHERE lp_circulation_start_date IS NOT NULL
          AND mi_gm_approval_date IS NULL
    ) AS lp_started_without_mi_gm,
    COUNT(*) FILTER (
        WHERE mi_gm_approval_date IS NOT NULL
          AND lp_circulation_start_date IS NULL
    ) AS awaiting_lp_circulation

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
    ) = row

    completion_rate = (
        round((lp_completed / total_khs) * 100, 2)
        if total_khs
        else 0.0
    )

    return jsonify({
        "success": True,
        "data": {
            "total_requests": total_requests,
            "total_khs": total_khs,
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
                    round((inject_completed / total_khs) * 100, 2)
                    if total_khs else 0.0
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
    k.lp_completion_date,
    k.khs_inject_start_date,
    k.khs_inject_completion_date,

    k.waiting_for,
    k.waiting_reason,
    k.last_updated_date,
    k.remarks,
    k.updated_at,

    derived.lp_status,
    derived.workflow_status,
    derived.current_stage_code,
    stage.stage_name AS current_stage_name,

    (
        k.lp_circulation_start_date IS NOT NULL
        AND k.mi_gm_approval_date IS NULL
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
                THEN 'in_progress'
            ELSE 'not_started'
        END AS lp_status,

        CASE
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
        END AS current_stage_code
) AS derived

LEFT JOIN khs_stage_config stage
    ON stage.stage_code = derived.current_stage_code
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

    if waiting_for:
        filters.append("register.waiting_for = %s")
        params.append(waiting_for)

    attention = request.args.get("attention", "").strip().lower() in {"1", "true", "yes"}
    if attention:
        filters.append("(register.waiting_for IS NOT NULL OR register.lp_started_without_mi_gm_approval IS TRUE)")

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
        "data": [_register_json_safe(row) for row in rows],
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
        },
    }), 200


# ----------------------- Operational management API -----------------------

REQUEST_FIELDS = {"request_date", "request_subject", "requester_owner"}
ITEM_FIELDS = {
    "request_id", "vendor_name", "executor_code", "subtype",
    "dispatch_date", "contract_start_date", "contract_end_date",
    "boq_confirmation_date", "negotiation_date", "final_negotiation_date",
    "mi_head_approval_date", "mi_sm_approval_date", "mi_gm_approval_date",
    "legal_submission_date", "lp_circulation_start_date", "lp_completion_date",
    "khs_inject_start_date", "khs_inject_completion_date",
    "waiting_for", "waiting_reason", "last_updated_date", "remarks",
}
DATE_FIELDS = {
    "request_date", "dispatch_date", "contract_start_date", "contract_end_date",
    "boq_confirmation_date", "negotiation_date", "final_negotiation_date",
    "mi_head_approval_date", "mi_sm_approval_date", "mi_gm_approval_date",
    "legal_submission_date", "lp_circulation_start_date", "lp_completion_date",
    "khs_inject_start_date", "khs_inject_completion_date",
    "last_updated_date",
}
TEXT_LIMITS = {
    "request_id": 64, "request_subject": 300, "requester_owner": 160,
    "khs_id": 64, "vendor_name": 240, "executor_code": 32, "waiting_for": 160,
    "waiting_reason": 1000, "remarks": 2000,
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
                            WHERE k.khs_inject_completion_date IS NULL
                        )::int AS open_khs,
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
            data=_row_dict(item),
            history=[_row_dict(x) for x in history],
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

    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    mime_type = mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    target.write_bytes(payload)

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
            if merged.get("lp_completion_date") and not merged.get("lp_circulation_start_date"):
                return jsonify(success=False,code="LP_START_REQUIRED",message="LP completion requires circulation start."),422
            if merged.get("lp_completion_date") and merged.get("lp_circulation_start_date") and merged["lp_completion_date"]<merged["lp_circulation_start_date"]:
                return jsonify(success=False,code="LP_DATE_ORDER",message="LP completion cannot precede circulation start."),422
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
        return jsonify(success=True,message="KHS updated."),200
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    except Exception:
        current_app.logger.exception("KHS update failed.")
        return jsonify(success=False,message="Unable to update KHS."),500


@dashboard_bp.get("/workflow")
def workflow_monitoring():
    query = """
        SELECT stage.stage_code, stage.stage_name, stage.sequence_number,
               COUNT(register.khs_id)::int AS total,
               COUNT(register.khs_id) FILTER (
                   WHERE register.workflow_status = 'completed'
               )::int AS completed
        FROM khs_stage_config stage
        LEFT JOIN (
            SELECT khs_id, current_stage_code, lp_status, workflow_status
            FROM (""" + REGISTER_BASE_QUERY + """) AS derived_register
        ) AS register
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


@dashboard_bp.get("/activity")
def activity_log():
    try:
        page=_register_positive_int("page",1)
        per_page=_register_positive_int("per_page",25,maximum=100)
    except ValueError as exc:
        return jsonify(success=False,message=str(exc)),400
    try:
        with get_db_pool().connection() as conn:
            total=conn.execute("SELECT COUNT(*) FROM khs_activity_logs").fetchone()[0]
            rows=conn.execute("""SELECT id,entity_type,entity_id,action,actor,changes,occurred_at
                                 FROM khs_activity_logs ORDER BY occurred_at DESC,id DESC
                                 LIMIT %s OFFSET %s""",(per_page,(page-1)*per_page)).fetchall()
        return jsonify(success=True,data=[_row_dict(dict(zip(
            ("id","entity_type","entity_id","action","actor","changes","occurred_at"),r))) for r in rows],
            pagination={"page":page,"per_page":per_page,"total_records":total,
                        "total_pages":(total+per_page-1)//per_page if total else 0}),200
    except Exception:
        current_app.logger.exception("Activity query failed.")
        return jsonify(success=False,message="Activity log unavailable."),503


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
        ("lp_completion_date", "LP Completion"),
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
