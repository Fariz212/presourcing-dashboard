from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re

from openpyxl import load_workbook
from openpyxl.utils.datetime import from_excel


REQUEST_SHEET = "01 - Request Register"
KHS_SHEET = "02 - KHS Tracking"
MASTER_SHEET = "03 - Master Data"

REQUEST_HEADERS = {
    "Request ID",
    "Request Date",
    "Request / Subject",
    "Requester / Owner",
}

KHS_HEADERS = {
    "KHS ID",
    "Request ID",
    "Source Row No.",
    "Request Date",
    "Dispatch Date",
    "Executor",
    "Request / Subject",
    "Subtype",
    "Vendor Name",
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
    "LP Completion Date (Director Signed)",
    "LP Status",
    "Current Stage",
    "Overall Status",
    "Processing Days",
    "Waiting For",
    "Waiting Reason",
    "Last Updated",
    "Remarks",
    "Legacy Overall Status",
    "Legacy Detailed Status",
    "Original Source Column S (Audit Copy - LP Circulation Start Date)",
    "Migration Review",
}

REQUEST_DATE_FIELDS = {
    "Request Date": "request_date",
}

ITEM_DATE_FIELDS = {
    "Dispatch Date": "dispatch_date",
    "Contract Start Date": "contract_start_date",
    "Contract End Date": "contract_end_date",
    "BOQ Confirmation Date": "boq_confirmation_date",
    "Negotiation Date": "negotiation_date",
    "Final Negotiation Date": "final_negotiation_date",
    "MI Head Approval Date": "mi_head_approval_date",
    "MI SM Approval Date": "mi_sm_approval_date",
    "MI GM Approval Date": "mi_gm_approval_date",
    "Legal Submission Date": "legal_submission_date",
    "LP Circulation Start Date": "lp_circulation_start_date",
    "LP Contract Team Completion Date": "lp_contract_team_completion_date",
    "LP Junior Manager Approval Date": "lp_junior_manager_approval_date",
    "LP Senior Manager Approval Date": "lp_senior_manager_approval_date",
    "LP GM SCM Approval Date": "lp_gm_scm_approval_date",
    "LP Completion Date (Director Signed)": "lp_completion_date",
    "KHS Inject Start Date": "khs_inject_start_date",
    "KHS Inject Completion Date": "khs_inject_completion_date",
    "Original Source Column S (Audit Copy - LP Circulation Start Date)": "source_col_s_audit_date",
}

SUBTYPE_MAP = {
    "renewal": "Renewal",
    "kontrak baru": "Kontrak Baru",
}


class WorkbookImportError(ValueError):
    """Raised when an uploaded workbook is not compatible with the KHS v2.4 schema."""

    
HEADER_ALIASES = {
    "Request / Subject": ("Request / Subject", "Request Subject"),
    "LP Completion Date (Director Signed)": (
        "LP Completion Date (Director Signed)",
        "LP Completion Date",
    ),
    "KHS Inject Start Date": (
        "KHS Inject Start Date",
        "KHS Injection Start Date",
    ),
    "KHS Inject Completion Date": (
        "KHS Inject Completion Date",
        "KHS Fully Injected Date",
    ),
}

REQUEST_REQUIRED_HEADERS = {"Request ID"}
KHS_REQUIRED_HEADERS = {"KHS ID"}


def _text(value):
    if value is None:
        return None

    result = str(value).strip()
    return result or None


def _normalized_subject(value):
    text = _text(value)
    return re.sub(r"\s+", " ", text).casefold() if text else None


def _find_header_row(ws, required_headers, label):
    """
    Detect headers even when worksheet XML omits its dimension metadata.

    In read_only mode, OpenPyXL may report max_row/max_column as None.
    calculate_dimension(force=True) scans the worksheet XML and restores
    the correct dimensions before row and column indexing.
    """

    try:
        ws.calculate_dimension(force=True)
    except Exception as exc:
        raise WorkbookImportError(
            f"Unable to inspect worksheet dimensions for '{label}': {exc}"
        ) from exc

    max_row = ws.max_row
    scan_limit = min(max_row or 15, 15)

    discovered_headers = set()

    for row_number in range(1, scan_limit + 1):
        values = next(
            ws.iter_rows(
                min_row=row_number,
                max_row=row_number,
                values_only=True,
            ),
            (),
        )

        mapping = {
            str(value).strip(): index
            for index, value in enumerate(values)
            if value is not None and str(value).strip()
        }

        discovered_headers.update(mapping)

        if required_headers.issubset(mapping):
            return row_number, mapping

    missing = sorted(required_headers - discovered_headers)

    raise WorkbookImportError(
        f"Sheet '{label}' does not contain the required workbook headers. "
        f"Missing: {', '.join(missing)}"
    )


def _header_index(header_map, field):
    for candidate in HEADER_ALIASES.get(field, (field,)):
        index = header_map.get(candidate)
        if index is not None:
            return index
    return None


def _value(cells, header_map, field):
    index = _header_index(header_map, field)

    if index is None or index >= len(cells):
        return None

    return cells[index].value


def _parse_date(value, epoch):
    if value is None or value == "":
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, bool):
        raise ValueError("Boolean is not a valid date.")

    if isinstance(value, (int, float)):
        converted = from_excel(value, epoch)

        if isinstance(converted, datetime):
            return converted.date()

        if isinstance(converted, date):
            return converted

        raise ValueError("Excel value does not represent a date.")

    if isinstance(value, str):
        raw = value.strip()

        formats = (
            "%Y-%m-%d",
            "%d/%m/%Y",
            "%d-%m-%Y",
            "%Y/%m/%d",
            "%d %B %Y",
            "%d %b %Y",
        )

        for fmt in formats:
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                continue

    raise ValueError(f"Unsupported date value: {value!r}")


def _add_issue(issues, severity, code, entity, row, field, message):
    issues.append({
        "severity": severity,
        "code": code,
        "entity": entity,
        "row": row,
        "field": field,
        "message": message,
    })


def _date_fields(cells, header_map, field_map, epoch,
                 issues, entity, row_number):
    result = {}

    for header, target in field_map.items():
        raw = _value(cells, header_map, header)

        try:
            result[target] = _parse_date(raw, epoch)
        except (ValueError, OverflowError, TypeError) as exc:
            result[target] = None
            _add_issue(
                issues,
                "ERROR",
                "INVALID_DATE",
                entity,
                row_number,
                header,
                str(exc),
            )

    return result


def _source_row_number(value, issues, row_number):
    if value in (None, ""):
        return None

    try:
        number = int(value)

        if float(value) != number or number < 1:
            raise ValueError

        return number

    except (TypeError, ValueError, OverflowError):
        _add_issue(
            issues,
            "ERROR",
            "INVALID_SOURCE_ROW",
            "KHS_ITEM",
            row_number,
            "Source Row No.",
            "Source Row No. must be a positive integer.",
        )
        return None


def _read_template_executors(workbook, issues):
    if MASTER_SHEET not in workbook.sheetnames:
        _add_issue(
            issues,
            "WARNING",
            "MASTER_SHEET_MISSING",
            "WORKBOOK",
            None,
            MASTER_SHEET,
            "Master Data sheet is missing.",
        )
        return set()

    ws = workbook[MASTER_SHEET]

    try:
        header_row, mapping = _find_header_row(
            ws, {"Executor"}, MASTER_SHEET
        )
    except WorkbookImportError:
        return set()

    index = mapping["Executor"]
    codes = set()

    for row in ws.iter_rows(
        min_row=header_row + 1,
        values_only=True,
    ):
        if index < len(row):
            code = _text(row[index])

            if code:
                codes.add(code.upper())

    return codes


def parse_khs_workbook(file_object, known_executors=None, known_requests=None, known_items=None):
    """
    Parse and validate a KHS workbook for safe insert/update.

    Current v2.4 workbooks include LP approval milestones and KHS Inject fields. Legacy v2.2 and v2.3
    headers remain accepted. Request and KHS IDs are matching keys; rows
    can be partial, provided their parent Request already exists.

    known_executors:
        Optional set of active executor codes obtained from khs_executors.
    known_requests:
        Optional mapping of existing Request IDs to parent metadata
        (request_date and request_subject), obtained from khs_requests.
    known_items:
        Optional mapping of existing KHS IDs to parent/vendor/date metadata,
        obtained from khs_items. Used to validate partial column updates.
    """

    issues = []

    try:
        if hasattr(file_object, "seek"):
            file_object.seek(0)

        workbook = load_workbook(
            file_object,
            read_only=True,
            data_only=True,
        )

    except Exception as exc:
        raise WorkbookImportError(
            f"Unable to read Excel workbook: {exc}"
        ) from exc

    try:
        required_sheets = {REQUEST_SHEET, KHS_SHEET}
        missing_sheets = required_sheets - set(workbook.sheetnames)

        if missing_sheets:
            raise WorkbookImportError(
                "Missing required sheets: "
                + ", ".join(sorted(missing_sheets))
            )

        request_ws = workbook[REQUEST_SHEET]
        khs_ws = workbook[KHS_SHEET]

        request_header_row, request_map = _find_header_row(
            request_ws, REQUEST_REQUIRED_HEADERS, REQUEST_SHEET
        )
        khs_header_row, khs_map = _find_header_row(
            khs_ws, KHS_REQUIRED_HEADERS, KHS_SHEET
        )

        has_inject_start = _header_index(khs_map, "KHS Inject Start Date") is not None
        has_inject_completion = _header_index(khs_map, "KHS Inject Completion Date") is not None
        has_lp_milestones = any(
            _header_index(khs_map, header) is not None
            for header in (
                "LP Contract Team Completion Date",
                "LP Junior Manager Approval Date",
                "LP Senior Manager Approval Date",
                "LP GM SCM Approval Date",
            )
        )

        requests = []
        items = []
        request_lookup = {}
        item_ids = set()

        # -------------------------------------------------
        # REQUEST REGISTER
        # -------------------------------------------------

        for row_number, cells in enumerate(
            request_ws.iter_rows(
                min_row=request_header_row + 1,
                values_only=False,
            ),
            start=request_header_row + 1,
        ):
            request_id = _text(
                _value(cells, request_map, "Request ID")
            )

            subject = _text(
                _value(cells, request_map, "Request / Subject")
            )
            existing_request = (
                known_requests.get(request_id)
                if request_id and isinstance(known_requests, dict)
                else None
            )
            if not subject and existing_request:
                subject = existing_request.get("request_subject")

            if not request_id and not subject:
                continue

            if not request_id:
                _add_issue(
                    issues, "ERROR", "MISSING_REQUEST_ID",
                    "REQUEST", row_number, "Request ID",
                    "Request ID is required.",
                )
                continue

            if request_id in request_lookup:
                _add_issue(
                    issues, "ERROR", "DUPLICATE_REQUEST_ID",
                    "REQUEST", row_number, "Request ID",
                    f"Duplicate Request ID: {request_id}.",
                )
                continue

            if not subject:
                _add_issue(
                    issues, "ERROR", "MISSING_REQUEST_SUBJECT",
                    "REQUEST", row_number, "Request / Subject",
                    "Request / Subject is required.",
                )
                continue

            dates = _date_fields(
                cells,
                request_map,
                REQUEST_DATE_FIELDS,
                workbook.epoch,
                issues,
                "REQUEST",
                row_number,
            )

            record = {
                "source_excel_row": row_number,
                "request_id": request_id,
                "request_date": dates["request_date"],
                "request_subject": subject,
                "requester_owner": _text(
                    _value(cells, request_map, "Requester / Owner")
                ),
            }

            requests.append(record)
            request_lookup[request_id] = record

        # -------------------------------------------------
        # EXECUTOR MASTER CONSISTENCY
        # -------------------------------------------------

        template_executors = _read_template_executors(
            workbook, issues
        )

        if known_executors is not None:
            db_executors = {
                str(code).strip().upper()
                for code in known_executors
            }

            missing_from_template = sorted(
                db_executors - template_executors
            )

            if missing_from_template:
                _add_issue(
                    issues,
                    "WARNING",
                    "EXECUTOR_MASTER_MISMATCH",
                    "WORKBOOK",
                    None,
                    "03 - Master Data",
                    "Database executor codes missing from the "
                    "template dropdown: "
                    + ", ".join(missing_from_template),
                )

        # -------------------------------------------------
        # INDIVIDUAL KHS
        # -------------------------------------------------

        for row_number, cells in enumerate(
            khs_ws.iter_rows(
                min_row=khs_header_row + 1,
                values_only=False,
            ),
            start=khs_header_row + 1,
        ):
            khs_id = _text(_value(cells, khs_map, "KHS ID"))
            existing_item = (
                known_items.get(khs_id)
                if khs_id and isinstance(known_items, dict)
                else None
            )
            request_id = _text(
                _value(cells, khs_map, "Request ID")
            ) or (existing_item or {}).get("request_id")
            vendor = _text(
                _value(cells, khs_map, "Vendor Name")
            ) or (existing_item or {}).get("vendor_name")
            subject = _text(
                _value(cells, khs_map, "Request / Subject")
            )

            if not any((khs_id, request_id, vendor, subject)):
                continue

            row_has_error = False

            for field, value, code in (
                ("KHS ID", khs_id, "MISSING_KHS_ID"),
                ("Request ID", request_id, "MISSING_REQUEST_ID"),
                ("Vendor Name", vendor, "MISSING_VENDOR"),
            ):
                if not value:
                    row_has_error = True
                    _add_issue(
                        issues,
                        "ERROR",
                        code,
                        "KHS_ITEM",
                        row_number,
                        field,
                        f"{field} is required.",
                    )

            if row_has_error:
                continue

            if khs_id in item_ids:
                _add_issue(
                    issues,
                    "ERROR",
                    "DUPLICATE_KHS_ID",
                    "KHS_ITEM",
                    row_number,
                    "KHS ID",
                    f"Duplicate KHS ID: {khs_id}.",
                )
                continue

            item_ids.add(khs_id)

            executor = _text(
                _value(cells, khs_map, "Executor")
            )
            executor = executor.upper() if executor else None

            if executor and known_executors is not None:
                allowed = {
                    str(code).strip().upper()
                    for code in known_executors
                }

                if executor not in allowed:
                    _add_issue(
                        issues,
                        "ERROR",
                        "UNKNOWN_EXECUTOR",
                        "KHS_ITEM",
                        row_number,
                        "Executor",
                        f"Executor {executor} is not active "
                        "in the database master.",
                    )

            subtype_raw = _text(
                _value(cells, khs_map, "Subtype")
            )
            subtype = (
                SUBTYPE_MAP.get(subtype_raw.casefold())
                if subtype_raw else None
            )

            if subtype_raw and subtype is None:
                _add_issue(
                    issues,
                    "ERROR",
                    "INVALID_SUBTYPE",
                    "KHS_ITEM",
                    row_number,
                    "Subtype",
                    f"Unsupported subtype: {subtype_raw}.",
                )

            dates = _date_fields(
                cells,
                khs_map,
                ITEM_DATE_FIELDS,
                workbook.epoch,
                issues,
                "KHS_ITEM",
                row_number,
            )

            try:
                item_request_date = _parse_date(
                    _value(cells, khs_map, "Request Date"),
                    workbook.epoch,
                )
            except (ValueError, OverflowError, TypeError) as exc:
                item_request_date = None
                _add_issue(
                    issues,
                    "ERROR",
                    "INVALID_REQUEST_DATE",
                    "KHS_ITEM",
                    row_number,
                    "Request Date",
                    str(exc),
                )

            existing_parent = (
                known_requests.get(request_id)
                if isinstance(known_requests, dict)
                else None
            )
            parent = request_lookup.get(request_id) or existing_parent

            known_request_ids = (
                set(known_requests)
                if isinstance(known_requests, dict)
                else set(known_requests or ())
            )
            if parent is None and request_id not in known_request_ids:
                _add_issue(
                    issues,
                    "ERROR",
                    "UNKNOWN_REQUEST_ID",
                    "KHS_ITEM",
                    row_number,
                    "Request ID",
                    f"Request ID {request_id} does not exist in this workbook or the database.",
                )

            # If the Request row is included in this workbook, it is the
            # canonical parent update. Its duplicated Request Date/Subject
            # columns in KHS are snapshot context and may legitimately be stale.
            compare_khs_parent_snapshot = request_id not in request_lookup

            if parent and compare_khs_parent_snapshot:
                parent_date = parent.get("request_date")

                if (
                    item_request_date
                    and parent_date
                    and item_request_date != parent_date
                ):
                    _add_issue(
                        issues,
                        "WARNING",
                        "REQUEST_DATE_MISMATCH",
                        "KHS_ITEM",
                        row_number,
                        "Request Date",
                        "Request Date differs from Request Register.",
                    )

                if (
                    subject
                    and _normalized_subject(subject)
                    != _normalized_subject(parent["request_subject"])
                ):
                    _add_issue(
                        issues,
                        "WARNING",
                        "REQUEST_SUBJECT_MISMATCH",
                        "KHS_ITEM",
                        row_number,
                        "Request / Subject",
                        "Subject differs from Request Register.",
                    )

            # ---------------------------------------------
            # BUSINESS CHRONOLOGY VALIDATION
            # ---------------------------------------------

            request_date = (
                parent.get("request_date")
                if parent else (existing_item or {}).get("request_date")
            )
            effective_dates = {
                target: (
                    dates.get(target)
                    if dates.get(target) is not None
                    else (existing_item or {}).get(target)
                )
                for target in set(ITEM_DATE_FIELDS.values())
            }
            dispatch_date = effective_dates["dispatch_date"]

            if (
                request_date
                and dispatch_date
                and dispatch_date < request_date
            ):
                _add_issue(
                    issues,
                    "ERROR",
                    "DISPATCH_BEFORE_REQUEST",
                    "KHS_ITEM",
                    row_number,
                    "Dispatch Date",
                    "Dispatch Date cannot precede Request Date.",
                )

            start_date = effective_dates["contract_start_date"]
            end_date = effective_dates["contract_end_date"]
            contract_date_fields = ("contract_start_date", "contract_end_date")
            contract_dates_changed = any(
                dates.get(field) is not None
                and dates.get(field) != (existing_item or {}).get(field)
                for field in contract_date_fields
            )

            if (
                start_date
                and end_date
                and end_date < start_date
                and contract_dates_changed
            ):
                _add_issue(
                    issues,
                    "ERROR",
                    "INVALID_CONTRACT_DATE_RANGE",
                    "KHS_ITEM",
                    row_number,
                    "Contract End Date",
                    "Contract End Date precedes Contract Start Date.",
                )

            mi_dates = [
                effective_dates["mi_head_approval_date"],
                effective_dates["mi_sm_approval_date"],
                effective_dates["mi_gm_approval_date"],
            ]

            populated_mi_dates = [
                value for value in mi_dates if value is not None
            ]

            if populated_mi_dates != sorted(populated_mi_dates):
                _add_issue(
                    issues,
                    "WARNING",
                    "MI_APPROVAL_CHRONOLOGY",
                    "KHS_ITEM",
                    row_number,
                    "MI Approval Dates",
                    "MI approval dates are not in chronological order.",
                )

            lp_start = effective_dates["lp_circulation_start_date"]
            lp_completion = effective_dates["lp_completion_date"]
            lp_milestone_fields = (
                "lp_contract_team_completion_date",
                "lp_junior_manager_approval_date",
                "lp_senior_manager_approval_date",
                "lp_gm_scm_approval_date",
            )
            all_lp_date_fields = (
                "lp_circulation_start_date",
                *lp_milestone_fields,
                "lp_completion_date",
            )
            # Empty Excel cells and columns absent from legacy v2.2/v2.3
            # workbooks mean "no change". Validate chronology only when an LP
            # milestone is actually being added or changed, so old partial
            # histories do not block unrelated updates.
            lp_milestones_changed = any(
                dates.get(field) is not None
                and dates.get(field) != (existing_item or {}).get(field)
                for field in all_lp_date_fields
            )
            if (
                any(effective_dates.get(field) for field in lp_milestone_fields)
                and not lp_start
                and lp_milestones_changed
            ):
                _add_issue(
                    issues,
                    "ERROR",
                    "LP_MILESTONE_WITHOUT_START",
                    "KHS_ITEM",
                    row_number,
                    "LP Circulation Start Date",
                    "LP intermediate milestones require an LP circulation start date.",
                )

            populated_lp_dates = [
                effective_dates.get(field)
                for field in all_lp_date_fields
                if effective_dates.get(field) is not None
            ]
            if (
                populated_lp_dates != sorted(populated_lp_dates)
                and lp_milestones_changed
            ):
                _add_issue(
                    issues,
                    "ERROR",
                    "LP_MILESTONE_CHRONOLOGY",
                    "KHS_ITEM",
                    row_number,
                    "LP Milestones",
                    "LP milestone dates must be in chronological order.",
                )

            inject_start = effective_dates["khs_inject_start_date"]
            inject_completion = effective_dates["khs_inject_completion_date"]
            inject_dates_changed = any(
                dates.get(field) is not None
                and dates.get(field) != (existing_item or {}).get(field)
                for field in ("khs_inject_start_date", "khs_inject_completion_date")
            )
            mi_gm = effective_dates["mi_gm_approval_date"]

            if lp_start and not mi_gm:
                _add_issue(
                    issues,
                    "WARNING",
                    "LP_START_WITHOUT_MI_GM_DATE",
                    "KHS_ITEM",
                    row_number,
                    "LP Circulation Start Date",
                    "LP circulation is recorded but MI GM Approval "
                    "Date is missing. Verify the source data.",
                )

            elif lp_start and mi_gm and lp_start < mi_gm:
                _add_issue(
                    issues,
                    "WARNING",
                    "LP_START_BEFORE_MI_GM",
                    "KHS_ITEM",
                    row_number,
                    "LP Circulation Start Date",
                    "LP circulation date precedes MI GM approval.",
                )

            if lp_completion and not lp_start and lp_milestones_changed:
                _add_issue(
                    issues,
                    "ERROR",
                    "LP_COMPLETION_WITHOUT_START",
                    "KHS_ITEM",
                    row_number,
                    "LP Completion Date (Director Signed)",
                    "LP completion requires a circulation start date.",
                )

            elif (
                lp_completion
                and lp_start
                and lp_completion < lp_start
                and lp_milestones_changed
            ):
                _add_issue(
                    issues,
                    "ERROR",
                    "LP_COMPLETION_BEFORE_START",
                    "KHS_ITEM",
                    row_number,
                    "LP Completion Date (Director Signed)",
                    "LP completion date cannot precede LP start date.",
                )

            if inject_start and not lp_completion and inject_dates_changed:
                _add_issue(
                    issues,
                    "ERROR",
                    "INJECT_START_WITHOUT_LP_COMPLETION",
                    "KHS_ITEM",
                    row_number,
                    "KHS Inject Start Date",
                    "KHS Inject can only start after LP completion.",
                )

            elif (
                inject_start
                and lp_completion
                and inject_start < lp_completion
                and inject_dates_changed
            ):
                _add_issue(
                    issues,
                    "ERROR",
                    "INJECT_START_BEFORE_LP_COMPLETION",
                    "KHS_ITEM",
                    row_number,
                    "KHS Inject Start Date",
                    "KHS Inject start date cannot precede LP completion.",
                )

            if inject_completion and not inject_start and inject_dates_changed:
                _add_issue(
                    issues,
                    "ERROR",
                    "INJECT_COMPLETION_WITHOUT_START",
                    "KHS_ITEM",
                    row_number,
                    "KHS Inject Completion Date",
                    "KHS Inject completion requires an Inject start date.",
                )

            elif (
                inject_completion
                and inject_start
                and inject_completion < inject_start
                and inject_dates_changed
            ):
                _add_issue(
                    issues,
                    "ERROR",
                    "INJECT_COMPLETION_BEFORE_START",
                    "KHS_ITEM",
                    row_number,
                    "KHS Inject Completion Date",
                    "KHS Inject completion date cannot precede Inject start date.",
                )

            audit_date = dates["source_col_s_audit_date"]

            if audit_date and lp_start and audit_date != lp_start:
                _add_issue(
                    issues,
                    "WARNING",
                    "LP_AUDIT_DATE_MISMATCH",
                    "KHS_ITEM",
                    row_number,
                    "Original Source Column S (Audit Copy - LP Circulation Start Date)",
                    "Audit copy differs from LP Circulation Start Date.",
                )

            record = {
                "source_excel_row": row_number,
                "khs_id": khs_id,
                "request_id": request_id,
                "source_row_no": _source_row_number(
                    _value(cells, khs_map, "Source Row No."),
                    issues,
                    row_number,
                ),
                "executor_code": executor,
                "subtype": subtype,
                "vendor_name": vendor,
                "waiting_for": _text(
                    _value(cells, khs_map, "Waiting For")
                ),
                "waiting_reason": _text(
                    _value(cells, khs_map, "Waiting Reason")
                ),
                "remarks": _text(
                    _value(cells, khs_map, "Remarks")
                ),
                "legacy_overall_status": _text(
                    _value(cells, khs_map, "Legacy Overall Status")
                ),
                "legacy_detailed_status": _text(
                    _value(cells, khs_map, "Legacy Detailed Status")
                ),
                "migration_review": _text(
                    _value(cells, khs_map, "Migration Review")
                ),
                **dates,
            }

            items.append(record)

        if not requests and not items:
            _add_issue(
                issues,
                "ERROR",
                "NO_RECORDS",
                "WORKBOOK",
                None,
                None,
                "No Request or KHS records were found in the workbook.",
            )

        # -------------------------------------------------
        # SUMMARY
        # -------------------------------------------------

        error_count = sum(
            1 for issue in issues
            if issue["severity"] == "ERROR"
        )

        warning_count = sum(
            1 for issue in issues
            if issue["severity"] == "WARNING"
        )

        return {
            "template_version": (
                "2.4"
                if has_lp_milestones
                else "2.3"
                if has_inject_start or has_inject_completion
                else "2.2-compatible"
            ),
            "requests": requests,
            "items": items,
            "issues": issues,
            "summary": {
                "total_requests": len(requests),
                "total_khs_items": len(items),
                "error_count": error_count,
                "warning_count": warning_count,
                "can_import": error_count == 0,
            },
        }

    finally:
        workbook.close()
