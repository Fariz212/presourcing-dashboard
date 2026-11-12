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
    "lp_completion_date",
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
    "lp_completion_date",
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

            if not request_ids:
                raise ImportConfirmationError(
                    "No request records found in staging.",
                    422,
                    "NO_REQUEST_RECORDS",
                )

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
                    raise ImportConfirmationError(
                        f"KHS {data.get('khs_id')} has no request in this batch.",
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
