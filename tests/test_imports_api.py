from datetime import date
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import Workbook, load_workbook

from app import create_app
from app.services.excel_workbook import build_current_khs_workbook


@pytest.fixture()
def client():
    app = create_app({"TESTING": True})

    yield app.test_client()

    pool = app.extensions.get("khs_db_pool")
    if pool:
        pool.close()


def test_preview_requires_file(client):
    response = client.post("/api/imports/preview")

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_preview_rejects_wrong_extension(client):
    response = client.post(
        "/api/imports/preview",
        data={
            "file": (
                BytesIO(b"test data"),
                "tracking.csv",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "xlsx" in response.get_json()["message"].lower()


def test_preview_rejects_invalid_xlsx_container(client):
    response = client.post(
        "/api/imports/preview",
        data={
            "file": (
                BytesIO(b"this-is-not-an-excel-file"),
                "tracking.xlsx",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_preview_rejects_workbook_with_missing_sheets(client):
    workbook = Workbook()
    workbook.active.title = "Wrong Sheet"

    output = BytesIO()
    workbook.save(output)
    output.seek(0)

    response = client.post(
        "/api/imports/preview",
        data={
            "file": (
                output,
                "wrong-template.xlsx",
            )
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 400
    assert "missing required sheets" in (
        response.get_json()["message"].lower()
    )


def test_confirmation_rejects_non_boolean_warning_acknowledgement(client):
    response = client.post(
        "/api/imports/1/confirm",
        json={"accept_warnings": "yes"},
    )

    assert response.status_code == 400
    assert response.get_json()["success"] is False


def test_confirmation_rejects_unknown_batch(client):
    response = client.post(
        "/api/imports/999999999/confirm",
        json={"accept_warnings": True},
    )

    assert response.status_code == 404
    assert response.get_json()["code"] == "BATCH_NOT_FOUND"


def test_confirmation_rejects_non_json_array(client):
    response = client.post(
        "/api/imports/1/confirm",
        json=["invalid"],
    )

    assert response.status_code == 400




def test_partial_khs_excel_roundtrip_updates_existing_record(client):
    app = client.application
    pool = app.extensions["khs_db_pool"]
    token = uuid4().hex[:12].upper()
    request_id = f"REQ-XL-{token}"
    khs_id = f"KHS-XL-{token}"
    batch_id = None

    with pool.connection() as conn, conn.transaction():
        conn.execute(
            """
            INSERT INTO khs_requests (
                request_id, request_date, request_subject, requester_owner
            )
            VALUES (%s, %s, %s, %s)
            """,
            (request_id, date(2026, 11, 1), "Excel round-trip test", "CI"),
        )
        conn.execute(
            """
            INSERT INTO khs_items (
                khs_id, request_id, vendor_name, dispatch_date,
                mi_gm_approval_date, lp_circulation_start_date,
                lp_completion_date
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                khs_id,
                request_id,
                "PT Excel Round Trip",
                date(2026, 11, 2),
                date(2026, 11, 8),
                date(2026, 11, 10),
                date(2026, 11, 12),
            ),
        )

    try:
        with pool.connection() as conn:
            executor_rows = conn.execute(
                """
                SELECT executor_code, display_name
                FROM khs_executors
                WHERE is_active = TRUE
                ORDER BY display_name
                """
            ).fetchall()
            subtype_rows = conn.execute(
                """
                SELECT DISTINCT subtype
                FROM khs_items
                WHERE subtype IS NOT NULL AND btrim(subtype) <> ''
                ORDER BY subtype
                """
            ).fetchall()

        workbook = build_current_khs_workbook(
            requests=[],
            items=[{
                # Only the key and changed milestones are supplied.
                "khs_id": khs_id,
                "khs_inject_start_date": date(2026, 11, 13),
                "khs_inject_completion_date": date(2026, 11, 14),
            }],
            executors=[
                {"executor_code": row[0], "display_name": row[1]}
                for row in executor_rows
            ],
            subtypes=sorted(
                {"Renewal", "Kontrak Baru"} | {row[0] for row in subtype_rows}
            ),
        )

        preview = client.post(
            "/api/imports/preview",
            data={"file": (workbook, "partial-khs-update.xlsx")},
            content_type="multipart/form-data",
        )
        assert preview.status_code == 201, preview.get_json()
        preview_payload = preview.get_json()
        assert preview_payload["template_version"] == "2.3"
        assert preview_payload["summary"]["can_import"] is True
        assert preview_payload["summary"]["total_requests"] == 0
        assert preview_payload["summary"]["total_khs_items"] == 1
        assert preview_payload["summary"]["error_rows"] == 0
        batch_id = preview_payload["batch_id"]

        confirmation = client.post(
            f"/api/imports/{batch_id}/confirm",
            json={"accept_warnings": True},
        )
        assert confirmation.status_code == 200, confirmation.get_json()
        assert confirmation.get_json()["result"]["updated_items"] == 1

        with pool.connection() as conn:
            persisted = conn.execute(
                """
                SELECT khs_inject_start_date, khs_inject_completion_date
                FROM khs_items
                WHERE khs_id = %s
                """,
                (khs_id,),
            ).fetchone()

        assert persisted == (date(2026, 11, 13), date(2026, 11, 14))
    finally:
        with pool.connection() as conn, conn.transaction():
            conn.execute(
                "DELETE FROM khs_activity_logs WHERE entity_type='KHS_ITEM' AND entity_id=%s",
                (khs_id,),
            )
            conn.execute("DELETE FROM khs_items WHERE khs_id=%s", (khs_id,))
            conn.execute("DELETE FROM khs_requests WHERE request_id=%s", (request_id,))
            if batch_id is not None:
                conn.execute("DELETE FROM khs_import_batches WHERE id=%s", (batch_id,))



def test_download_current_workbook_contains_v23_schema(client):
    response = client.get("/api/imports/workbook.xlsx")

    assert response.status_code == 200
    assert response.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert "attachment;" in response.headers["Content-Disposition"]
    assert response.headers["Cache-Control"] == "no-store"

    workbook = load_workbook(BytesIO(response.data), data_only=True)
    try:
        assert workbook.sheetnames == [
            "00 - Instructions",
            "01 - Request Register",
            "02 - KHS Tracking",
            "03 - Master Data",
        ]
        request_headers = {
            cell.value for cell in workbook["01 - Request Register"][5]
        }
        khs_headers = {
            cell.value for cell in workbook["02 - KHS Tracking"][5]
        }
        assert "Request Subject" in request_headers
        assert "KHS Inject Start Date" in khs_headers
        assert "KHS Inject Completion Date" in khs_headers
        assert "KHS ID" in khs_headers
        assert "Blank cells do not erase existing database values." in workbook["00 - Instructions"]["B7"].value
    finally:
        workbook.close()
