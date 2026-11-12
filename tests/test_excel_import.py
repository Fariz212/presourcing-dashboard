from datetime import date, datetime
from io import BytesIO
import re
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

from app.services.excel_import import (
    KHS_HEADERS,
    parse_khs_workbook,
)


REQUEST_HEADERS = [
    "Request ID",
    "Request Date",
    "Request / Subject",
    "Total KHS",
    "Completed KHS",
    "In Progress KHS",
    "Request Status",
    "Requester / Owner",
]


def build_workbook(item_overrides=None, extra_items=None):
    wb = Workbook()

    request_ws = wb.active
    request_ws.title = "01 - Request Register"

    for _ in range(3):
        request_ws.append([])

    request_ws.append(REQUEST_HEADERS)

    request_ws.append([
        "REQ-2026-001",
        datetime(2026, 11, 1),
        "KHS Test Request",
        1,
        0,
        1,
        "In Progress",
        "Test User",
    ])

    khs_ws = wb.create_sheet("02 - KHS Tracking")

    for _ in range(3):
        khs_ws.append([])

    headers = list(KHS_HEADERS)
    khs_ws.append(headers)

    item = {
        "KHS ID": "KHS-2026-0001",
        "Request ID": "REQ-2026-001",
        "Source Row No.": 1,
        "Request Date": datetime(2026, 11, 1),
        "Dispatch Date": datetime(2026, 11, 1),
        "Executor": "ALW",
        "Request / Subject": "KHS Test Request",
        "Subtype": "Renewal",
        "Vendor Name": "PT Test Vendor",
        "Contract Start Date": datetime(2027, 1, 1),
        "Contract End Date": datetime(2027, 12, 31),
        "MI Status": "Not Completed",
        "LP Status": "Not Completed",
        "Current Stage": "Dispatch",
        "Overall Status": "In Progress",
        "Legacy Overall Status": None,
        "Legacy Detailed Status": None,
    }

    if item_overrides:
        item.update(item_overrides)

    def append_item(values):
        khs_ws.append([values.get(header) for header in headers])

    append_item(item)

    for extra in extra_items or []:
        append_item({**item, **extra})

    master = wb.create_sheet("03 - Master Data")
    master.append(["MASTER DATA"])
    master.append([])
    master.append(["Executor", "Subtype", "Waiting For"])
    master.append(["ALW", "Renewal", "Requester / User"])
    master.append(["AME", "Kontrak Baru", "Executor"])

    output = BytesIO()
    wb.save(output)
    output.seek(0)

    return output


def test_valid_template_parses_successfully():
    result = parse_khs_workbook(
        build_workbook(),
        known_executors={"ALW", "AME"},
    )

    assert result["summary"]["can_import"] is True
    assert result["summary"]["total_requests"] == 1
    assert result["summary"]["total_khs_items"] == 1
    assert result["summary"]["error_count"] == 0

    item = result["items"][0]

    assert item["khs_id"] == "KHS-2026-0001"
    assert item["executor_code"] == "ALW"
    assert item["subtype"] == "Renewal"
    assert item["dispatch_date"] == date(2026, 11, 1)


def test_lp_start_without_mi_gm_generates_warning():
    result = parse_khs_workbook(
        build_workbook({
            "LP Circulation Start Date": datetime(2026, 11, 10),
            "Original Source Column S (Audit Copy - LP Circulation Start Date)": datetime(2026, 11, 10),
        }),
        known_executors={"ALW"},
    )

    codes = {issue["code"] for issue in result["issues"]}

    assert result["summary"]["can_import"] is True
    assert "LP_START_WITHOUT_MI_GM_DATE" in codes


def test_lp_completion_before_start_is_rejected():
    result = parse_khs_workbook(
        build_workbook({
            "LP Circulation Start Date": datetime(2026, 11, 10),
            "LP Completion Date (Director Signed)": datetime(2026, 11, 9),
        }),
        known_executors={"ALW"},
    )

    codes = {issue["code"] for issue in result["issues"]}

    assert result["summary"]["can_import"] is False
    assert "LP_COMPLETION_BEFORE_START" in codes


def test_unknown_executor_is_rejected():
    result = parse_khs_workbook(
        build_workbook({"Executor": "ZZZ"}),
        known_executors={"ALW", "AME"},
    )

    codes = {issue["code"] for issue in result["issues"]}

    assert result["summary"]["can_import"] is False
    assert "UNKNOWN_EXECUTOR" in codes


def test_database_executor_missing_from_template_generates_warning():
    result = parse_khs_workbook(
        build_workbook(),
        known_executors={"ALW", "AME", "FZK"},
    )

    codes = {issue["code"] for issue in result["issues"]}

    assert result["summary"]["can_import"] is True
    assert "EXECUTOR_MASTER_MISMATCH" in codes


def test_duplicate_khs_id_is_rejected():
    result = parse_khs_workbook(
        build_workbook(
            extra_items=[{
                "KHS ID": "KHS-2026-0001",
                "Vendor Name": "PT Another Vendor",
            }]
        ),
        known_executors={"ALW"},
    )

    codes = {issue["code"] for issue in result["issues"]}

    assert result["summary"]["can_import"] is False
    assert "DUPLICATE_KHS_ID" in codes


def test_parser_supports_missing_worksheet_dimensions():
    original = build_workbook().getvalue()
    rewritten = BytesIO()

    with ZipFile(BytesIO(original), "r") as source_zip:
        with ZipFile(rewritten, "w", ZIP_DEFLATED) as target_zip:
            for info in source_zip.infolist():
                data = source_zip.read(info.filename)

                if (
                    info.filename.startswith("xl/worksheets/")
                    and info.filename.endswith(".xml")
                ):
                    data = re.sub(
                        rb"<dimension\\b[^>]*/>",
                        b"",
                        data,
                    )

                target_zip.writestr(info, data)

    rewritten.seek(0)

    result = parse_khs_workbook(
        rewritten,
        known_executors={"ALW", "AME"},
    )

    assert result["summary"]["can_import"] is True
    assert result["summary"]["total_requests"] == 1
    assert result["summary"]["total_khs_items"] == 1
    assert result["items"][0]["executor_code"] == "ALW"
