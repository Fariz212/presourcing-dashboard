from io import BytesIO

import pytest
from openpyxl import Workbook, load_workbook

from app import create_app


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
