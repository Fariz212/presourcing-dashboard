from datetime import date, datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.utils import get_column_letter


REQUEST_HEADERS = [
    "Request ID",
    "Request Date",
    "Request Subject",
    "Requester / Owner",
    "Vendors",
    "Total KHS",
    "Fully Injected KHS",
    "Open KHS",
    "Request Status",
]

KHS_HEADERS = [
    "KHS ID",
    "Request ID",
    "Request Date",
    "Request Subject",
    "Vendor Name",
    "Source Row No.",
    "Dispatch Date",
    "Executor",
    "Subtype",
    "Contract Start Date",
    "Contract End Date",
    "BOQ Confirmation Date",
    "Negotiation Date",
    "Final Negotiation Date",
    "MI Head Approval Date",
    "MI SM Approval Date",
    "MI GM Approval Date",
    "MI Status",
    "Legal Submission Date",
    "LP Circulation Start Date",
    "LP Contract Team Completion Date",
    "LP Junior Manager Approval Date",
    "LP Senior Manager Approval Date",
    "LP GM SCM Approval Date",
    "LP Completion Date",
    "LP Status",
    "KHS Inject Start Date",
    "KHS Inject Completion Date",
    "Workflow Status",
    "Current Stage",
    "Waiting For",
    "Waiting Reason",
    "Last Updated",
    "Remarks",
    "Legacy Overall Status",
    "Legacy Detailed Status",
    "Original Source Column S (Audit Copy - LP Circulation Start Date)",
    "Migration Review",
]

MASTER_HEADERS = ["Executor", "Executor Name", "Subtype", "Waiting For"]

DATE_COLUMNS = {
    "Request Date",
    "Dispatch Date",
    "Contract Start Date",
    "Contract End Date",
    "BOQ Confirmation Date",
    "Negotiation Date",
    "Final Negotiation Date",
    "MI Head Approval Date",
    "MI SM Approval Date",
    "MI GM Approval Date",
    "Legal Submission Date",
    "LP Circulation Start Date",
    "LP Contract Team Completion Date",
    "LP Junior Manager Approval Date",
    "LP Senior Manager Approval Date",
    "LP GM SCM Approval Date",
    "LP Completion Date",
    "KHS Inject Start Date",
    "KHS Inject Completion Date",
    "Last Updated",
}

STAGE_NAMES = {
    "REQUEST_RECEIVED": "Request Received",
    "DISPATCH": "Dispatch",
    "BOQ_CONFIRMATION": "BOQ Confirmation",
    "NEGOTIATION": "Negotiation",
    "FINAL_NEGOTIATION": "Final Negotiation",
    "MI_HEAD_APPROVAL": "MI Approval - Head",
    "MI_SM_APPROVAL": "MI Approval - SM",
    "MI_GM_APPROVAL": "MI Approval - GM",
    "LEGAL_SUBMISSION": "Legal Submission",
    "LEGAL_PROCESSING": "Legal Processing",
    "LP_CIRCULATION": "LP Circulation",
    "KHS_INJECTION": "KHS Inject",
    "COMPLETED": "Fully Injected",
}


def _date_value(value):
    if isinstance(value, datetime):
        return value.date()
    return value


def _workflow_stage(item):
    if item.get("khs_inject_completion_date"):
        return "COMPLETED"
    if item.get("lp_completion_date"):
        return "KHS_INJECTION"
    if item.get("lp_circulation_start_date"):
        return "LP_CIRCULATION"
    if item.get("legal_submission_date"):
        return "LEGAL_PROCESSING"
    if item.get("mi_gm_approval_date"):
        return "LEGAL_SUBMISSION"
    if item.get("mi_sm_approval_date"):
        return "MI_GM_APPROVAL"
    if item.get("mi_head_approval_date"):
        return "MI_SM_APPROVAL"
    if item.get("final_negotiation_date"):
        return "MI_HEAD_APPROVAL"
    if item.get("negotiation_date"):
        return "FINAL_NEGOTIATION"
    if item.get("boq_confirmation_date"):
        return "NEGOTIATION"
    if item.get("dispatch_date"):
        return "BOQ_CONFIRMATION"
    if item.get("request_date"):
        return "DISPATCH"
    return "REQUEST_RECEIVED"


def _style_sheet(ws, header_row, headers, widths):
    ws.freeze_panes = f"A{header_row + 1}"
    ws.auto_filter.ref = (
        f"A{header_row}:{get_column_letter(len(headers))}"
        f"{max(header_row, ws.max_row)}"
    )
    ws.sheet_view.showGridLines = False
    for cell in ws[header_row]:
        cell.fill = PatternFill("solid", fgColor="183153")
        cell.font = Font(name="Aptos", bold=True, color="FFFFFF", size=10)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = Border(bottom=Side(style="thin", color="A9B8CC"))
    ws.row_dimensions[header_row].height = 34
    for col, width in widths.items():
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=False)
            if cell.column % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F4F7FB")
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            if cell.is_date:
                cell.number_format = "dd/mm/yyyy"


def _write_cell(cell, value):
    if isinstance(value, (datetime, date)):
        cell.value = _date_value(value)
        cell.number_format = "dd/mm/yyyy"
        return
    if isinstance(value, str):
        cell.value = value
        # Force text storage so source values beginning with '=' are not formulas.
        cell.data_type = "s"
        return
    cell.value = value


def _add_sheet_title(ws, title, note):
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)
    ws["A1"] = title
    ws["A1"].font = Font(name="Aptos Display", bold=True, size=16, color="183153")
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 28
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=8)
    ws["A2"] = note
    ws["A2"].font = Font(name="Aptos", italic=True, size=10, color="596579")
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[2].height = 32


def build_current_khs_workbook(requests, items, executors, subtypes=None, waiting_for=None):
    """Build an editable current-data workbook using the active KHS import schema."""
    wb = Workbook()
    wb.properties.title = "KHS Contract Creation Monitoring — Current Workbook"
    wb.properties.subject = "Current KHS records for controlled Excel review and update"
    wb.properties.creator = "KHS Contract Creation Monitoring"

    instructions = wb.active
    instructions.title = "00 - Instructions"
    instructions.sheet_view.showGridLines = False
    instructions.column_dimensions["A"].width = 28
    instructions.column_dimensions["B"].width = 100
    instructions["A1"] = "KHS CONTRACT CREATION MONITORING"
    instructions["A1"].font = Font(name="Aptos Display", bold=True, size=17, color="183153")
    instructions["A3"] = "Workbook version"
    instructions["B3"] = "2.4 — LP approval milestones and contract lifecycle"
    instructions["A4"] = "Purpose"
    instructions["B4"] = "This workbook is a snapshot of the current database records. Edit the existing rows and upload it through Excel Import / Export to preview and apply updates."
    instructions["A5"] = "Matching keys"
    instructions["B5"] = "Keep Request ID and KHS ID unchanged. They identify the records to update."
    instructions["A6"] = "Partial updates"
    instructions["B6"] = "You may upload only the Request rows and/or KHS rows you changed. A KHS row may reference an existing Request without that Request being repeated in this workbook."
    instructions["A7"] = "Blank cells"
    instructions["B7"] = "Blank cells do not erase existing database values. This protects data when a column is not being maintained in Excel."
    instructions["A8"] = "Clearing values"
    instructions["B8"] = "To intentionally clear a value, use the KHS web form. Blank Excel cells are treated as 'no change'."
    instructions["A9"] = "New records"
    instructions["B9"] = "Create new Requests and KHS records in the web application so IDs are generated safely. This workbook is designed for checking and updating existing records."
    instructions["A10"] = "Deletion"
    instructions["B10"] = "Deleting a row from this workbook does not delete the database record."
    instructions["A11"] = "Computed columns"
    instructions["B11"] = "Total KHS, status, current stage, and other derived columns are for reference only; they are not imported."
    instructions["A12"] = "KHS Inject"
    instructions["B12"] = "KHS Inject starts only after LP Completion. KHS is fully complete only when KHS Inject Completion Date is populated."
    instructions["A13"] = "Legacy workbooks"
    instructions["B13"] = "Existing v2.2 and v2.3 workbooks remain accepted. For new updates, download this current workbook so all LP milestones are available."
    instructions["A14"] = "Workflow"
    instructions["B14"] = "Review the Preview result and all warnings/errors before selecting Confirm Import. Preview does not change master records."
    instructions["A15"] = "Contract Lifecycle"
    instructions["B15"] = "Expiry monitoring starts only after KHS Inject Completion Date. Alert stages are calculated from Contract End Date; no alert status is imported."
    instructions["A16"] = "LP Timeline"
    instructions["B16"] = "Current LP stage and stage age are calculated from milestone dates. Blank historical milestone dates remain blank; do not invent dates."
    for row in range(3, 17):
        instructions[f"A{row}"].font = Font(bold=True, color="183153")
        instructions[f"A{row}"].alignment = Alignment(vertical="top")
        instructions[f"B{row}"].alignment = Alignment(wrap_text=True, vertical="top")
        instructions.row_dimensions[row].height = 38

    request_ws = wb.create_sheet("01 - Request Register")
    _add_sheet_title(
        request_ws,
        "REQUEST REGISTER",
        "Edit existing Request fields only. Request ID is the matching key; vendor and aggregate columns are reference information.",
    )
    request_header_row = 5
    for col, header in enumerate(REQUEST_HEADERS, start=1):
        _write_cell(request_ws.cell(request_header_row, col), header)
    for record in requests:
        row = [
            record.get("request_id"),
            record.get("request_date"),
            record.get("request_subject"),
            record.get("requester_owner"),
            record.get("vendor_summary"),
            record.get("total_khs", 0),
            record.get("completed_khs", 0),
            record.get("open_khs", 0),
            record.get("request_status"),
        ]
        request_ws.append([None] * len(REQUEST_HEADERS))
        for col, value in enumerate(row, start=1):
            _write_cell(request_ws.cell(request_ws.max_row, col), value)
    _style_sheet(
        request_ws,
        request_header_row,
        REQUEST_HEADERS,
        {"A": 20, "B": 15, "C": 48, "D": 26, "E": 48, "F": 14, "G": 18, "H": 14, "I": 20},
    )

    khs_ws = wb.create_sheet("02 - KHS Tracking")
    _add_sheet_title(
        khs_ws,
        "KHS TRACKING",
        "Edit the existing KHS row using KHS ID. The Request Subject and status columns are for context; stage/status columns are calculated and ignored on import.",
    )
    khs_header_row = 5
    for col, header in enumerate(KHS_HEADERS, start=1):
        _write_cell(khs_ws.cell(khs_header_row, col), header)

    for record in items:
        workflow_status = (
            "Completed" if record.get("khs_inject_completion_date")
            else "In Progress" if any(record.get(field) for field in (
                "dispatch_date", "boq_confirmation_date", "negotiation_date",
                "final_negotiation_date", "mi_head_approval_date", "mi_sm_approval_date",
                "mi_gm_approval_date", "legal_submission_date",
                "lp_circulation_start_date", "lp_completion_date",
            ))
            else "Not Started"
        )
        lp_status = (
            "Completed" if record.get("lp_completion_date")
            else "In Progress" if record.get("lp_circulation_start_date")
            else "Not Started"
        )
        stage_code = _workflow_stage(record)
        row = [
            record.get("khs_id"),
            record.get("request_id"),
            record.get("request_date"),
            record.get("request_subject"),
            record.get("vendor_name"),
            record.get("source_row_no"),
            record.get("dispatch_date"),
            record.get("executor_code"),
            record.get("subtype"),
            record.get("contract_start_date"),
            record.get("contract_end_date"),
            record.get("boq_confirmation_date"),
            record.get("negotiation_date"),
            record.get("final_negotiation_date"),
            record.get("mi_head_approval_date"),
            record.get("mi_sm_approval_date"),
            record.get("mi_gm_approval_date"),
            "Completed" if record.get("mi_gm_approval_date") else "Not Completed",
            record.get("legal_submission_date"),
            record.get("lp_circulation_start_date"),
            record.get("lp_contract_team_completion_date"),
            record.get("lp_junior_manager_approval_date"),
            record.get("lp_senior_manager_approval_date"),
            record.get("lp_gm_scm_approval_date"),
            record.get("lp_completion_date"),
            lp_status,
            record.get("khs_inject_start_date"),
            record.get("khs_inject_completion_date"),
            workflow_status,
            STAGE_NAMES.get(stage_code, stage_code),
            record.get("waiting_for"),
            record.get("waiting_reason"),
            record.get("last_updated_date"),
            record.get("remarks"),
            record.get("legacy_overall_status"),
            record.get("legacy_detailed_status"),
            record.get("source_col_s_audit_date"),
            record.get("migration_review"),
        ]
        khs_ws.append([None] * len(KHS_HEADERS))
        for col, value in enumerate(row, start=1):
            _write_cell(khs_ws.cell(khs_ws.max_row, col), value)

    khs_widths = {
        "A": 20, "B": 20, "C": 15, "D": 42, "E": 34, "F": 14, "G": 15,
        "H": 18, "I": 18, "J": 16, "K": 16, "L": 18, "M": 16, "N": 18,
        "O": 18, "P": 18, "Q": 18, "R": 17, "S": 18, "T": 19,
        "U": 25, "V": 25, "W": 25, "X": 21, "Y": 19, "Z": 16,
        "AA": 18, "AB": 20, "AC": 17, "AD": 22, "AE": 20, "AF": 42,
        "AG": 15, "AH": 42, "AI": 24, "AJ": 28, "AK": 40, "AL": 28,
    }
    _style_sheet(khs_ws, khs_header_row, KHS_HEADERS, khs_widths)

    master_ws = wb.create_sheet("03 - Master Data")
    _add_sheet_title(
        master_ws,
        "MASTER DATA",
        "Reference values for Excel dropdowns. Active Executor codes are validated against the database during preview.",
    )
    master_header_row = 5
    for col, header in enumerate(MASTER_HEADERS, start=1):
        _write_cell(master_ws.cell(master_header_row, col), header)
    max_rows = max(len(executors), len(subtypes or []), len(waiting_for or []), 1)
    for index in range(max_rows):
        values = [
            executors[index].get("executor_code") if index < len(executors) else None,
            executors[index].get("display_name") if index < len(executors) else None,
            (subtypes or [])[index] if index < len(subtypes or []) else None,
            (waiting_for or [])[index] if index < len(waiting_for or []) else None,
        ]
        master_ws.append([None] * len(MASTER_HEADERS))
        for col, value in enumerate(values, start=1):
            _write_cell(master_ws.cell(master_ws.max_row, col), value)
    _style_sheet(
        master_ws,
        master_header_row,
        MASTER_HEADERS,
        {"A": 18, "B": 34, "C": 20, "D": 28},
    )

    # Inline-list validations are safe for the short master lists used here.
    executor_values = [str(row.get("executor_code", "")).replace('"', '""') for row in executors if row.get("executor_code")]
    subtype_values = [str(value).replace('"', '""') for value in (subtypes or [])]
    if executor_values and len(",".join(executor_values)) <= 240:
        validation = DataValidation(
            type="list",
            formula1='"' + ",".join(executor_values) + '"',
            allow_blank=True,
        )
        khs_ws.add_data_validation(validation)
        validation.add(f"H{khs_header_row + 1}:H1048576")
    if subtype_values and len(",".join(subtype_values)) <= 240:
        validation = DataValidation(
            type="list",
            formula1='"' + ",".join(subtype_values) + '"',
            allow_blank=True,
        )
        khs_ws.add_data_validation(validation)
        validation.add(f"I{khs_header_row + 1}:I1048576")

    waiting_values = [
        str(value).replace('"', '""')
        for value in (waiting_for or [])
        if value and "," not in str(value)
    ]
    if waiting_values and len(",".join(waiting_values)) <= 240:
        validation = DataValidation(
            type="list",
            formula1='"' + ",".join(waiting_values) + '"',
            allow_blank=True,
        )
        khs_ws.add_data_validation(validation)
        validation.add(f"AA{khs_header_row + 1}:AA1048576")

    output = BytesIO()
    wb.save(output)
    output.seek(0)
    wb.close()
    return output
