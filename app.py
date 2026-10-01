from flask import (
    Flask,
    request,
    jsonify,
    render_template,
    session,
    redirect,
    url_for,
    send_file,
    send_from_directory,
)
from flask_cors import CORS
import pandas as pd
import sqlite3
import json
import os
import io
import uuid
import contextlib
from copy import copy
from datetime import datetime, date
from werkzeug.utils import secure_filename
from openpyxl import load_workbook


# ============================================================================
# APP CONFIGURATION
# ============================================================================
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.secret_key = "presourcing_secret_key_123"
CORS(app)

DB_NAME = "presourcing_db.sqlite"
COMPARISON_DIR = os.path.join(app.root_path, "secure_data", "comparisons")

BOQ_SHEET_NAME = "BoQ Request"
BOQ_TEMPLATE_FILENAME = "Template_BoQ_Presourcing_Final.xlsx"

BOQ_COLUMN_ITEM_NO = "Item No"
BOQ_COLUMN_DESCRIPTION = "Deskripsi Item"
BOQ_COLUMN_QTY = "Qty"
BOQ_COLUMN_UOM = "UoM"
BOQ_COLUMN_BRAND = "Preferred Brand"
BOQ_COLUMN_DELIVERY = "Delivery Time (RFS)"
BOQ_COLUMN_SOW = "Scope of Work (Opsional)"
BOQ_COLUMN_BOQ = "Bill of Quantity (Opsional)"
BOQ_COLUMN_VENDOR = "Vendor (Opsional)"
BOQ_COLUMN_AWAL_UNIT = "SPH Awal / Unit"
BOQ_COLUMN_AWAL_TOTAL = "Total SPH Awal"
BOQ_COLUMN_FINAL_UNIT = "SPH Final / Unit"
BOQ_COLUMN_FINAL_TOTAL = "Total SPH Final"
BOQ_COLUMN_SYSTEM_ID = "Item ID (System)"

BOQ_CORE_COLUMNS = [
    BOQ_COLUMN_ITEM_NO,
    BOQ_COLUMN_DESCRIPTION,
    BOQ_COLUMN_QTY,
    BOQ_COLUMN_UOM,
    BOQ_COLUMN_BRAND,
    BOQ_COLUMN_DELIVERY,
]

BOQ_OPTIONAL_COLUMNS = [
    BOQ_COLUMN_SOW,
    BOQ_COLUMN_BOQ,
    BOQ_COLUMN_VENDOR,
    BOQ_COLUMN_AWAL_UNIT,
    BOQ_COLUMN_AWAL_TOTAL,
    BOQ_COLUMN_FINAL_UNIT,
    BOQ_COLUMN_FINAL_TOTAL,
]

BOQ_ALL_COLUMNS = BOQ_CORE_COLUMNS + BOQ_OPTIONAL_COLUMNS + [
    BOQ_COLUMN_SYSTEM_ID
]

XLSX_MIMETYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ============================================================================
# GENERAL HELPERS
# ============================================================================
def db_connect():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def json_response_error(message, status=400, **extra):
    payload = {"success": False, "message": str(message)}
    payload.update(extra)
    return jsonify(payload), status


def current_username():
    return session.get("username")


def is_admin():
    return session.get("role") == "admin"


def is_logged_in():
    return "username" in session


def _excel_text(value):
    """Convert Excel values to stable string values without NaN."""
    if value is None:
        return ""

    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass

    if isinstance(value, (pd.Timestamp, datetime, date)):
        return value.strftime("%Y-%m-%d")

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    return str(value).strip()


def optional_number(value):
    """Return float for non-empty numeric input, otherwise None."""
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None
        value = text.replace(",", "")

    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Nilai harga harus berupa angka.")

    if number < 0:
        raise ValueError("Nilai harga tidak boleh negatif.")

    return number


def parse_qty(value, default=0):
    text = _excel_text(value)

    if text == "":
        return default

    try:
        number = float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError("Qty harus berupa angka.")

    if number < 0:
        raise ValueError("Qty tidak boleh negatif.")

    return int(number) if number.is_integer() else number


def calculate_sph_total(qty, unit_price):
    if qty is None or unit_price is None:
        return None

    try:
        return float(qty) * float(unit_price)
    except (TypeError, ValueError):
        return None


def derive_unit_price(qty, total):
    if qty is None or total is None:
        return None

    try:
        qty = float(qty)
        total = float(total)
    except (TypeError, ValueError):
        return None

    if qty <= 0:
        return None

    return total / qty


def resolve_sph_values(qty, unit_price, old_total=None, old_unit=None):
    """
    Unit price is the source of truth when supplied.
    When unit price is intentionally left blank during revision,
    legacy/current values are preserved.
    """
    if unit_price is not None:
        return unit_price, calculate_sph_total(qty, unit_price)

    return old_unit, old_total


def normalize_compare_value(value, kind="text"):
    if kind == "qty":
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return _excel_text(value).strip().lower()

    if kind == "number":
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return _excel_text(value).strip().lower()

    return _excel_text(value).strip().lower()


def generate_id(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _template_path():
    candidates = [
        os.path.join(app.static_folder or "", BOQ_TEMPLATE_FILENAME),
        os.path.join(app.root_path, BOQ_TEMPLATE_FILENAME),
        os.path.join(os.getcwd(), BOQ_TEMPLATE_FILENAME),
    ]

    for path in candidates:
        if path and os.path.isfile(path):
            return path

    return None


# ============================================================================
# BOQ EXCEL IMPORT / PARSING
# ============================================================================
def _read_boq_excel(file_storage, require_system_id=False):
    """Read the first worksheet and validate the finalized BoQ template."""
    if not file_storage:
        raise ValueError("File Excel tidak ditemukan.")

    file_storage.stream.seek(0)

    try:
        workbook = pd.ExcelFile(file_storage.stream)
    except Exception as exc:
        raise ValueError(f"File Excel tidak dapat dibaca: {exc}")

    if not workbook.sheet_names:
        raise ValueError("File Excel tidak memiliki sheet.")

    first_sheet = workbook.sheet_names[0]

    if first_sheet != BOQ_SHEET_NAME:
        raise ValueError(
            f'Sheet pertama harus bernama "{BOQ_SHEET_NAME}". '
            f'Sheet yang ditemukan: "{first_sheet}".'
        )

    try:
        df = pd.read_excel(
            workbook,
            sheet_name=BOQ_SHEET_NAME,
            dtype=object,
        )
    except Exception as exc:
        raise ValueError(
            f'Sheet "{BOQ_SHEET_NAME}" tidak dapat diproses: {exc}'
        )

    df.columns = [_excel_text(col) for col in df.columns]

    missing = [
        col
        for col in BOQ_CORE_COLUMNS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            "Format template tidak sesuai. Kolom wajib tidak ditemukan: "
            + ", ".join(missing)
        )

    if require_system_id and BOQ_COLUMN_SYSTEM_ID not in df.columns:
        raise ValueError(
            f'Kolom "{BOQ_COLUMN_SYSTEM_ID}" wajib ada untuk file revisi.'
        )

    if BOQ_COLUMN_SYSTEM_ID not in df.columns:
        df[BOQ_COLUMN_SYSTEM_ID] = ""

    for col in BOQ_OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    return df


def _parse_boq_rows(df):
    rows = []
    issues = []
    seen_ids = {}

    for excel_idx, row in df.iterrows():
        excel_row = excel_idx + 2

        description = _excel_text(
            row.get(BOQ_COLUMN_DESCRIPTION)
        )

        # Blank rows are ignored as template padding.
        if not description:
            continue

        item_id = _excel_text(
            row.get(BOQ_COLUMN_SYSTEM_ID)
        )

        if item_id:
            if item_id in seen_ids:
                issues.append(
                    {
                        "row": excel_row,
                        "severity": "error",
                        "message": (
                            f'Item ID duplikat dengan row '
                            f"{seen_ids[item_id]}."
                        ),
                    }
                )
            else:
                seen_ids[item_id] = excel_row

        qty_raw = row.get(BOQ_COLUMN_QTY, "")
        qty = 0

        if _excel_text(qty_raw):
            try:
                qty = parse_qty(qty_raw)
            except ValueError as exc:
                issues.append(
                    {
                        "row": excel_row,
                        "severity": "error",
                        "message": str(exc),
                    }
                )
        else:
            issues.append(
                {
                    "row": excel_row,
                    "severity": "warning",
                    "message": "Qty kosong; sistem menyimpan Qty = 0.",
                }
            )

        uom = _excel_text(row.get(BOQ_COLUMN_UOM))

        if not uom:
            issues.append(
                {
                    "row": excel_row,
                    "severity": "warning",
                    "message": "UoM kosong.",
                }
            )

        try:
            sph_awal_unit = optional_number(
                row.get(BOQ_COLUMN_AWAL_UNIT)
            )
        except ValueError as exc:
            issues.append(
                {
                    "row": excel_row,
                    "severity": "error",
                    "message": f"SPH Awal / Unit: {exc}",
                }
            )
            sph_awal_unit = None

        try:
            sph_final_unit = optional_number(
                row.get(BOQ_COLUMN_FINAL_UNIT)
            )
        except ValueError as exc:
            issues.append(
                {
                    "row": excel_row,
                    "severity": "error",
                    "message": f"SPH Final / Unit: {exc}",
                }
            )
            sph_final_unit = None

        rows.append(
            {
                "excelRow": excel_row,
                "id": item_id,
                "itemNo": _excel_text(
                    row.get(BOQ_COLUMN_ITEM_NO)
                ),
                "product": description,
                "qty": qty,
                "uom": uom,
                "preferredBrand": _excel_text(
                    row.get(BOQ_COLUMN_BRAND)
                ),
                "deliveryTime": _excel_text(
                    row.get(BOQ_COLUMN_DELIVERY)
                ),
                "sowName": (
                    _excel_text(
                        row.get(BOQ_COLUMN_SOW)
                    )
                    or "General Scope of Work"
                ),
                "boqName": (
                    _excel_text(
                        row.get(BOQ_COLUMN_BOQ)
                    )
                    or "General Items"
                ),
                "vendor": _excel_text(
                    row.get(BOQ_COLUMN_VENDOR)
                ),
                "sphAwalUnit": sph_awal_unit,
                "sphFinalUnit": sph_final_unit,
                "sphAwal": calculate_sph_total(
                    qty,
                    sph_awal_unit,
                ),
                "sphFinal": calculate_sph_total(
                    qty,
                    sph_final_unit,
                ),
            }
        )

    # Auto-number Item No only when blank.
    for idx, item in enumerate(rows, start=1):
        if not item["itemNo"]:
            item["itemNo"] = str(idx)

    return rows, issues


def read_boq_template(file_storage):
    """Backward-compatible parser used by the SA portal."""
    df = _read_boq_excel(
        file_storage,
        require_system_id=False,
    )
    rows, issues = _parse_boq_rows(df)

    errors = [
        issue for issue in issues
        if issue["severity"] == "error"
    ]

    if errors:
        raise ValueError(
            "Excel memiliki error: "
            + "; ".join(
                issue["message"] for issue in errors[:5]
            )
        )

    return [
        {
            "item_no": row["itemNo"],
            "description": row["product"],
            "qty": row["qty"],
            "uom": row["uom"],
            "preferred_brand": row["preferredBrand"],
            "delivery_time": row["deliveryTime"],
            "sow_name": row["sowName"],
            "boq_section": row["boqName"],
            "vendor": row["vendor"],
            "sph_awal_unit": row["sphAwalUnit"],
            "sph_final_unit": row["sphFinalUnit"],
            "item_id": row["id"],
        }
        for row in rows
    ]


# ============================================================================
# PAGE ROUTES
# ============================================================================
@app.route("/")
def index():
    if not is_logged_in() or not is_admin():
        return redirect(url_for("login_page"))

    return render_template("presourcing-dashboard.html")


@app.route("/login")
def login_page():
    if is_logged_in():
        if is_admin():
            return redirect(url_for("index"))
        return redirect(url_for("sa_portal"))

    return render_template("login.html")


@app.route("/portal")
def sa_portal():
    if not is_logged_in():
        return redirect(url_for("login_page"))

    return render_template("sa-portal.html")


# ============================================================================
# DATABASE INITIALIZATION & MIGRATION
# ============================================================================
def table_columns(cursor, table_name):
    rows = cursor.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()
    return {row[1] for row in rows}


def ensure_columns(cursor, table_name, columns):
    existing = table_columns(cursor, table_name)

    for column, dtype in columns.items():
        if column in existing:
            continue

        cursor.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column} {dtype}"
        )


def init_db():
    with db_connect() as conn:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS dashboard_state (
                id INTEGER PRIMARY KEY,
                data_type TEXT UNIQUE,
                json_data TEXT
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                department TEXT,
                role TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                client_name TEXT,
                competitor_info TEXT,
                sla_date TEXT NOT NULL,
                notes TEXT,
                status TEXT DEFAULT 'unassigned',
                requester_username TEXT NOT NULL,
                pic_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS request_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                sow_name TEXT DEFAULT 'General Scope of Work',
                boq_section TEXT DEFAULT 'General Items',
                item_no TEXT,
                description TEXT NOT NULL,
                preferred_brand TEXT,
                quantity REAL,
                uom TEXT,
                delivery_time TEXT,
                vendor TEXT,
                sph_awal_unit REAL,
                sph_final_unit REAL,
                FOREIGN KEY(ticket_id)
                    REFERENCES requests(ticket_id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_user TEXT NOT NULL,
                message TEXT NOT NULL,
                is_read INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id TEXT PRIMARY KEY,
                name TEXT,
                requestor_name TEXT,
                requestor_dept TEXT,
                priority TEXT,
                status TEXT,
                lead_id TEXT,
                sph_mode TEXT,
                project_sph_awal REAL,
                project_sph_final REAL,
                created_at TEXT,
                closed_at TEXT,
                target_rfs TEXT,
                pipeline_stage TEXT,
                progress_pct INTEGER
            )
            """
        )

        ensure_columns(
            cursor,
            "projects",
            {
                "target_rfs": "TEXT",
                "pipeline_stage": "TEXT",
                "progress_pct": "INTEGER",
            },
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sows (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                name TEXT,
                FOREIGN KEY(project_id)
                    REFERENCES projects(id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS boqs (
                id TEXT PRIMARY KEY,
                sow_id TEXT,
                name TEXT,
                FOREIGN KEY(sow_id)
                    REFERENCES sows(id)
                    ON DELETE CASCADE
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                boq_id TEXT,
                product TEXT,
                qty REAL,
                uom TEXT,
                vendor TEXT,
                sph_awal REAL,
                sph_final REAL,
                notes TEXT,
                pic_ids TEXT,
                item_no TEXT,
                preferred_brand TEXT,
                delivery_time TEXT,
                sph_awal_unit REAL,
                sph_final_unit REAL,
                FOREIGN KEY(boq_id)
                    REFERENCES boqs(id)
                    ON DELETE CASCADE
            )
            """
        )

        ensure_columns(
            cursor,
            "items",
            {
                "item_no": "TEXT",
                "preferred_brand": "TEXT",
                "delivery_time": "TEXT",
                "sph_awal_unit": "REAL",
                "sph_final_unit": "REAL",
            },
        )

        ensure_columns(
            cursor,
            "request_items",
            {
                "sph_awal_unit": "REAL",
                "sph_final_unit": "REAL",
            },
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS comparison_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                vendor_name TEXT,
                offered_price REAL,
                file_path TEXT,
                FOREIGN KEY(project_id)
                    REFERENCES projects(id)
                    ON DELETE CASCADE
            )
            """
        )

        seed_users = [
            (
                "admin",
                "admin123",
                "Admin Presourcing",
                "Presourcing Control",
                "admin",
            ),
            (
                "master",
                "master123",
                "Master Admin",
                "System Control",
                "admin",
            ),
            (
                "tester",
                "tester123",
                "QA Tester",
                "Testing Team",
                "sa",
            ),
        ]

        for user_data in seed_users:
            cursor.execute(
                "SELECT 1 FROM users WHERE username = ?",
                (user_data[0],),
            )

            if cursor.fetchone() is None:
                cursor.execute(
                    """
                    INSERT INTO users (
                        username,
                        password,
                        full_name,
                        department,
                        role
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    user_data,
                )

        conn.commit()


init_db()


# ============================================================================
# RELATIONAL DATA -> FRONTEND SHAPE
# ============================================================================
def get_projects_relational(cursor):
    cursor.execute(
        "SELECT * FROM projects ORDER BY created_at DESC, id DESC"
    )

    projects_data = []

    for p_row in cursor.fetchall():
        p = dict(p_row)

        cursor.execute(
            """
            SELECT
                vendor_name,
                offered_price,
                file_path
            FROM comparison_docs
            WHERE project_id = ?
            ORDER BY id DESC
            """,
            (p["id"],),
        )

        p["comparison_docs"] = [
            dict(row) for row in cursor.fetchall()
        ]

        cursor.execute(
            """
            SELECT id, name
            FROM sows
            WHERE project_id = ?
            ORDER BY rowid
            """,
            (p["id"],),
        )

        sows = []

        for s_row in cursor.fetchall():
            s = dict(s_row)

            cursor.execute(
                """
                SELECT id, name
                FROM boqs
                WHERE sow_id = ?
                ORDER BY rowid
                """,
                (s["id"],),
            )

            boqs = []

            for b_row in cursor.fetchall():
                b = dict(b_row)

                cursor.execute(
                    """
                    SELECT *
                    FROM items
                    WHERE boq_id = ?
                    ORDER BY rowid
                    """,
                    (b["id"],),
                )

                items = []

                for i_row in cursor.fetchall():
                    i = dict(i_row)

                    try:
                        pic_ids = (
                            json.loads(i["pic_ids"])
                            if i.get("pic_ids")
                            else []
                        )
                    except (TypeError, json.JSONDecodeError):
                        pic_ids = []

                    sph_awal = i.pop("sph_awal", None)
                    sph_final = i.pop("sph_final", None)
                    sph_awal_unit = i.pop("sph_awal_unit", None)
                    sph_final_unit = i.pop("sph_final_unit", None)

                    # Backward compatibility for legacy rows.
                    if sph_awal_unit is None:
                        sph_awal_unit = derive_unit_price(
                            i.get("qty"),
                            sph_awal,
                        )

                    if sph_final_unit is None:
                        sph_final_unit = derive_unit_price(
                            i.get("qty"),
                            sph_final,
                        )

                    i["picIds"] = pic_ids
                    i["sphAwal"] = sph_awal
                    i["sphFinal"] = sph_final
                    i["sphAwalUnit"] = sph_awal_unit
                    i["sphFinalUnit"] = sph_final_unit
                    i["itemNo"] = i.pop("item_no", "") or ""
                    i["preferredBrand"] = i.pop("preferred_brand", "") or ""
                    i["deliveryTime"] = i.pop("delivery_time", "") or ""

                    # Do not expose DB internal field name.
                    i.pop("pic_ids", None)

                    items.append(i)

                b["items"] = items
                boqs.append(b)

            s["boqs"] = boqs
            sows.append(s)

        p["sows"] = sows

        p["requestorName"] = p.pop("requestor_name", "") or ""
        p["requestorDept"] = p.pop("requestor_dept", "") or ""
        p["leadId"] = p.pop("lead_id", "") or ""
        p["sphMode"] = p.pop("sph_mode", "item") or "item"
        p["projectSphAwal"] = p.pop("project_sph_awal", None)
        p["projectSphFinal"] = p.pop("project_sph_final", None)
        p["createdAt"] = p.pop("created_at", "") or ""
        p["closedAt"] = p.pop("closed_at", None)
        p["targetRfs"] = p.pop("target_rfs", None)
        p["pipelineStage"] = p.pop("pipeline_stage", None)
        p["progressPct"] = p.pop("progress_pct", 0)

        projects_data.append(p)

    return projects_data


# ============================================================================
# AUTHENTICATION & USERS
# ============================================================================
@app.route("/api/register", methods=["POST"])
def register():
    payload = request.get_json(silent=True) or {}

    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    full_name = str(payload.get("full_name") or "").strip()
    department = str(payload.get("department") or "").strip()
    role = str(payload.get("role") or "sa").strip().lower()

    if not username or not password or not full_name:
        return json_response_error(
            "Username, password, dan nama lengkap wajib diisi."
        )

    if role not in {"sa", "admin"}:
        role = "sa"

    try:
        with db_connect() as conn:
            conn.execute(
                """
                INSERT INTO users (
                    username,
                    password,
                    full_name,
                    department,
                    role
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    username,
                    password,
                    full_name,
                    department,
                    role,
                ),
            )
            conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Registrasi berhasil!",
            }
        ), 201

    except sqlite3.IntegrityError:
        return json_response_error(
            "Username sudah terdaftar.",
            400,
        )


def _login_user(payload):
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")

    if not username or not password:
        return json_response_error(
            "Username dan password wajib diisi."
        )

    with db_connect() as conn:
        user = conn.execute(
            """
            SELECT
                username,
                full_name,
                department,
                role
            FROM users
            WHERE username = ?
              AND password = ?
            """,
            (username, password),
        ).fetchone()

    if user is None:
        return json_response_error(
            "Username atau Password salah!",
            401,
        )

    session.update(
        {
            "username": user["username"],
            "full_name": user["full_name"],
            "department": user["department"] or "",
            "role": user["role"],
        }
    )

    return jsonify(
        {
            "success": True,
            "user": {
                "username": user["username"],
                "full_name": user["full_name"],
                "department": user["department"] or "",
                "role": user["role"],
            },
        }
    ), 200


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    return _login_user(payload)


@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify(
        {
            "success": True,
            "message": "Berhasil logout",
        }
    )


# ============================================================================
# NOTIFICATIONS
# ============================================================================
@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    target = str(
        request.args.get("username")
        or current_username()
        or ""
    ).strip()

    if not target:
        return json_response_error(
            "Target user diperlukan."
        )

    try:
        with db_connect() as conn:
            cursor = conn.cursor()

            if target == "admin":
                ongoing_projects = cursor.execute(
                    """
                    SELECT id, name, target_rfs
                    FROM projects
                    WHERE status = 'ongoing'
                      AND target_rfs IS NOT NULL
                      AND target_rfs != ''
                    """
                ).fetchall()

                today = datetime.now().date()

                for project in ongoing_projects:
                    try:
                        rfs_date = datetime.strptime(
                            project["target_rfs"],
                            "%Y-%m-%d",
                        ).date()
                    except (TypeError, ValueError):
                        continue

                    days_left = (rfs_date - today).days

                    message = ""

                    if days_left < 0:
                        message = (
                            f"🚨 OVERDUE: Project "
                            f"'{project['name']}' telah melewati "
                            f"batas Target RFS."
                        )
                    elif days_left <= 14:
                        message = (
                            f"⚠️ AT RISK: Project "
                            f"'{project['name']}' tersisa "
                            f"{days_left} hari menuju RFS."
                        )

                    if message:
                        existing = cursor.execute(
                            """
                            SELECT 1
                            FROM notifications
                            WHERE target_user = 'admin'
                              AND message = ?
                              AND date(created_at) = date('now', 'localtime')
                            LIMIT 1
                            """,
                            (message,),
                        ).fetchone()

                        if existing is None:
                            cursor.execute(
                                """
                                INSERT INTO notifications (
                                    target_user,
                                    message
                                ) VALUES ('admin', ?)
                                """,
                                (message,),
                            )

            conn.commit()

            rows = cursor.execute(
                """
                SELECT *
                FROM notifications
                WHERE target_user = ?
                   OR target_user = 'broadcast'
                ORDER BY created_at DESC, id DESC
                LIMIT 20
                """,
                (target,),
            ).fetchall()

            return jsonify(
                {
                    "success": True,
                    "data": [dict(row) for row in rows],
                }
            )

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def mark_notification_read(notif_id):
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    with db_connect() as conn:
        cursor = conn.execute(
            """
            UPDATE notifications
            SET is_read = 1
            WHERE id = ?
            """,
            (notif_id,),
        )
        conn.commit()

        if cursor.rowcount == 0:
            return json_response_error(
                "Notifikasi tidak ditemukan.",
                404,
            )

    return jsonify({"success": True}), 200


# ============================================================================
# SA REQUEST FLOW
# ============================================================================
@app.route("/api/requests", methods=["POST"])
def create_request():
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    payload = request.get_json(silent=True) or {}

    title = str(payload.get("title") or "").strip()
    client_name = str(payload.get("client_name") or "").strip()
    competitor_info = str(payload.get("competitor_info") or "").strip()
    sla_date = str(payload.get("sla_date") or "").strip()
    notes = str(payload.get("notes") or "").strip()

    requester_username = current_username()

    if not title or not client_name or not sla_date:
        return json_response_error(
            "Nama project, pelanggan/end-user, dan Target Selesai wajib diisi."
        )

    try:
        datetime.strptime(sla_date, "%Y-%m-%d")
    except ValueError:
        return json_response_error(
            "Format Target Selesai harus YYYY-MM-DD."
        )

    ticket_id = (
        f"REQ-{datetime.now().strftime('%y%m')}"
        f"-{uuid.uuid4().hex[:4].upper()}"
    )

    try:
        with db_connect() as conn:
            conn.execute(
                """
                INSERT INTO requests (
                    ticket_id,
                    title,
                    client_name,
                    competitor_info,
                    sla_date,
                    notes,
                    requester_username,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unassigned')
                """,
                (
                    ticket_id,
                    title,
                    client_name,
                    competitor_info,
                    sla_date,
                    notes,
                    requester_username,
                ),
            )

            conn.execute(
                """
                INSERT INTO notifications (
                    target_user,
                    message
                ) VALUES ('admin', ?)
                """,
                (
                    f"Request Baru: {ticket_id} "
                    f"dari @{requester_username}",
                ),
            )

            conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Request berhasil dibuat",
                "ticket_id": ticket_id,
            }
        ), 201

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


@app.route("/api/requests", methods=["GET"])
def get_requests():
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    requested_username = str(
        request.args.get("username")
        or current_username()
        or ""
    ).strip()

    admin = is_admin()

    try:
        with db_connect() as conn:
            if admin:
                rows = conn.execute(
                    """
                    SELECT
                        r.*,
                        u.full_name,
                        u.department,
                        p.pipeline_stage,
                        p.progress_pct,
                        p.target_rfs
                    FROM requests r
                    LEFT JOIN users u
                        ON r.requester_username = u.username
                    LEFT JOIN projects p
                        ON r.ticket_id = p.id
                    ORDER BY r.created_at DESC, r.id DESC
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT
                        r.*,
                        u.full_name,
                        u.department,
                        p.pipeline_stage,
                        p.progress_pct,
                        p.target_rfs
                    FROM requests r
                    LEFT JOIN users u
                        ON r.requester_username = u.username
                    LEFT JOIN projects p
                        ON r.ticket_id = p.id
                    WHERE r.requester_username = ?
                    ORDER BY r.created_at DESC, r.id DESC
                    """,
                    (current_username(),),
                ).fetchall()

            return jsonify(
                {
                    "success": True,
                    "data": [dict(row) for row in rows],
                }
            ), 200

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


@app.route("/api/upload_boq", methods=["POST"])
def upload_boq():
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    ticket_id = str(
        request.form.get("ticket_id") or ""
    ).strip()

    if not ticket_id or "file" not in request.files:
        return json_response_error(
            "Ticket ID dan file Excel wajib diisi."
        )

    file = request.files["file"]

    if not file.filename:
        return json_response_error(
            "Nama file tidak valid."
        )

    try:
        df = _read_boq_excel(
            file,
            require_system_id=False,
        )
        rows, issues = _parse_boq_rows(df)

        if not rows:
            return json_response_error(
                "Tidak ada item yang terisi di Sheet BoQ Request."
            )

        for item in rows:
            if item["id"]:
                issues.append(
                    {
                        "row": item["excelRow"],
                        "severity": "error",
                        "message": (
                            f'"{BOQ_COLUMN_SYSTEM_ID}" harus kosong '
                            "untuk Initial Request."
                        ),
                    }
                )

        errors = [
            issue for issue in issues
            if issue["severity"] == "error"
        ]

        warnings = [
            issue for issue in issues
            if issue["severity"] == "warning"
        ]

        if errors:
            return json_response_error(
                "Excel memiliki error. Perbaiki file terlebih dahulu.",
                400,
                issues=issues[:50],
            )

        with db_connect() as conn:
            ticket = conn.execute(
                """
                SELECT ticket_id, requester_username
                FROM requests
                WHERE ticket_id = ?
                """,
                (ticket_id,),
            ).fetchone()

            if ticket is None:
                return json_response_error(
                    "Request tidak ditemukan.",
                    404,
                )

            if (
                not is_admin()
                and ticket["requester_username"] != current_username()
            ):
                return json_response_error(
                    "Anda tidak berhak mengubah request ini.",
                    403,
                )

            conn.execute(
                "DELETE FROM request_items WHERE ticket_id = ?",
                (ticket_id,),
            )

            for item in rows:
                conn.execute(
                    """
                    INSERT INTO request_items (
                        ticket_id,
                        sow_name,
                        boq_section,
                        item_no,
                        description,
                        preferred_brand,
                        quantity,
                        uom,
                        delivery_time,
                        vendor,
                        sph_awal_unit,
                        sph_final_unit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket_id,
                        item["sowName"],
                        item["boqName"],
                        item["itemNo"],
                        item["product"],
                        item["preferredBrand"],
                        item["qty"],
                        item["uom"],
                        item["deliveryTime"],
                        item["vendor"] or None,
                        item["sphAwalUnit"],
                        item["sphFinalUnit"],
                    ),
                )

            conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "File BoQ berhasil diunggah.",
                "summary": {
                    "items": len(rows),
                    "warnings": len(warnings),
                },
                "issues": issues[:50],
            }
        ), 200

    except ValueError as exc:
        return json_response_error(str(exc), 400)
    except Exception as exc:
        return json_response_error(str(exc), 500)


@app.route("/api/parse_boq_template", methods=["POST"])
def parse_boq_template():
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    if "file" not in request.files:
        return json_response_error(
            "File Excel belum diunggah."
        )

    try:
        rows = read_boq_template(
            request.files["file"]
        )

        return jsonify(
            {
                "success": True,
                "data": rows,
                "count": len(rows),
            }
        ), 200

    except ValueError as exc:
        return json_response_error(
            str(exc),
            400,
        )
    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


@app.route("/api/request_items/<ticket_id>", methods=["GET"])
def get_request_items(ticket_id):
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    try:
        with db_connect() as conn:
            ticket = conn.execute(
                """
                SELECT ticket_id, requester_username
                FROM requests
                WHERE ticket_id = ?
                """,
                (ticket_id,),
            ).fetchone()

            if ticket is None:
                return json_response_error(
                    "Request tidak ditemukan.",
                    404,
                )

            if (
                not is_admin()
                and ticket["requester_username"] != current_username()
            ):
                return json_response_error(
                    "Anda tidak berhak melihat request ini.",
                    403,
                )

            rows = conn.execute(
                """
                SELECT *
                FROM request_items
                WHERE ticket_id = ?
                ORDER BY id
                """,
                (ticket_id,),
            ).fetchall()

            return jsonify(
                {
                    "success": True,
                    "data": [dict(row) for row in rows],
                }
            ), 200

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# REQUEST ASSIGNMENT -> PROJECT CREATION
# ============================================================================
@app.route("/api/requests/assign", methods=["POST"])
def assign_ticket():
    if not is_admin():
        return json_response_error(
            "Akses ditolak. Admin Presourcing diperlukan.",
            403,
        )

    payload = request.get_json(silent=True) or {}
    ticket_id = str(payload.get("ticket_id") or "").strip()
    pic_username = str(payload.get("pic_username") or "").strip()

    if not ticket_id or not pic_username:
        return json_response_error(
            "Ticket ID dan PIC wajib diisi."
        )

    try:
        with db_connect() as conn:
            cursor = conn.cursor()

            req = cursor.execute(
                """
                SELECT
                    r.*,
                    u.full_name,
                    u.department
                FROM requests r
                LEFT JOIN users u
                    ON r.requester_username = u.username
                WHERE r.ticket_id = ?
                """,
                (ticket_id,),
            ).fetchone()

            if req is None:
                return json_response_error(
                    "Request tidak ditemukan.",
                    404,
                )

            pic_user = cursor.execute(
                """
                SELECT username
                FROM users
                WHERE username = ?
                """,
                (pic_username,),
            ).fetchone()

            if pic_user is None:
                return json_response_error(
                    "PIC tidak ditemukan di user master.",
                    400,
                )

            cursor.execute(
                """
                UPDATE requests
                SET pic_username = ?,
                    status = 'ongoing'
                WHERE ticket_id = ?
                """,
                (pic_username, ticket_id),
            )

            project_exists = cursor.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (ticket_id,),
            ).fetchone()

            if project_exists is None:
                req_name = (
                    req["full_name"]
                    or req["requester_username"]
                )
                req_dept = (
                    req["department"]
                    or "Presales Team"
                )

                title = (
                    f"{req['title']} "
                    f"({req['client_name'] or 'Klien Umum'})"
                )

                created_at = (
                    str(req["created_at"])[:10]
                    if req["created_at"]
                    else datetime.now().strftime("%Y-%m-%d")
                )

                target_rfs = req["sla_date"] or ""

                cursor.execute(
                    """
                    INSERT INTO projects (
                        id,
                        name,
                        requestor_name,
                        requestor_dept,
                        priority,
                        status,
                        lead_id,
                        sph_mode,
                        project_sph_awal,
                        project_sph_final,
                        created_at,
                        closed_at,
                        target_rfs,
                        pipeline_stage,
                        progress_pct
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticket_id,
                        title,
                        req_name,
                        req_dept,
                        "High",
                        "ongoing",
                        pic_username,
                        "item",
                        None,
                        None,
                        created_at,
                        None,
                        target_rfs,
                        "1 - Project Identification",
                        0,
                    ),
                )

                req_items = cursor.execute(
                    """
                    SELECT *
                    FROM request_items
                    WHERE ticket_id = ?
                    ORDER BY id
                    """,
                    (ticket_id,),
                ).fetchall()

                if not req_items:
                    raise ValueError(
                        "Request belum memiliki item BoQ. "
                        "Upload BoQ terlebih dahulu."
                    )

                sow_map = {}
                boq_map = {}

                for item in req_items:
                    sow_name = (
                        item["sow_name"]
                        or "General Scope of Work"
                    )
                    boq_name = (
                        item["boq_section"]
                        or "General Items"
                    )

                    if sow_name not in sow_map:
                        sow_id = generate_id("sow")
                        cursor.execute(
                            """
                            INSERT INTO sows (
                                id,
                                project_id,
                                name
                            ) VALUES (?, ?, ?)
                            """,
                            (
                                sow_id,
                                ticket_id,
                                sow_name,
                            ),
                        )
                        sow_map[sow_name] = sow_id

                    sow_id = sow_map[sow_name]
                    boq_key = (sow_name, boq_name)

                    if boq_key not in boq_map:
                        boq_id = generate_id("boq")
                        cursor.execute(
                            """
                            INSERT INTO boqs (
                                id,
                                sow_id,
                                name
                            ) VALUES (?, ?, ?)
                            """,
                            (
                                boq_id,
                                sow_id,
                                boq_name,
                            ),
                        )
                        boq_map[boq_key] = boq_id

                    boq_id = boq_map[boq_key]
                    item_id = generate_id("item")

                    sph_awal_unit = item["sph_awal_unit"]
                    sph_final_unit = item["sph_final_unit"]

                    sph_awal = calculate_sph_total(
                        item["quantity"],
                        sph_awal_unit,
                    )
                    sph_final = calculate_sph_total(
                        item["quantity"],
                        sph_final_unit,
                    )

                    cursor.execute(
                        """
                        INSERT INTO items (
                            id,
                            boq_id,
                            product,
                            qty,
                            uom,
                            vendor,
                            sph_awal,
                            sph_final,
                            notes,
                            pic_ids,
                            item_no,
                            preferred_brand,
                            delivery_time,
                            sph_awal_unit,
                            sph_final_unit
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            item_id,
                            boq_id,
                            item["description"],
                            item["quantity"],
                            item["uom"] or "",
                            item["vendor"] or "",
                            sph_awal,
                            sph_final,
                            "",
                            json.dumps([pic_username]),
                            item["item_no"] or "",
                            item["preferred_brand"] or "",
                            item["delivery_time"] or "",
                            sph_awal_unit,
                            sph_final_unit,
                        ),
                    )

            cursor.execute(
                """
                INSERT INTO notifications (
                    target_user,
                    message
                ) VALUES (?, ?)
                """,
                (
                    req["requester_username"],
                    f"Tiket {ticket_id} sudah di-assign "
                    f"ke PIC: {pic_username}",
                ),
            )

            conn.commit()

            return jsonify(
                {
                    "success": True,
                    "message": "Tiket berhasil di-assign!",
                }
            ), 200

    except ValueError as exc:
        return json_response_error(
            str(exc),
            400,
        )
    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# PRESOURCING DASHBOARD API
# ============================================================================
def _delete_project_tree(cursor, project_id, delete_request=False):
    """Delete a project tree. Request data is preserved unless explicitly requested."""
    cursor.execute(
        "DELETE FROM projects WHERE id = ?",
        (project_id,),
    )

    # Explicit cleanup also protects legacy DBs where FK cascades may not
    # have been enabled historically.
    cursor.execute(
        "DELETE FROM comparison_docs WHERE project_id = ?",
        (project_id,),
    )

    # request_items belong to the original SA request and should survive
    # dashboard/project rewrites so the SA portal can continue to inspect it.
    if delete_request:
        cursor.execute(
            "DELETE FROM request_items WHERE ticket_id = ?",
            (project_id,),
        )
        cursor.execute(
            "DELETE FROM requests WHERE ticket_id = ?",
            (project_id,),
        )


def _insert_project_tree(cursor, project):
    project_id = str(
        project.get("id") or generate_id("proj")
    )

    sph_mode = (
        "project"
        if project.get("sphMode") == "project"
        else "item"
    )

    cursor.execute(
        """
        INSERT INTO projects (
            id,
            name,
            requestor_name,
            requestor_dept,
            priority,
            status,
            lead_id,
            sph_mode,
            project_sph_awal,
            project_sph_final,
            created_at,
            closed_at,
            target_rfs,
            pipeline_stage,
            progress_pct
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            project.get("name") or "",
            project.get("requestorName") or "",
            project.get("requestorDept") or "",
            project.get("priority") or "Medium",
            project.get("status") or "ongoing",
            project.get("leadId") or "",
            sph_mode,
            project.get("projectSphAwal"),
            project.get("projectSphFinal"),
            project.get("createdAt") or datetime.now().strftime("%Y-%m-%d"),
            project.get("closedAt"),
            project.get("targetRfs") or "",
            project.get("pipelineStage") or "1 - Project Identification",
            project.get("progressPct") if project.get("progressPct") is not None else 0,
        ),
    )

    for sow in project.get("sows") or []:
        sow_id = str(
            sow.get("id") or generate_id("sow")
        )

        cursor.execute(
            """
            INSERT INTO sows (
                id,
                project_id,
                name
            ) VALUES (?, ?, ?)
            """,
            (
                sow_id,
                project_id,
                sow.get("name") or "",
            ),
        )

        for boq in sow.get("boqs") or []:
            boq_id = str(
                boq.get("id") or generate_id("boq")
            )

            cursor.execute(
                """
                INSERT INTO boqs (
                    id,
                    sow_id,
                    name
                ) VALUES (?, ?, ?)
                """,
                (
                    boq_id,
                    sow_id,
                    boq.get("name") or "",
                ),
            )

            for item in boq.get("items") or []:
                item_id = str(
                    item.get("id") or generate_id("item")
                )

                qty = item.get("qty")
                sph_awal_unit = optional_number(
                    item.get("sphAwalUnit")
                )
                sph_final_unit = optional_number(
                    item.get("sphFinalUnit")
                )

                # Unit price is the canonical input. Legacy total values are
                # fallback only when unit is absent.
                legacy_awal = optional_number(
                    item.get("sphAwal")
                )
                legacy_final = optional_number(
                    item.get("sphFinal")
                )

                if sph_awal_unit is not None:
                    sph_awal = calculate_sph_total(
                        qty,
                        sph_awal_unit,
                    )
                else:
                    sph_awal = legacy_awal

                if sph_final_unit is not None:
                    sph_final = calculate_sph_total(
                        qty,
                        sph_final_unit,
                    )
                else:
                    sph_final = legacy_final

                cursor.execute(
                    """
                    INSERT INTO items (
                        id,
                        boq_id,
                        product,
                        qty,
                        uom,
                        vendor,
                        sph_awal,
                        sph_final,
                        notes,
                        pic_ids,
                        item_no,
                        preferred_brand,
                        delivery_time,
                        sph_awal_unit,
                        sph_final_unit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item_id,
                        boq_id,
                        item.get("product") or "",
                        qty,
                        item.get("uom") or "",
                        item.get("vendor") or "",
                        sph_awal,
                        sph_final,
                        item.get("notes") or "",
                        json.dumps(
                            item.get("picIds") or [],
                            ensure_ascii=False,
                        ),
                        item.get("itemNo") or "",
                        item.get("preferredBrand") or "",
                        item.get("deliveryTime") or "",
                        sph_awal_unit,
                        sph_final_unit,
                    ),
                )

    for doc in project.get("comparison_docs") or []:
        cursor.execute(
            """
            INSERT INTO comparison_docs (
                project_id,
                vendor_name,
                offered_price,
                file_path
            ) VALUES (?, ?, ?, ?)
            """,
            (
                project_id,
                doc.get("vendor_name") or "",
                doc.get("offered_price"),
                doc.get("file_path") or "",
            ),
        )


@app.route("/api/presourcing", methods=["GET", "POST"])
def api_presourcing():
    if not is_admin():
        return json_response_error(
            "Akses ditolak. Admin Presourcing diperlukan.",
            403,
        )

    if request.method == "GET":
        try:
            with db_connect() as conn:
                team_row = conn.execute(
                    """
                    SELECT json_data
                    FROM dashboard_state
                    WHERE data_type = 'team'
                    """
                ).fetchone()

                if team_row and team_row["json_data"]:
                    try:
                        team = json.loads(
                            team_row["json_data"]
                        )
                    except json.JSONDecodeError:
                        team = []
                else:
                    team_rows = conn.execute(
                        """
                        SELECT full_name
                        FROM users
                        WHERE role IN ('sa', 'admin')
                        ORDER BY full_name
                        """
                    ).fetchall()

                    team = [
                        row["full_name"]
                        for row in team_rows
                        if row["full_name"]
                    ]

                projects_data = get_projects_relational(
                    conn.cursor()
                )

                return jsonify(
                    {
                        "projects": projects_data,
                        "team": team,
                    }
                ), 200

        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    data = request.get_json(silent=True) or {}
    incoming_projects = data.get("projects")
    incoming_team = data.get("team")

    if not isinstance(incoming_projects, list):
        return json_response_error(
            "Payload projects harus berupa array.",
            400,
        )

    if not isinstance(incoming_team, list):
        incoming_team = []

    normalized_team = [
        str(member).strip()
        for member in incoming_team
        if str(member).strip()
    ]

    try:
        with db_connect() as conn:
            cursor = conn.cursor()

            cursor.execute(
                """
                REPLACE INTO dashboard_state (
                    data_type,
                    json_data
                ) VALUES ('team', ?)
                """,
                (
                    json.dumps(
                        normalized_team,
                        ensure_ascii=False,
                    ),
                ),
            )

            existing_ids = {
                row["id"]
                for row in cursor.execute(
                    "SELECT id FROM projects"
                ).fetchall()
            }

            incoming_ids = {
                str(project.get("id"))
                for project in incoming_projects
                if project.get("id")
            }

            # Preserve the project's existing DB identity. Any project removed
            # from the dashboard payload is removed from the relational tree.
            for project_id in existing_ids - incoming_ids:
                _delete_project_tree(
                    cursor,
                    project_id,
                    delete_request=False,
                )

            for project in incoming_projects:
                if not project.get("id"):
                    project["id"] = generate_id("proj")

                # Full rewrite is intentional: Dashboard is the operational
                # control center, and its relational state remains the source
                # represented by this endpoint.
                _delete_project_tree(
                    cursor,
                    str(project["id"]),
                    delete_request=False,
                )

                _insert_project_tree(
                    cursor,
                    project,
                )

            conn.commit()

        return jsonify({"success": True}), 200

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# PROJECT DELETE
# ============================================================================
@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    if not is_admin():
        return json_response_error(
            "Akses ditolak.",
            403,
        )

    try:
        with db_connect() as conn:
            cursor = conn.cursor()

            exists = cursor.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()

            if exists is None:
                return json_response_error(
                    "Project tidak ditemukan atau sudah terhapus.",
                    404,
                )

            _delete_project_tree(
                cursor,
                project_id,
                delete_request=True,
            )

            conn.commit()

        return jsonify(
            {
                "success": True,
                "message": "Project berhasil dihapus dari database!",
            }
        ), 200

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# TEMPLATE DOWNLOADS
# ============================================================================
def _send_master_template():
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    path = _template_path()

    if not path:
        return json_response_error(
            f"Template '{BOQ_TEMPLATE_FILENAME}' belum tersedia di server.",
            404,
        )

    return send_file(
        path,
        mimetype=XLSX_MIMETYPE,
        as_attachment=True,
        download_name=BOQ_TEMPLATE_FILENAME,
    )


@app.route("/api/download_template_boq", methods=["GET"])
def download_template_boq():
    return _send_master_template()


# Legacy alias used by older SA portal code.
@app.route("/api/boq_template", methods=["GET"])
def boq_template_legacy():
    return _send_master_template()


@app.route("/api/projects/<project_id>/download_boq_template", methods=["GET"])
def download_project_boq_template(project_id):
    if not is_admin():
        return json_response_error(
            "Akses ditolak. Admin Presourcing diperlukan.",
            403,
        )

    template_path = _template_path()

    if not template_path:
        return json_response_error(
            f"Template '{BOQ_TEMPLATE_FILENAME}' tidak ditemukan.",
            404,
        )

    try:
        with db_connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()

            if exists is None:
                return json_response_error(
                    "Project tidak ditemukan.",
                    404,
                )

            items = conn.execute(
                """
                SELECT
                    i.*,
                    s.name AS sow_name,
                    b.name AS boq_name
                FROM items i
                JOIN boqs b
                    ON i.boq_id = b.id
                JOIN sows s
                    ON b.sow_id = s.id
                WHERE s.project_id = ?
                ORDER BY
                    s.rowid,
                    b.rowid,
                    i.rowid
                """,
                (project_id,),
            ).fetchall()

        wb = load_workbook(template_path)
        ws = wb[BOQ_SHEET_NAME]

        # Keep the instructions worksheet untouched.
        data_start = 2
        old_last_row = max(ws.max_row, 2)

        style_source_row = 2

        # Clear current BoQ data rows only.
        for row_idx in range(data_start, old_last_row + 1):
            for col_idx in range(1, 15):
                ws.cell(row_idx, col_idx).value = None

        # Guarantee enough data rows for larger projects.
        needed_last_row = max(
            2,
            len(items) + 1,
        )

        if needed_last_row > ws.max_row:
            ws.insert_rows(
                ws.max_row + 1,
                amount=needed_last_row - ws.max_row,
            )

        # Copy style + number format for newly inserted rows.
        for row_idx in range(2, needed_last_row + 1):
            if row_idx == style_source_row:
                continue

            for col_idx in range(1, 15):
                source = ws.cell(style_source_row, col_idx)
                target = ws.cell(row_idx, col_idx)

                if source.has_style:
                    target._style = copy(source._style)

                if source.number_format:
                    target.number_format = source.number_format

            ws.cell(
                row_idx,
                11,
            ).value = (
                f'=IF(OR(C{row_idx}="",J{row_idx}=""),"",'
                f'C{row_idx}*J{row_idx})'
            )
            ws.cell(
                row_idx,
                13,
            ).value = (
                f'=IF(OR(C{row_idx}="",L{row_idx}=""),"",'
                f'C{row_idx}*L{row_idx})'
            )

        for excel_row, item in enumerate(items, start=2):
            sph_awal_unit = item["sph_awal_unit"]
            sph_final_unit = item["sph_final_unit"]

            if sph_awal_unit is None:
                sph_awal_unit = derive_unit_price(
                    item["qty"],
                    item["sph_awal"],
                )

            if sph_final_unit is None:
                sph_final_unit = derive_unit_price(
                    item["qty"],
                    item["sph_final"],
                )

            values = [
                item["item_no"] or "",
                item["product"] or "",
                item["qty"] if item["qty"] is not None else "",
                item["uom"] or "",
                item["preferred_brand"] or "",
                item["delivery_time"] or "",
                item["sow_name"] or "General Scope of Work",
                item["boq_name"] or "General Items",
                item["vendor"] or "",
                sph_awal_unit,
                None,
                sph_final_unit,
                None,
                item["id"] or "",
            ]

            for col_idx, value in enumerate(
                values,
                start=1,
            ):
                ws.cell(
                    excel_row,
                    col_idx,
                ).value = value

            ws.cell(
                excel_row,
                11,
            ).value = (
                f'=IF(OR(C{excel_row}="",J{excel_row}=""),"",'
                f'C{excel_row}*J{excel_row})'
            )

            ws.cell(
                excel_row,
                13,
            ).value = (
                f'=IF(OR(C{excel_row}="",L{excel_row}=""),"",'
                f'C{excel_row}*L{excel_row})'
            )

            if item["delivery_time"]:
                try:
                    parsed_date = datetime.strptime(
                        str(item["delivery_time"]),
                        "%Y-%m-%d",
                    ).date()
                    ws.cell(
                        excel_row,
                        6,
                    ).value = parsed_date
                    ws.cell(
                        excel_row,
                        6,
                    ).number_format = "yyyy-mm-dd"
                except ValueError:
                    pass

        if "BoQInputTable" in ws.tables:
            ws.tables["BoQInputTable"].ref = (
                f"A1:N{needed_last_row}"
            )

        try:
            wb.calculation.fullCalcOnLoad = True
            wb.calculation.forceFullCalc = True
            wb.calculation.calcMode = "auto"
        except Exception:
            pass

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        return send_file(
            output,
            mimetype=XLSX_MIMETYPE,
            as_attachment=True,
            download_name=f"BoQ_Revisi_{project_id}.xlsx",
        )

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# Legacy revision download alias.
@app.route("/api/download_boq_revision/<project_id>", methods=["GET"])
def download_boq_revision(project_id):
    return download_project_boq_template(project_id)


# ============================================================================
# MANAGEMENT REPORT
# ============================================================================
@app.route("/api/download_report", methods=["GET"])
def download_report():
    if not is_admin():
        return json_response_error(
            "Akses ditolak.",
            403,
        )

    target_project_id = str(
        request.args.get("project_id") or ""
    ).strip()

    try:
        with db_connect() as conn:
            projects = get_projects_relational(
                conn.cursor()
            )

        if target_project_id:
            projects = [
                project
                for project in projects
                if project.get("id") == target_project_id
            ]

        report_data = []

        for project in projects:
            for sow in project.get("sows") or []:
                for boq in sow.get("boqs") or []:
                    for item in boq.get("items") or []:
                        report_data.append(
                            {
                                "Ticket ID": project.get("id", ""),
                                "Project": project.get("name", ""),
                                "Requestor": project.get("requestorName", ""),
                                "PIC": project.get("leadId", ""),
                                "Status": project.get("status", ""),
                                "Date": project.get("createdAt", ""),
                                "Target RFS": project.get("targetRfs", ""),
                                "Pipeline Stage": project.get("pipelineStage", ""),
                                "Item ID": item.get("id", ""),
                                "Item No": item.get("itemNo", ""),
                                "SoW": sow.get("name", ""),
                                "BoQ": boq.get("name", ""),
                                "Description": item.get("product", ""),
                                "Qty": item.get("qty", 0),
                                "UoM": item.get("uom", ""),
                                "Preferred Brand": item.get("preferredBrand", ""),
                                "Delivery Time (RFS)": item.get("deliveryTime", ""),
                                "Vendor": item.get("vendor", ""),
                                "SPH Awal / Unit": item.get("sphAwalUnit"),
                                "Total SPH Awal": item.get("sphAwal"),
                                "SPH Final / Unit": item.get("sphFinalUnit"),
                                "Total SPH Final": item.get("sphFinal"),
                            }
                        )

        if not report_data:
            report_data.append(
                {
                    "Ticket ID": target_project_id or "-",
                    "Project": "Data tidak ditemukan",
                }
            )

        df = pd.DataFrame(report_data)

        output = io.BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl",
        ) as writer:
            df.to_excel(
                writer,
                index=False,
                sheet_name="Detail Project",
            )

            worksheet = writer.sheets["Detail Project"]
            worksheet.freeze_panes = "A2"
            worksheet.auto_filter.ref = worksheet.dimensions

            for column_cells in worksheet.columns:
                max_length = 0
                column_letter = column_cells[0].column_letter

                for cell in column_cells:
                    value = "" if cell.value is None else str(cell.value)
                    max_length = max(
                        max_length,
                        len(value),
                    )

                worksheet.column_dimensions[
                    column_letter
                ].width = min(
                    max(max_length + 2, 10),
                    32,
                )

        output.seek(0)

        return send_file(
            output,
            mimetype=XLSX_MIMETYPE,
            as_attachment=True,
            download_name=(
                f"Report_{target_project_id or 'All_Projects'}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            ),
        )

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# PROJECT-NEW EXCEL IMPORT PREVIEW
# ============================================================================
@app.route("/api/project_import_boq/preview", methods=["POST"])
def preview_project_import_boq():
    if not is_admin():
        return json_response_error(
            "Akses ditolak.",
            403,
        )

    if "file" not in request.files:
        return json_response_error(
            "File Excel tidak ditemukan."
        )

    file = request.files["file"]

    if not file.filename:
        return json_response_error(
            "Nama file tidak valid."
        )

    try:
        df = _read_boq_excel(
            file,
            require_system_id=False,
        )
        rows, issues = _parse_boq_rows(df)

        for item in rows:
            if item["id"]:
                issues.append(
                    {
                        "row": item["excelRow"],
                        "severity": "error",
                        "message": (
                            f'"{BOQ_COLUMN_SYSTEM_ID}" harus kosong '
                            "untuk Project Baru."
                        ),
                    }
                )

        grouped = {}

        for item in rows:
            sow_name = item["sowName"]
            boq_name = item["boqName"]

            grouped.setdefault(
                sow_name,
                {}
            ).setdefault(
                boq_name,
                []
            ).append(
                {
                    "id": generate_id("item"),
                    "itemNo": item["itemNo"],
                    "product": item["product"],
                    "qty": item["qty"],
                    "uom": item["uom"],
                    "preferredBrand": item["preferredBrand"],
                    "deliveryTime": item["deliveryTime"],
                    "vendor": item["vendor"],
                    "notes": "",
                    "picIds": [],
                    "sphAwalUnit": item["sphAwalUnit"],
                    "sphFinalUnit": item["sphFinalUnit"],
                    "sphAwal": item["sphAwal"],
                    "sphFinal": item["sphFinal"],
                }
            )

        result_sows = []

        for sow_name, boq_groups in grouped.items():
            sow_obj = {
                "id": generate_id("sow"),
                "name": sow_name,
                "boqs": [],
            }

            for boq_name, item_list in boq_groups.items():
                sow_obj["boqs"].append(
                    {
                        "id": generate_id("boq"),
                        "name": boq_name,
                        "items": item_list,
                    }
                )

            result_sows.append(sow_obj)

        errors = [
            issue for issue in issues
            if issue["severity"] == "error"
        ]

        warnings = [
            issue for issue in issues
            if issue["severity"] == "warning"
        ]

        total_boqs = sum(
            len(sow["boqs"])
            for sow in result_sows
        )

        total_items = sum(
            len(boq["items"])
            for sow in result_sows
            for boq in sow["boqs"]
        )

        return jsonify(
            {
                "success": True,
                "data": {
                    "summary": {
                        "rows": len(df),
                        "items": total_items,
                        "sows": len(result_sows),
                        "boqs": total_boqs,
                        "errors": len(errors),
                        "warnings": len(warnings),
                    },
                    "issues": issues[:50],
                    "has_errors": bool(errors),
                    "sows": result_sows,
                },
            }
        ), 200

    except ValueError as exc:
        return json_response_error(
            str(exc),
            400,
        )
    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# REVISION PREVIEW
# ============================================================================
def _revision_items_for_project(cursor, project_id):
    rows = cursor.execute(
        """
        SELECT
            i.*,
            b.name AS boq_name,
            s.name AS sow_name
        FROM items i
        JOIN boqs b
            ON i.boq_id = b.id
        JOIN sows s
            ON b.sow_id = s.id
        WHERE s.project_id = ?
        ORDER BY
            s.rowid,
            b.rowid,
            i.rowid
        """,
        (project_id,),
    ).fetchall()

    return [dict(row) for row in rows]


@app.route("/api/revisi_boq/preview", methods=["POST"])
def preview_revisi_boq():
    if not is_admin():
        return json_response_error(
            "Akses ditolak.",
            403,
        )

    ticket_id = str(
        request.form.get("ticket_id") or ""
    ).strip()

    if not ticket_id or "file" not in request.files:
        return json_response_error(
            "Data tidak valid."
        )

    try:
        df = _read_boq_excel(
            request.files["file"],
            require_system_id=True,
        )
        incoming, issues = _parse_boq_rows(df)

        with db_connect() as conn:
            project = conn.execute(
                "SELECT id FROM projects WHERE id = ?",
                (ticket_id,),
            ).fetchone()

            if project is None:
                return json_response_error(
                    "Project tidak ditemukan.",
                    404,
                )

            existing_rows = _revision_items_for_project(
                conn.cursor(),
                ticket_id,
            )

        existing = {
            str(row["id"]).strip(): row
            for row in existing_rows
            if row.get("id")
        }

        incoming_ids = {
            item["id"]
            for item in incoming
            if item["id"]
        }

        added = []
        updated = []
        unchanged = []

        for item in incoming:
            item_id = item["id"]

            if not item_id:
                added.append(
                    {
                        "description": item["product"],
                        "itemNo": item["itemNo"],
                        "qty": item["qty"],
                        "uom": item["uom"],
                        "vendor": item["vendor"],
                        "sphAwalUnit": item["sphAwalUnit"],
                        "sphFinalUnit": item["sphFinalUnit"],
                    }
                )
                continue

            old = existing.get(item_id)

            if old is None:
                issues.append(
                    {
                        "row": item["excelRow"],
                        "severity": "error",
                        "message": (
                            f"Item ID '{item_id}' tidak ditemukan "
                            "di project."
                        ),
                    }
                )
                continue

            changes = {}

            comparisons = [
                (
                    "Item No",
                    old.get("item_no"),
                    item["itemNo"],
                    "text",
                ),
                (
                    "Deskripsi Item",
                    old.get("product"),
                    item["product"],
                    "text",
                ),
                (
                    "Qty",
                    old.get("qty"),
                    item["qty"],
                    "qty",
                ),
                (
                    "UoM",
                    old.get("uom"),
                    item["uom"],
                    "text",
                ),
                (
                    "Preferred Brand",
                    old.get("preferred_brand"),
                    item["preferredBrand"],
                    "text",
                ),
                (
                    "Delivery Time (RFS)",
                    old.get("delivery_time"),
                    item["deliveryTime"],
                    "text",
                ),
                (
                    "Scope of Work",
                    old.get("sow_name"),
                    item["sowName"],
                    "text",
                ),
                (
                    "Bill of Quantity",
                    old.get("boq_name"),
                    item["boqName"],
                    "text",
                ),
                (
                    "Vendor",
                    old.get("vendor"),
                    item["vendor"],
                    "text",
                ),
            ]

            # Blank unit price in a revision means "do not change current
            # pricing". Supplying 0 is still a valid explicit price.
            if item["sphAwalUnit"] is not None:
                comparisons.append(
                    (
                        "SPH Awal / Unit",
                        old.get("sph_awal_unit"),
                        item["sphAwalUnit"],
                        "number",
                    )
                )
            elif old.get("sph_awal_unit") is not None:
                # Existing price stays as-is.
                pass

            if item["sphFinalUnit"] is not None:
                comparisons.append(
                    (
                        "SPH Final / Unit",
                        old.get("sph_final_unit"),
                        item["sphFinalUnit"],
                        "number",
                    )
                )

            for label, old_value, new_value, kind in comparisons:
                if normalize_compare_value(
                    old_value,
                    kind,
                ) != normalize_compare_value(
                    new_value,
                    kind,
                ):
                    changes[label] = [
                        _excel_text(old_value),
                        _excel_text(new_value),
                    ]

            if changes:
                updated.append(
                    {
                        "id": item_id,
                        "description": item["product"],
                        "qty": item["qty"],
                        "uom": item["uom"],
                        "vendor": item["vendor"],
                        "changes": changes,
                    }
                )
            else:
                unchanged.append(
                    {
                        "id": item_id,
                        "description": item["product"],
                    }
                )

        removed = [
            {
                "id": row["id"],
                "description": row.get("product", ""),
                "itemNo": row.get("item_no", ""),
            }
            for item_id, row in existing.items()
            if item_id not in incoming_ids
        ]

        errors = sum(
            1
            for issue in issues
            if issue["severity"] == "error"
        )

        warnings = sum(
            1
            for issue in issues
            if issue["severity"] == "warning"
        )

        return jsonify(
            {
                "success": True,
                "data": {
                    "summary": {
                        "added": len(added),
                        "updated": len(updated),
                        "removed": len(removed),
                        "unchanged": len(unchanged),
                        "errors": errors,
                        "warnings": warnings,
                    },
                    "issues": issues[:50],
                    "has_errors": errors > 0,
                    "added": added,
                    "updated": updated,
                    "removed": removed,
                    "unchanged": unchanged,
                },
            }
        ), 200

    except ValueError as exc:
        return json_response_error(
            str(exc),
            400,
        )
    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# REVISION APPLY
# ============================================================================
@app.route("/api/revisi_boq", methods=["POST"])
def revisi_boq():
    if not is_admin():
        return json_response_error(
            "Akses ditolak.",
            403,
        )

    ticket_id = str(
        request.form.get("ticket_id") or ""
    ).strip()

    if not ticket_id or "file" not in request.files:
        return json_response_error(
            "Data tidak valid."
        )

    try:
        df = _read_boq_excel(
            request.files["file"],
            require_system_id=True,
        )
        incoming, issues = _parse_boq_rows(df)

        if not incoming:
            return json_response_error(
                "File revisi tidak memiliki item."
            )

        validation_errors = [
            issue for issue in issues
            if issue["severity"] == "error"
        ]

        with db_connect() as conn:
            cursor = conn.cursor()

            project = cursor.execute(
                "SELECT id FROM projects WHERE id = ?",
                (ticket_id,),
            ).fetchone()

            if project is None:
                return json_response_error(
                    "Project tidak ditemukan.",
                    404,
                )

            existing_rows = _revision_items_for_project(
                cursor,
                ticket_id,
            )

            existing = {
                str(row["id"]).strip(): row
                for row in existing_rows
                if row.get("id")
            }

            seen_ids = set()

            for item in incoming:
                item_id = item["id"]

                if not item_id:
                    continue

                if item_id in seen_ids:
                    validation_errors.append(
                        {
                            "row": item["excelRow"],
                            "severity": "error",
                            "message": (
                                f"Item ID duplikat: {item_id}."
                            ),
                        }
                    )

                seen_ids.add(item_id)

                if item_id not in existing:
                    validation_errors.append(
                        {
                            "row": item["excelRow"],
                            "severity": "error",
                            "message": (
                                f"Item ID '{item_id}' tidak ditemukan "
                                "di project."
                            ),
                        }
                    )

            if validation_errors:
                return json_response_error(
                    "Excel revisi memiliki error. "
                    "Perbaiki file lalu upload kembali.",
                    400,
                    issues=validation_errors[:50],
                )

            sow_map = {}
            boq_map = {}

            sow_rows = cursor.execute(
                """
                SELECT id, name
                FROM sows
                WHERE project_id = ?
                ORDER BY rowid
                """,
                (ticket_id,),
            ).fetchall()

            for sow_row in sow_rows:
                sow_map[sow_row["name"]] = sow_row["id"]

                boq_rows = cursor.execute(
                    """
                    SELECT id, name
                    FROM boqs
                    WHERE sow_id = ?
                    ORDER BY rowid
                    """,
                    (sow_row["id"],),
                ).fetchall()

                for boq_row in boq_rows:
                    boq_map[
                        (
                            sow_row["name"],
                            boq_row["name"],
                        )
                    ] = boq_row["id"]

            incoming_existing_ids = set()

            for item in incoming:
                sow_name = (
                    item["sowName"]
                    or "General Scope of Work"
                )
                boq_name = (
                    item["boqName"]
                    or "General Items"
                )

                if sow_name not in sow_map:
                    sow_id = generate_id("sow")
                    cursor.execute(
                        """
                        INSERT INTO sows (
                            id,
                            project_id,
                            name
                        ) VALUES (?, ?, ?)
                        """,
                        (
                            sow_id,
                            ticket_id,
                            sow_name,
                        ),
                    )
                    sow_map[sow_name] = sow_id

                sow_id = sow_map[sow_name]
                boq_key = (sow_name, boq_name)

                if boq_key not in boq_map:
                    boq_id = generate_id("boq")
                    cursor.execute(
                        """
                        INSERT INTO boqs (
                            id,
                            sow_id,
                            name
                        ) VALUES (?, ?, ?)
                        """,
                        (
                            boq_id,
                            sow_id,
                            boq_name,
                        ),
                    )
                    boq_map[boq_key] = boq_id

                target_boq_id = boq_map[boq_key]
                item_id = item["id"]

                if item_id:
                    old = existing[item_id]
                    incoming_existing_ids.add(item_id)

                    old_awal_unit = old.get("sph_awal_unit")
                    old_final_unit = old.get("sph_final_unit")

                    if item["sphAwalUnit"] is not None:
                        sph_awal_unit = item["sphAwalUnit"]
                        sph_awal_total = calculate_sph_total(
                            item["qty"],
                            sph_awal_unit,
                        )
                    elif old_awal_unit is not None:
                        sph_awal_unit = old_awal_unit
                        sph_awal_total = calculate_sph_total(
                            item["qty"],
                            sph_awal_unit,
                        )
                    else:
                        sph_awal_unit = derive_unit_price(
                            old.get("qty"),
                            old.get("sph_awal"),
                        )
                        sph_awal_total = old.get("sph_awal")

                    if item["sphFinalUnit"] is not None:
                        sph_final_unit = item["sphFinalUnit"]
                        sph_final_total = calculate_sph_total(
                            item["qty"],
                            sph_final_unit,
                        )
                    elif old_final_unit is not None:
                        sph_final_unit = old_final_unit
                        sph_final_total = calculate_sph_total(
                            item["qty"],
                            sph_final_unit,
                        )
                    else:
                        sph_final_unit = derive_unit_price(
                            old.get("qty"),
                            old.get("sph_final"),
                        )
                        sph_final_total = old.get("sph_final")

                    cursor.execute(
                        """
                        UPDATE items
                        SET
                            boq_id = ?,
                            product = ?,
                            qty = ?,
                            uom = ?,
                            vendor = ?,
                            sph_awal = ?,
                            sph_final = ?,
                            item_no = ?,
                            preferred_brand = ?,
                            delivery_time = ?,
                            sph_awal_unit = ?,
                            sph_final_unit = ?
                        WHERE id = ?
                        """,
                        (
                            target_boq_id,
                            item["product"],
                            item["qty"],
                            item["uom"],
                            item["vendor"],
                            sph_awal_total,
                            sph_final_total,
                            item["itemNo"],
                            item["preferredBrand"],
                            item["deliveryTime"],
                            sph_awal_unit,
                            sph_final_unit,
                            item_id,
                        ),
                    )

                else:
                    new_item_id = generate_id("item")

                    sph_awal_unit = item["sphAwalUnit"]
                    sph_final_unit = item["sphFinalUnit"]

                    sph_awal_total = calculate_sph_total(
                        item["qty"],
                        sph_awal_unit,
                    )
                    sph_final_total = calculate_sph_total(
                        item["qty"],
                        sph_final_unit,
                    )

                    cursor.execute(
                        """
                        INSERT INTO items (
                            id,
                            boq_id,
                            product,
                            qty,
                            uom,
                            vendor,
                            sph_awal,
                            sph_final,
                            notes,
                            pic_ids,
                            item_no,
                            preferred_brand,
                            delivery_time,
                            sph_awal_unit,
                            sph_final_unit
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            new_item_id,
                            target_boq_id,
                            item["product"],
                            item["qty"],
                            item["uom"],
                            item["vendor"],
                            sph_awal_total,
                            sph_final_total,
                            "",
                            "[]",
                            item["itemNo"],
                            item["preferredBrand"],
                            item["deliveryTime"],
                            sph_awal_unit,
                            sph_final_unit,
                        ),
                    )

            # Entire working BoQ is replaced by the uploaded file.
            # Existing IDs absent from the revision are removed.
            for item_id in set(existing) - incoming_existing_ids:
                cursor.execute(
                    "DELETE FROM items WHERE id = ?",
                    (item_id,),
                )

            # Remove empty groups left behind by deleted items.
            cursor.execute(
                """
                DELETE FROM boqs
                WHERE id NOT IN (
                    SELECT DISTINCT boq_id
                    FROM items
                    WHERE boq_id IS NOT NULL
                )
                """
            )

            cursor.execute(
                """
                DELETE FROM sows
                WHERE id NOT IN (
                    SELECT DISTINCT sow_id
                    FROM boqs
                    WHERE sow_id IS NOT NULL
                )
                """
            )

            conn.commit()

        return jsonify(
            {
                "success": True,
                "message": (
                    f"BoQ berhasil direvisi. "
                    f"{len(incoming)} item pada working BoQ sekarang "
                    "mengikuti file yang diunggah."
                ),
            }
        ), 200

    except ValueError as exc:
        return json_response_error(
            str(exc),
            400,
        )
    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


# ============================================================================
# SPH COMPARISON DOCUMENTS
# ============================================================================
@app.route("/api/upload_comparison", methods=["POST"])
def upload_comparison():
    if not is_admin():
        return json_response_error(
            "Akses ditolak.",
            403,
        )

    ticket_id = str(
        request.form.get("ticket_id") or ""
    ).strip()
    vendor_name = str(
        request.form.get("vendor_name") or ""
    ).strip()
    offered_price_raw = str(
        request.form.get("offered_price") or ""
    ).strip()

    if (
        not ticket_id
        or not vendor_name
        or not offered_price_raw
        or "file" not in request.files
    ):
        return json_response_error(
            "Data tidak lengkap."
        )

    file = request.files["file"]

    if not file.filename:
        return json_response_error(
            "File tidak valid."
        )

    try:
        offered_price = float(
            offered_price_raw.replace(",", "")
        )

        if offered_price < 0:
            raise ValueError

    except ValueError:
        return json_response_error(
            "Harga penawaran harus berupa angka non-negatif."
        )

    try:
        with db_connect() as conn:
            exists = conn.execute(
                "SELECT 1 FROM projects WHERE id = ?",
                (ticket_id,),
            ).fetchone()

            if exists is None:
                return json_response_error(
                    "Project tidak ditemukan.",
                    404,
                )

        os.makedirs(
            COMPARISON_DIR,
            exist_ok=True,
        )

        safe_base = secure_filename(
            file.filename
        )

        if not safe_base:
            return json_response_error(
                "Nama file tidak valid."
            )

        ext = (
            safe_base.rsplit(".", 1)[1].lower()
            if "." in safe_base
            else "bin"
        )

        allowed_exts = {
            "pdf",
            "xls",
            "xlsx",
            "jpg",
            "jpeg",
            "png",
        }

        if ext not in allowed_exts:
            return json_response_error(
                "Format file tidak didukung."
            )

        safe_filename = (
            f"{ticket_id}_"
            f"{uuid.uuid4().hex[:8]}."
            f"{ext}"
        )

        disk_path = os.path.join(
            COMPARISON_DIR,
            safe_filename,
        )

        file.save(disk_path)

        web_file_path = (
            f"/api/downloads/comparisons/"
            f"{safe_filename}"
        )

        try:
            with db_connect() as conn:
                conn.execute(
                    """
                    INSERT INTO comparison_docs (
                        project_id,
                        vendor_name,
                        offered_price,
                        file_path
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        ticket_id,
                        vendor_name,
                        offered_price,
                        web_file_path,
                    ),
                )
                conn.commit()
        except Exception:
            try:
                os.remove(disk_path)
            except OSError:
                pass
            raise

        return jsonify(
            {
                "success": True,
                "message": (
                    "Dokumen pembanding berhasil diunggah"
                ),
            }
        ), 200

    except Exception as exc:
        return json_response_error(
            str(exc),
            500,
        )


@app.route(
    "/api/downloads/comparisons/<filename>",
    methods=["GET"],
)
def download_comparison(filename):
    if not is_logged_in():
        return json_response_error(
            "Akses ditolak. Silakan login.",
            403,
        )

    safe_filename = secure_filename(filename)

    if not safe_filename:
        return json_response_error(
            "Nama file tidak valid.",
            400,
        )

    return send_from_directory(
        COMPARISON_DIR,
        safe_filename,
    )


# ============================================================================
# SERVER ENTRY POINT
# ============================================================================
if __name__ == "__main__":
    port = int(
        os.environ.get(
            "PORT",
            5001,
        )
    )

    app.run(
        host="0.0.0.0",
        port=port,
        debug=True,
    )
