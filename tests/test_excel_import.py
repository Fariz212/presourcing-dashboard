from datetime import date, datetime
from io import BytesIO
import re
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook, load_workbook

from app.services.excel_import import (
    KHS_HEADERS,
    parse_khs_workbook,
)
from app.services.excel_workbook import build_current_khs_workbook


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


def build_workbook(item_overrides=None, extra_items=None, legacy_v22=False, legacy_v23=False):
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
    if legacy_v22 or legacy_v23:
        legacy_only_headers = {
            "LP Contract Team Completion Date",
            "LP Junior Manager Approval Date",
            "LP Senior Manager Approval Date",
            "LP GM SCM Approval Date",
        }
        headers = [header for header in headers if header not in legacy_only_headers]
    if legacy_v23:
        headers.extend(["KHS Inject Start Date", "KHS Inject Completion Date"])
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
        "Last Updated": datetime(2026, 11, 10),
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
    assert "last_updated_date" not in item



def test_legacy_v22_workbook_remains_supported():
    result = parse_khs_workbook(
        build_workbook(legacy_v22=True),
        known_executors={"ALW", "AME"},
        known_requests={},
    )
    assert result["summary"]["can_import"] is True
    assert result["template_version"] == "2.2-compatible"


def test_legacy_v23_workbook_remains_supported():
    result = parse_khs_workbook(
        build_workbook(legacy_v23=True),
        known_executors={"ALW", "AME"},
        known_requests={},
    )
    assert result["summary"]["can_import"] is True
    assert result["template_version"] == "2.3"


def test_current_v24_workbook_round_trips_lp_and_khs_inject_dates():
    workbook = build_current_khs_workbook(
        requests=[{
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Annual maintenance contract",
            "requester_owner": "Procurement",
            "vendor_summary": "PT Test Vendor",
            "total_khs": 1,
            "completed_khs": 0,
            "open_khs": 1,
            "request_status": "In Progress",
        }],
        items=[{
            "khs_id": "KHS-2026-0001",
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Annual maintenance contract",
            "vendor_name": "PT Test Vendor",
            "executor_code": "ALW",
            "subtype": "Renewal",
            "dispatch_date": date(2026, 11, 2),
            "lp_circulation_start_date": date(2026, 11, 10),
            "lp_contract_team_completion_date": date(2026, 11, 11),
            "lp_junior_manager_approval_date": date(2026, 11, 12),
            "lp_senior_manager_approval_date": date(2026, 11, 13),
            "lp_gm_scm_approval_date": date(2026, 11, 14),
            "lp_completion_date": date(2026, 11, 15),
            "khs_inject_start_date": date(2026, 11, 16),
            "khs_inject_completion_date": date(2026, 11, 17),
        }],
        executors=[{"executor_code": "ALW", "display_name": "Executor A"}],
        subtypes=["Renewal", "Kontrak Baru"],
        waiting_for=["Executor", "Requester / User"],
    )

    result = parse_khs_workbook(
        workbook,
        known_executors={"ALW"},
        known_requests={
            "REQ-2026-001": {
                "request_date": date(2026, 11, 1),
                "request_subject": "Annual maintenance contract",
            }
        },
    )

    assert result["template_version"] == "2.4"
    assert result["summary"]["can_import"] is True
    item = result["items"][0]
    assert item["lp_contract_team_completion_date"] == date(2026, 11, 11)
    assert item["lp_junior_manager_approval_date"] == date(2026, 11, 12)
    assert item["lp_senior_manager_approval_date"] == date(2026, 11, 13)
    assert item["lp_gm_scm_approval_date"] == date(2026, 11, 14)
    assert item["khs_inject_start_date"] == date(2026, 11, 16)
    assert item["khs_inject_completion_date"] == date(2026, 11, 17)


def test_khs_only_partial_workbook_can_reference_existing_request():
    workbook = build_current_khs_workbook(
        requests=[],
        items=[{
            "khs_id": "KHS-2026-0001",
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Annual maintenance contract",
            "vendor_name": "PT Test Vendor",
            "executor_code": "ALW",
            "subtype": "Renewal",
            "lp_circulation_start_date": date(2026, 11, 10),
            "lp_completion_date": date(2026, 11, 12),
            "khs_inject_start_date": date(2026, 11, 13),
        }],
        executors=[{"executor_code": "ALW", "display_name": "Executor A"}],
        subtypes=["Renewal", "Kontrak Baru"],
    )

    result = parse_khs_workbook(
        workbook,
        known_executors={"ALW"},
        known_requests={
            "REQ-2026-001": {
                "request_date": date(2026, 11, 1),
                "request_subject": "Annual maintenance contract",
            }
        },
    )

    assert result["summary"]["can_import"] is True
    assert result["requests"] == []
    assert result["items"][0]["request_id"] == "REQ-2026-001"


def test_request_register_edit_does_not_flag_its_own_khs_snapshot_as_stale():
    workbook = build_current_khs_workbook(
        requests=[{
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 2),
            "request_subject": "Updated request subject",
        }],
        items=[{
            "khs_id": "KHS-2026-0001",
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Original request subject",
            "vendor_name": "PT Test Vendor",
            "dispatch_date": date(2026, 11, 3),
        }],
        executors=[],
    )
    result = parse_khs_workbook(
        workbook,
        known_executors=set(),
        known_requests={
            "REQ-2026-001": {
                "request_date": date(2026, 11, 1),
                "request_subject": "Original request subject",
            }
        },
        known_items={
            "KHS-2026-0001": {
                "khs_id": "KHS-2026-0001",
                "request_id": "REQ-2026-001",
                "vendor_name": "PT Test Vendor",
            }
        },
    )

    codes = {issue["code"] for issue in result["issues"]}
    assert result["summary"]["can_import"] is True
    assert "REQUEST_DATE_MISMATCH" not in codes
    assert "REQUEST_SUBJECT_MISMATCH" not in codes


def test_minimal_khs_row_uses_existing_values_for_validation_and_matching():
    workbook = build_current_khs_workbook(
        requests=[],
        items=[{
            "khs_id": "KHS-2026-0001",
            "request_id": None,
            "request_date": None,
            "request_subject": None,
            "vendor_name": None,
            "khs_inject_start_date": date(2026, 11, 13),
        }],
        executors=[],
    )

    result = parse_khs_workbook(
        workbook,
        known_executors={"ALW"},
        known_requests={
            "REQ-2026-001": {
                "request_date": date(2026, 11, 1),
                "request_subject": "Annual maintenance contract",
            }
        },
        known_items={
            "KHS-2026-0001": {
                "khs_id": "KHS-2026-0001",
                "request_id": "REQ-2026-001",
                "vendor_name": "PT Test Vendor",
                "lp_circulation_start_date": date(2026, 11, 10),
                "lp_completion_date": date(2026, 11, 12),
            }
        },
    )

    assert result["summary"]["can_import"] is True
    assert result["items"][0]["request_id"] == "REQ-2026-001"
    assert result["items"][0]["vendor_name"] == "PT Test Vendor"
    assert result["items"][0]["khs_inject_start_date"] == date(2026, 11, 13)


def test_inject_completion_chronology_is_validated():
    workbook = build_current_khs_workbook(
        requests=[{
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Annual maintenance contract",
        }],
        items=[{
            "khs_id": "KHS-2026-0001",
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Annual maintenance contract",
            "vendor_name": "PT Test Vendor",
            "executor_code": "ALW",
            "subtype": "Renewal",
            "lp_circulation_start_date": date(2026, 11, 10),
            "lp_completion_date": date(2026, 11, 12),
            "khs_inject_start_date": date(2026, 11, 13),
            "khs_inject_completion_date": date(2026, 11, 12),
        }],
        executors=[{"executor_code": "ALW", "display_name": "Executor A"}],
        subtypes=["Renewal", "Kontrak Baru"],
    )
    result = parse_khs_workbook(
        workbook,
        known_executors={"ALW"},
        known_requests={
            "REQ-2026-001": {
                "request_date": date(2026, 11, 1),
                "request_subject": "Annual maintenance contract",
            }
        },
    )
    codes = {issue["code"] for issue in result["issues"]}
    assert result["summary"]["can_import"] is False
    assert "INJECT_COMPLETION_BEFORE_START" in codes

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


def test_generated_workbook_stores_untrusted_text_as_plain_excel_text():
    workbook = build_current_khs_workbook(
        requests=[{
            "request_id": "REQ-2026-001",
            "request_subject": "=HYPERLINK(\"https://invalid.example\",\"click\")",
        }],
        items=[{
            "khs_id": "KHS-2026-0001",
            "request_id": "REQ-2026-001",
            "request_subject": "Safe subject",
            "vendor_name": "=HYPERLINK(\"https://invalid.example\",\"click\")",
        }],
        executors=[],
    )
    output = load_workbook(workbook, data_only=False)
    try:
        vendor_cell = output["02 - KHS Tracking"]["E6"]
        assert vendor_cell.value.startswith("=")
        assert vendor_cell.data_type == "s"
        subject_cell = output["01 - Request Register"]["C6"]
        assert subject_cell.value.startswith("=")
        assert subject_cell.data_type == "s"
    finally:
        output.close()


def test_lp_milestone_chronology_is_validated():
    workbook = build_current_khs_workbook(
        requests=[{
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Annual maintenance contract",
        }],
        items=[{
            "khs_id": "KHS-2026-0001",
            "request_id": "REQ-2026-001",
            "request_date": date(2026, 11, 1),
            "request_subject": "Annual maintenance contract",
            "vendor_name": "PT Test Vendor",
            "executor_code": "ALW",
            "subtype": "Renewal",
            "lp_circulation_start_date": date(2026, 11, 10),
            "lp_contract_team_completion_date": date(2026, 11, 12),
            "lp_junior_manager_approval_date": date(2026, 11, 11),
        }],
        executors=[{"executor_code": "ALW", "display_name": "Executor A"}],
    )
    result = parse_khs_workbook(
        workbook,
        known_executors={"ALW"},
        known_requests={
            "REQ-2026-001": {
                "request_date": date(2026, 11, 1),
                "request_subject": "Annual maintenance contract",
            }
        },
    )
    codes = {issue["code"] for issue in result["issues"]}
    assert result["summary"]["can_import"] is False
    assert "LP_MILESTONE_CHRONOLOGY" in codes
