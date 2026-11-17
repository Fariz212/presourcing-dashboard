from datetime import date
from typing import Any

from psycopg.types.json import Jsonb


class ImportConfirmationError(Exception):
    def __init__(self, message, status_code=409, code="IMPORT_REJECTED"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


REQUEST_FIELDS = (
    "request_date",
    "request_subject",
    "requester_owner",
)

ITEM_FIELDS = (
    "request_id",
    "source_row_no",
    "dispatch_date",
    "executor_code",
    "subtype",
    "vendor_name",
    "contract_start_date",
    "contract_end_date",
    "boq_confirmation_date",
    "negotiation_date",
    "final_negotiation_date",
    "mi_head_approval_date",
    "mi_sm_approval_date",
    "mi_gm_approval_date",
    "legal_submission_date",
    "lp_circulation_start_date",
    "lp_contract_team_completion_date",
    "lp_junior_manager_approval_date",
    "lp_senior_manager_approval_date",
    "lp_gm_scm_approval_date",
    "lp_completion_date",
    "khs_inject_start_date",
    "khs_inject_completion_date",
    "waiting_for",
    "waiting_reason",
    "last_updated_date",
    "remarks",
    "legacy_overall_status",
    "legacy_detailed_status",
    "source_col_s_audit_date",
    "migration_review",
)

DATE_FIELDS = {
    "request_date",
    "dispatch_date",
    "contract_start_date",
    "contract_end_date",
    "boq_confirmation_date",
    "negotiation_date",
    "final_negotiation_date",
    "mi_head_approval_date",
    "mi_sm_approval_date",
    "mi_gm_approval_date",
    "legal_submission_date",
    "lp_circulation_start_date",
    "lp_contract_team_completion_date",
    "lp_junior_manager_approval_date",
    "lp_senior_manager_approval_date",
    "lp_gm_scm_approval_date",
    "lp_completion_date",
    "khs_inject_start_date",
    "khs_inject_completion_date",
    "last_updated_date",
    "source_col_s_audit_date",
}

TABLE_CONFIG = {
    "REQUEST": {
        "table": "khs_requests",
        "id_column": "request_id",
        "fields": REQUEST_FIELDS,
    },
    "KHS_ITEM": {
        "table": "khs_items",
        "id_column": "khs_id",
        "fields": ITEM_FIELDS,
    },
}


def _json_safe(value):
    if isinstance(value, (date,)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    return value


def _db_value(field, value):
    if value is None:
        return None

    if field in DATE_FIELDS:
        if isinstance(value, date):
            return value

        return date.fromisoformat(str(value))

    if field == "source_row_no":
        return int(value)

    if isinstance(value, str):
        return value.strip() or None

    return value


def _log_activity(
    conn,
    entity_type,
    entity_id,
    action,
    changes,
    batch_id,
):
    conn.execute(
        """
        INSERT INTO khs_activity_logs (
            entity_type,
            entity_id,
            action,
            actor,
            changes,
            import_batch_id
        )
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            entity_type,
            entity_id,
            action,
            "excel-import",
            Jsonb(_json_safe(changes)),
            batch_id,
        ),
    )



WORKFLOW_MILESTONE_FIELDS = {
    "dispatch_date",
    "boq_confirmation_date",
    "negotiation_date",
    "final_negotiation_date",
    "mi_head_approval_date",
    "mi_sm_approval_date",
    "mi_gm_approval_date",
    "legal_submission_date",
    "lp_circulation_start_date",
    "lp_contract_team_completion_date",
    "lp_junior_manager_approval_date",
    "lp_senior_manager_approval_date",
    "lp_gm_scm_approval_date",
    "lp_completion_date",
    "khs_inject_start_date",
    "khs_inject_completion_date",
}


def _current_workflow_stage_identity(conn, khs_id):
    """Read the same milestone-derived stage identity used by the KHS register."""
    row = conn.execute(
        """
        SELECT
            k.process_status,
            derived.current_stage_code,
            CASE
                WHEN derived.current_stage_code = 'LP_CIRCULATION'
                    THEN derived.lp_stage_key
                WHEN derived.current_stage_code = 'KHS_INJECTION'
                    THEN CASE
                        WHEN k.khs_inject_start_date IS NULL
                            THEN 'injection_preparation'
                        ELSE 'khs_injection'
                    END
                ELSE COALESCE(derived.current_stage_code, '')
            END AS current_stage_key
        FROM khs_items AS k
        JOIN khs_requests AS r ON r.request_id = k.request_id
        CROSS JOIN LATERAL (
            SELECT
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
                END AS lp_stage_key
        ) AS derived
        WHERE k.khs_id = %s
        """,
        (khs_id,),
    ).fetchone()
    if row is None:
        raise ImportConfirmationError(
            f"KHS {khs_id} was not found while reconciling workflow reminders.",
            404,
            "KHS_NOT_FOUND",
        )
    return row


def _reconcile_imported_workflow_follow_ups(conn, khs_id, batch_id):
    """Supersede reminders whose stage identity no longer matches imported history."""
    process_status, stage_code, stage_key = _current_workflow_stage_identity(conn, khs_id)
    result = conn.execute(
        """
        UPDATE khs_follow_ups
        SET status = 'SUPERSEDED',
            cancelled_at = NOW(),
            cancelled_by = 'system'
        WHERE khs_id = %s
          AND status = 'OPEN'
          AND (
                %s <> 'ACTIVE'
             OR %s IN ('COMPLETED', 'NOT_PROCEEDED')
             OR stage_code IS DISTINCT FROM %s
             OR stage_key IS DISTINCT FROM %s
          )
        """,
        (khs_id, process_status, stage_code, stage_code, stage_key),
    )
    superseded_count = result.rowcount
    if superseded_count:
        _log_activity(
            conn,
            "KHS_ITEM",
            khs_id,
            "FOLLOW_UPS_SUPERSEDED",
            {
                "superseded_count": superseded_count,
                "current_stage_code": stage_code,
                "current_stage_key": stage_key,
                "reason": "IMPORTED_WORKFLOW_STAGE_CHANGED",
            },
            batch_id,
        )
    return superseded_count


def _upsert_entity(conn, entity_type, record, batch_id):
    config = TABLE_CONFIG[entity_type]

    table = config["table"]
    id_column = config["id_column"]
    fields = config["fields"]

    entity_id = record.get(id_column)

    if not entity_id:
        raise ImportConfirmationError(
            f"Missing {id_column} in staged {entity_type}.",
            422,
            "INVALID_STAGED_RECORD",
        )

    conn.execute(
        "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
        (f"{table}:{entity_id}",),
    )

    values = {}

    for field in fields:
        value = _db_value(field, record.get(field))

        # Blank cells never erase existing database values.
        if value is not None:
            values[field] = value

    required = (
        {"request_subject"}
        if entity_type == "REQUEST"
        else {"request_id", "vendor_name"}
    )

    if not required.issubset(values):
        raise ImportConfirmationError(
            f"Required fields missing for {entity_id}.",
            422,
            "INVALID_STAGED_RECORD",
        )

    columns = (id_column,) + fields

    existing_row = conn.execute(
        f"""
        SELECT {", ".join(columns)}
        FROM {table}
        WHERE {id_column} = %s
        FOR UPDATE
        """,
        (entity_id,),
    ).fetchone()

    if existing_row is None:
        insert_columns = (id_column,) + tuple(
            field for field in fields if field in values
        )

        insert_values = [entity_id] + [
            values[field]
            for field in insert_columns
            if field != id_column
        ]

        placeholders = ", ".join(["%s"] * len(insert_columns))

        inserted = conn.execute(
            f"""
            INSERT INTO {table} ({", ".join(insert_columns)})
            VALUES ({placeholders})
            ON CONFLICT ({id_column}) DO NOTHING
            RETURNING {id_column}
            """,
            insert_values,
        ).fetchone()

        if inserted:
            _log_activity(
                conn,
                entity_type,
                entity_id,
                "CREATED",
                {"after": values},
                batch_id,
            )
            return "NEW"

        # Defensive fallback if another writer created the ID.
        existing_row = conn.execute(
            f"""
            SELECT {", ".join(columns)}
            FROM {table}
            WHERE {id_column} = %s
            FOR UPDATE
            """,
            (entity_id,),
        ).fetchone()

        if existing_row is None:
            raise ImportConfirmationError(
                f"Unable to resolve concurrent upsert for {entity_id}.",
                409,
                "UPSERT_CONFLICT",
            )

    existing = dict(zip(columns, existing_row))

    changes = {}
    for field, new_value in values.items():
        old_value = existing[field]

        if old_value != new_value:
            changes[field] = {
                "before": _json_safe(old_value),
                "after": _json_safe(new_value),
            }

    if not changes:
        return "UNCHANGED"

    update_values = {
        field: _db_value(field, values[field])
        for field in changes
    }

    assignments = [
        f"{field} = %s"
        for field in update_values
    ]

    params = list(update_values.values())
    assignments.append("updated_at = NOW()")
    if entity_type == "KHS_ITEM":
        assignments.append("last_updated_date = CURRENT_DATE")
    params.append(entity_id)

    conn.execute(
        f"""
        UPDATE {table}
        SET {", ".join(assignments)}
        WHERE {id_column} = %s
        """,
        params,
    )

    _log_activity(
        conn,
        entity_type,
        entity_id,
        "UPDATED",
        changes,
        batch_id,
    )

    if entity_type == "KHS_ITEM" and WORKFLOW_MILESTONE_FIELDS.intersection(changes):
        _reconcile_imported_workflow_follow_ups(conn, entity_id, batch_id)
    elif entity_type == "REQUEST" and "request_date" in changes:
        # A request-date correction can move a KHS with no later milestones
        # from REQUEST_RECEIVED to DISPATCH, so reconcile its reminders too.
        related_items = conn.execute(
            """
            SELECT khs_id
            FROM khs_items
            WHERE request_id = %s
            ORDER BY khs_id
            FOR UPDATE
            """,
            (entity_id,),
        ).fetchall()
        for (related_khs_id,) in related_items:
            _reconcile_imported_workflow_follow_ups(conn, related_khs_id, batch_id)

    return "UPDATED"


def confirm_import(pool, batch_id, accept_warnings=False):
    """
    Atomically upsert all staged request/KHS records.

    No records are deleted when absent from an uploaded workbook.
    Null/blank input fields never overwrite existing values.
    """

    counters = {
        "inserted_requests": 0,
        "updated_requests": 0,
        "unchanged_requests": 0,
        "inserted_items": 0,
        "updated_items": 0,
        "unchanged_items": 0,
    }

    with pool.connection() as conn:
        with conn.transaction():

            batch = conn.execute(
                """
                SELECT
                    id,
                    status,
                    total_rows,
                    error_rows,
                    warning_rows
                FROM khs_import_batches
                WHERE id = %s
                FOR UPDATE
                """,
                (batch_id,),
            ).fetchone()

            if batch is None:
                raise ImportConfirmationError(
                    "Import batch not found.",
                    404,
                    "BATCH_NOT_FOUND",
                )

            _, status, total_rows, error_rows, warning_rows = batch

            if status != "PREVIEWED":
                raise ImportConfirmationError(
                    f"Batch cannot be imported from status {status}.",
                    409,
                    "INVALID_BATCH_STATUS",
                )

            if error_rows > 0:
                raise ImportConfirmationError(
                    "Batch contains validation errors and cannot be imported.",
                    409,
                    "VALIDATION_ERRORS",
                )

            if warning_rows > 0 and not accept_warnings:
                raise ImportConfirmationError(
                    "Warnings must be explicitly acknowledged before import.",
                    409,
                    "WARNINGS_REQUIRE_ACKNOWLEDGEMENT",
                )

            staged_rows = conn.execute(
                """
                SELECT
                    id,
                    entity_type,
                    external_id,
                    validation_status,
                    normalized_data
                FROM khs_import_rows
                WHERE batch_id = %s
                ORDER BY
                    CASE entity_type
                        WHEN 'REQUEST' THEN 0
                        WHEN 'KHS_ITEM' THEN 1
                        ELSE 2
                    END,
                    id
                FOR UPDATE
                """,
                (batch_id,),
            ).fetchall()

            if len(staged_rows) != total_rows:
                raise ImportConfirmationError(
                    "Staging row count does not match import batch summary.",
                    409,
                    "STAGING_COUNT_MISMATCH",
                )

            request_ids = set()

            for row in staged_rows:
                _, entity_type, external_id, validation_status, data = row

                if validation_status not in ("VALID", "WARNING"):
                    raise ImportConfirmationError(
                        f"Invalid staging row status: {validation_status}.",
                        409,
                        "INVALID_STAGING_STATUS",
                    )

                config = TABLE_CONFIG.get(entity_type)

                if config is None:
                    raise ImportConfirmationError(
                        f"Unsupported staged entity: {entity_type}.",
                        422,
                        "INVALID_STAGED_ENTITY",
                    )

                if not isinstance(data, dict):
                    raise ImportConfirmationError(
                        f"Invalid normalized data for {external_id}.",
                        422,
                        "INVALID_STAGED_DATA",
                    )

                if data.get(config["id_column"]) != external_id:
                    raise ImportConfirmationError(
                        f"Staged ID mismatch for {external_id}.",
                        422,
                        "STAGED_ID_MISMATCH",
                    )

                if entity_type == "REQUEST":
                    request_ids.add(external_id)

            # -------------------------------------------------
            # Parent records first.
            # -------------------------------------------------

            for row in staged_rows:
                row_id, entity_type, _, _, data = row

                if entity_type != "REQUEST":
                    continue

                change_type = _upsert_entity(
                    conn,
                    "REQUEST",
                    data,
                    batch_id,
                )

                counter_prefix = {
                    "NEW": "inserted",
                    "UPDATED": "updated",
                    "UNCHANGED": "unchanged",
                }[change_type]
                counters[f"{counter_prefix}_requests"] += 1

                conn.execute(
                    """
                    UPDATE khs_import_rows
                    SET validation_status = 'IMPORTED',
                        change_type = %s,
                        processed_at = NOW()
                    WHERE id = %s
                    """,
                    (change_type, row_id),
                )

            # -------------------------------------------------
            # Individual KHS records after parent records.
            # -------------------------------------------------

            for row in staged_rows:
                row_id, entity_type, _, _, data = row

                if entity_type != "KHS_ITEM":
                    continue

                if data.get("request_id") not in request_ids:
                    parent = conn.execute(
                        "SELECT 1 FROM khs_requests WHERE request_id = %s",
                        (data.get("request_id"),),
                    ).fetchone()
                    if parent is None:
                        raise ImportConfirmationError(
                            f"KHS {data.get('khs_id')} references a Request that is neither in this batch nor in the database.",
                            422,
                            "MISSING_PARENT_REQUEST",
                        )

                change_type = _upsert_entity(
                    conn,
                    "KHS_ITEM",
                    data,
                    batch_id,
                )

                counter_prefix = {
                    "NEW": "inserted",
                    "UPDATED": "updated",
                    "UNCHANGED": "unchanged",
                }[change_type]
                counters[f"{counter_prefix}_items"] += 1

                conn.execute(
                    """
                    UPDATE khs_import_rows
                    SET validation_status = 'IMPORTED',
                        change_type = %s,
                        processed_at = NOW()
                    WHERE id = %s
                    """,
                    (change_type, row_id),
                )

            conn.execute(
                """
                UPDATE khs_import_batches
                SET status = 'IMPORTED',
                    inserted_requests = %s,
                    updated_requests = %s,
                    unchanged_requests = %s,
                    inserted_items = %s,
                    updated_items = %s,
                    unchanged_items = %s,
                    completed_at = NOW()
                WHERE id = %s
                """,
                (
                    counters["inserted_requests"],
                    counters["updated_requests"],
                    counters["unchanged_requests"],
                    counters["inserted_items"],
                    counters["updated_items"],
                    counters["unchanged_items"],
                    batch_id,
                ),
            )

    return {
        "batch_id": batch_id,
        "status": "IMPORTED",
        **counters,
    }
