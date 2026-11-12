from datetime import date, datetime
from hashlib import sha256
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile, is_zipfile

from flask import Blueprint, current_app, jsonify, request, send_file
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from zoneinfo import ZoneInfo
from psycopg.types.json import Jsonb
from werkzeug.utils import secure_filename

from app.db import get_db_pool

from app.services.import_confirmation import (
    ImportConfirmationError,
    confirm_import as confirm_import_batch,
)
from app.services.excel_import import (
    WorkbookImportError,
    parse_khs_workbook,
)
from app.services.excel_workbook import build_current_khs_workbook


imports_bp = Blueprint("imports", __name__)

MAX_ZIP_ENTRIES = 3000
MAX_UNCOMPRESSED_SIZE = 120 * 1024 * 1024


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, dict):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]

    return value


def _check_xlsx_container(payload):
    stream = BytesIO(payload)

    if not is_zipfile(stream):
        raise WorkbookImportError(
            "Uploaded file is not a valid XLSX container."
        )

    try:
        with ZipFile(BytesIO(payload)) as archive:
            entries = archive.infolist()

            if len(entries) > MAX_ZIP_ENTRIES:
                raise WorkbookImportError(
                    "Workbook contains too many ZIP entries."
                )

            if sum(item.file_size for item in entries) > MAX_UNCOMPRESSED_SIZE:
                raise WorkbookImportError(
                    "Workbook expands beyond the permitted size."
                )

            if any(item.flag_bits & 0x1 for item in entries):
                raise WorkbookImportError(
                    "Encrypted workbooks are not supported."
                )

            names = set(archive.namelist())

            required = {
                "[Content_Types].xml",
                "xl/workbook.xml",
            }

            if not required.issubset(names):
                raise WorkbookImportError(
                    "The uploaded ZIP file is not a valid Excel workbook."
                )

    except BadZipFile as exc:
        raise WorkbookImportError(
            "Workbook ZIP structure is damaged."
        ) from exc


def _row_issues(issues, entity, source_row):
    return [
        issue for issue in issues
        if issue.get("entity") == entity
        and issue.get("row") == source_row
    ]


def _row_status(issues):
    if any(issue["severity"] == "ERROR" for issue in issues):
        return "ERROR"

    if any(issue["severity"] == "WARNING" for issue in issues):
        return "WARNING"

    return "VALID"


@imports_bp.get("/workbook.xlsx")
def download_current_workbook():
    """Download a current-data Excel snapshot with the active import schema."""
    try:
        with get_db_pool().connection() as conn:
            with conn.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    """
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
                        CASE
                            WHEN COUNT(k.khs_id) = 0 THEN 'Not Started'
                            WHEN COUNT(k.khs_id) FILTER (
                                WHERE k.khs_inject_completion_date IS NOT NULL
                            ) = COUNT(k.khs_id) THEN 'Completed'
                            WHEN COUNT(k.khs_id) FILTER (
                                WHERE k.khs_inject_completion_date IS NOT NULL
                            ) > 0 THEN 'Partially Completed'
                            ELSE 'In Progress'
                        END AS request_status
                    FROM khs_requests r
                    LEFT JOIN khs_items k ON k.request_id = r.request_id
                    GROUP BY r.request_id
                    ORDER BY r.request_date DESC NULLS LAST, r.request_subject
                    """
                )
                requests = cursor.fetchall()

                cursor.execute(
                    """
                    SELECT
                        i.*,
                        r.request_date,
                        r.request_subject,
                        r.requester_owner
                    FROM khs_items i
                    JOIN khs_requests r ON r.request_id = i.request_id
                    ORDER BY r.request_subject, i.vendor_name, i.khs_id
                    """
                )
                items = cursor.fetchall()

                executors = conn.execute(
                    """
                    SELECT executor_code, display_name
                    FROM khs_executors
                    WHERE is_active = TRUE
                    ORDER BY display_name
                    """
                ).fetchall()
                executors = [
                    {"executor_code": row[0], "display_name": row[1]}
                    for row in executors
                ]

                subtypes = conn.execute(
                    """
                    SELECT DISTINCT subtype
                    FROM khs_items
                    WHERE subtype IS NOT NULL AND btrim(subtype) <> ''
                    ORDER BY subtype
                    """
                ).fetchall()
                subtype_values = sorted(
                    {"Renewal", "Kontrak Baru"} | {row[0] for row in subtypes}
                )

                waiting_rows = conn.execute(
                    """
                    SELECT DISTINCT waiting_for
                    FROM khs_items
                    WHERE waiting_for IS NOT NULL AND btrim(waiting_for) <> ''
                    ORDER BY waiting_for
                    """
                ).fetchall()
                waiting_values = [row[0] for row in waiting_rows]

        workbook = build_current_khs_workbook(
            requests=requests,
            items=items,
            executors=executors,
            subtypes=subtype_values,
            waiting_for=waiting_values,
        )
        filename = (
            "KHS_Creation_Monitoring_Current_"
            + datetime.now(ZoneInfo("Asia/Jakarta")).date().isoformat()
            + ".xlsx"
        )
        response = send_file(
            workbook,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=filename,
        )
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response
    except Exception:
        current_app.logger.exception("Current KHS workbook export failed.")
        return jsonify({
            "success": False,
            "code": "WORKBOOK_EXPORT_UNAVAILABLE",
            "message": "Unable to generate the current KHS Excel workbook.",
        }), 503


@imports_bp.post("/preview")
def preview_import():
    uploaded = request.files.get("file")

    if uploaded is None or not uploaded.filename:
        return jsonify({
            "success": False,
            "message": "Please provide an Excel file using field 'file'.",
        }), 400

    safe_name = secure_filename(
        PurePosixPath(uploaded.filename.replace("\\", "/")).name
    )

    if not safe_name.lower().endswith(".xlsx"):
        return jsonify({
            "success": False,
            "message": "Only .xlsx workbooks are supported.",
        }), 400

    max_size = current_app.config["MAX_CONTENT_LENGTH"]
    payload = uploaded.stream.read(max_size + 1)

    if not payload:
        return jsonify({
            "success": False,
            "message": "Uploaded file is empty.",
        }), 400

    if len(payload) > max_size:
        return jsonify({
            "success": False,
            "message": "File exceeds the permitted upload size.",
        }), 413

    try:
        _check_xlsx_container(payload)
    except WorkbookImportError as exc:
        return jsonify({
            "success": False,
            "message": str(exc),
        }), 400

    file_hash = sha256(payload).hexdigest()
    pool = get_db_pool()

    try:
        # Fetch the active executor master.
        with pool.connection() as conn:
            executor_rows = conn.execute(
                """
                SELECT executor_code
                FROM khs_executors
                WHERE is_active = TRUE
                """
            ).fetchall()

            known_executors = {
                row[0] for row in executor_rows
            }

            request_rows = conn.execute(
                """
                SELECT request_id, request_date, request_subject
                FROM khs_requests
                """
            ).fetchall()
            known_requests = {
                row[0]: {
                    "request_date": row[1],
                    "request_subject": row[2],
                }
                for row in request_rows
            }

            existing = conn.execute(
                """
                SELECT id, status
                FROM khs_import_batches
                WHERE file_sha256 = %s
                """,
                (file_hash,),
            ).fetchone()

        if existing:
            return jsonify({
                "success": False,
                "code": "DUPLICATE_UPLOAD",
                "message": "This exact file has already been uploaded.",
                "existing_batch_id": existing[0],
                "existing_status": existing[1],
            }), 409

        parsed = parse_khs_workbook(
            BytesIO(payload),
            known_executors=known_executors,
            known_requests=known_requests,
        )

        issues = parsed["issues"]

        staged_records = (
            [
                ("REQUEST", "01 - Request Register", item)
                for item in parsed["requests"]
            ]
            +
            [
                ("KHS_ITEM", "02 - KHS Tracking", item)
                for item in parsed["items"]
            ]
        )

        row_keys = {
            (entity, record["source_excel_row"])
            for entity, _, record in staged_records
        }

        issue_keys = {
            (issue["entity"], issue["row"])
            for issue in issues
            if issue.get("entity") in ("REQUEST", "KHS_ITEM")
            and issue.get("row") is not None
            and issue["severity"] == "ERROR"
        }

        missing_staged_keys = issue_keys - row_keys

        valid_count = 0
        warning_count = 0
        error_count = 0

        for entity, sheet, record in staged_records:
            row_number = record["source_excel_row"]

            row_issues = _row_issues(
                issues, entity, row_number
            )

            status = _row_status(row_issues)

            if status == "VALID":
                valid_count += 1
            elif status == "WARNING":
                warning_count += 1
            else:
                error_count += 1

        error_count += len(missing_staged_keys)

        workbook_issues = [
            issue for issue in issues
            if issue.get("row") is None
        ]

        global_error_count = sum(
            1 for issue in workbook_issues
            if issue["severity"] == "ERROR"
        )
        global_warning_count = sum(
            1 for issue in workbook_issues
            if issue["severity"] == "WARNING"
        )
        error_count += global_error_count
        warning_count += global_warning_count
        has_global_error = global_error_count > 0

        total_rows = (
            len(staged_records) + len(missing_staged_keys)
        )

        with pool.connection() as conn:
            with conn.transaction():
                batch = conn.execute(
                    """
                    INSERT INTO khs_import_batches (
                        original_file_name,
                        file_sha256,
                        status,
                        total_rows,
                        valid_rows,
                        warning_rows,
                        error_rows,
                        error_summary
                    )
                    VALUES (%s, %s, 'PREVIEWED', %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        safe_name,
                        file_hash,
                        total_rows,
                        valid_count,
                        warning_count,
                        error_count,
                        Jsonb({
                            "parser_summary": parsed["summary"],
                            "workbook_issues": workbook_issues,
                            "unrepresented_error_rows": len(
                                missing_staged_keys
                            ),
                        }),
                    ),
                ).fetchone()

                batch_id = batch[0]

                for entity, sheet, record in staged_records:
                    row_number = record["source_excel_row"]

                    row_issues = _row_issues(
                        issues, entity, row_number
                    )

                    status = _row_status(row_issues)

                    external_id = (
                        record["request_id"]
                        if entity == "REQUEST"
                        else record["khs_id"]
                    )

                    conn.execute(
                        """
                        INSERT INTO khs_import_rows (
                            batch_id,
                            sheet_name,
                            source_row_number,
                            entity_type,
                            external_id,
                            validation_status,
                            raw_data,
                            normalized_data,
                            errors,
                            warnings
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s
                        )
                        """,
                        (
                            batch_id,
                            sheet,
                            row_number,
                            entity,
                            external_id,
                            status,
                            Jsonb({
                                "source_sheet": sheet,
                                "source_excel_row": row_number,
                            }),
                            Jsonb(_json_safe(record)),
                            Jsonb([
                                issue for issue in row_issues
                                if issue["severity"] == "ERROR"
                            ]),
                            Jsonb([
                                issue for issue in row_issues
                                if issue["severity"] == "WARNING"
                            ]),
                        ),
                    )

        return jsonify({
            "success": True,
            "message": "Workbook validation completed. No master KHS records were changed.",
            "batch_id": batch_id,
            "file_name": safe_name,
            "file_sha256": file_hash,
            "template_version": parsed["template_version"],
            "summary": {
                "total_requests": parsed["summary"]["total_requests"],
                "total_khs_items": parsed["summary"]["total_khs_items"],
                "total_rows": total_rows,
                "valid_rows": valid_count,
                "warning_rows": warning_count,
                "error_rows": error_count,
                "can_import": (
                    error_count == 0
                    and not has_global_error
                ),
            },
            "issues": issues[:500],
            "issues_truncated": len(issues) > 500,
        }), 201

    except WorkbookImportError as exc:
        return jsonify({
            "success": False,
            "message": str(exc),
        }), 400

    except UniqueViolation:
        current_app.logger.warning(
            "Duplicate KHS workbook upload attempted."
        )
        return jsonify({
            "success": False,
            "code": "DUPLICATE_UPLOAD",
            "message": "This workbook was uploaded concurrently.",
        }), 409

    except Exception:
        current_app.logger.exception(
            "KHS Excel preview processing failed."
        )
        return jsonify({
            "success": False,
            "message": "Excel preview processing failed. Check application logs.",
        }), 500


@imports_bp.post("/<int:batch_id>/confirm")
def confirm_import_route(batch_id):
    """Explicitly confirm a validated Excel import batch."""

    body = request.get_json(silent=True)

    if body is None:
        body = {}

    if not isinstance(body, dict):
        return jsonify({
            "success": False,
            "message": "A JSON object is required.",
        }), 400

    accept_warnings = body.get("accept_warnings", False)

    if not isinstance(accept_warnings, bool):
        return jsonify({
            "success": False,
            "message": "accept_warnings must be a boolean.",
        }), 400

    try:
        result = confirm_import_batch(
            pool=get_db_pool(),
            batch_id=batch_id,
            accept_warnings=accept_warnings,
        )

        return jsonify({
            "success": True,
            "message": "KHS import completed successfully.",
            "result": result,
        }), 200

    except ImportConfirmationError as exc:
        return jsonify({
            "success": False,
            "code": exc.code,
            "message": str(exc),
        }), exc.status_code

    except Exception:
        current_app.logger.exception(
            "KHS import confirmation failed for batch %s.",
            batch_id,
        )

        return jsonify({
            "success": False,
            "message": (
                "Import transaction failed. "
                "No partial master changes were committed."
            ),
        }), 500


@imports_bp.get("/history")
def import_history():
    """Return paginated import batch history without exposing file contents."""

    try:
        page = int(request.args.get("page", "1"))
        per_page = int(request.args.get("per_page", "10"))

        if page < 1 or per_page < 1 or per_page > 100:
            raise ValueError

    except (TypeError, ValueError):
        return jsonify({
            "success": False,
            "code": "INVALID_PAGINATION",
            "message": "Page must be positive and per_page must be between 1 and 100.",
        }), 400

    columns = (
        "id",
        "original_file_name",
        "status",
        "total_rows",
        "valid_rows",
        "warning_rows",
        "error_rows",
        "inserted_requests",
        "updated_requests",
        "unchanged_requests",
        "inserted_items",
        "updated_items",
        "unchanged_items",
        "uploaded_at",
        "completed_at",
    )

    offset = (page - 1) * per_page

    try:
        pool = get_db_pool()

        with pool.connection() as conn:
            total = conn.execute(
                "SELECT COUNT(*) FROM khs_import_batches"
            ).fetchone()[0]

            rows = conn.execute(
                f"""
                SELECT {", ".join(columns)}
                FROM khs_import_batches
                ORDER BY uploaded_at DESC, id DESC
                LIMIT %s OFFSET %s
                """,
                (per_page, offset),
            ).fetchall()

        records = [
            _json_safe(dict(zip(columns, row)))
            for row in rows
        ]

    except Exception:
        current_app.logger.exception(
            "KHS import history query failed."
        )
        return jsonify({
            "success": False,
            "code": "IMPORT_HISTORY_UNAVAILABLE",
            "message": "Import history is temporarily unavailable.",
        }), 503

    total_pages = (
        (total + per_page - 1) // per_page
        if total
        else 0
    )

    return jsonify({
        "success": True,
        "data": records,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_records": total,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        },
    }), 200
