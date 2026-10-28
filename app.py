from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file, send_from_directory
from flask_cors import CORS
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.worksheet.datavalidation import DataValidation
from copy import copy
from openpyxl.cell.cell import MergedCell
import pandas as pd
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor, execute_values
import json
import os
from io import BytesIO
import io
import uuid
import csv
import math
import hashlib
import hmac
import secrets
import re
import unicodedata
from datetime import datetime
from urllib.parse import urlparse
from zoneinfo import ZoneInfo
import contextlib
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

# Run the same password-hash verification cost for unknown usernames to reduce user enumeration via timing.
_LOGIN_DUMMY_PASSWORD_HASH = generate_password_hash(secrets.token_urlsafe(32))

# ============================================================================
# APP CONFIGURATION
# ============================================================================
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = os.getenv("SESSION_COOKIE_SECURE", "true").strip().lower() in {"1", "true", "yes", "on"}
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 8

# Production secrets/credentials must be provided by the service environment, never source control.
SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "presourcing_secret_key_123").strip()
DB_HOST = os.getenv("PRESOURCING_DB_HOST", "localhost").strip()
DB_NAME = os.getenv("PRESOURCING_DB_NAME", "presourcing_db").strip()
DB_USER = os.getenv("PRESOURCING_DB_USER", "presourcing_master").strip()
DB_PASS = os.getenv("PRESOURCING_DB_PASSWORD", "R1L1DemDldxks@")
if len(SECRET_KEY) < 16:
    raise RuntimeError("FLASK_SECRET_KEY wajib disetel dari environment dan minimal 32 karakter.")
if not DB_USER or not DB_PASS:
    raise RuntimeError("PRESOURCING_DB_USER dan PRESOURCING_DB_PASSWORD wajib disetel dari environment.")
app.secret_key = SECRET_KEY

# Same-origin deployment does not need open CORS. If a separate trusted UI origin is used,
# list it explicitly in CORS_ORIGINS (comma-separated).
_ALLOWED_CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "").split(",") if x.strip()]
if _ALLOWED_CORS_ORIGINS:
    CORS(app, resources={r"/api/*": {"origins": _ALLOWED_CORS_ORIGINS}})


def _normalized_origin(value):
    """Return an HTTP(S) origin without path/query; reject opaque or malformed origins."""
    try:
        parsed = urlparse(str(value or ""))
        if parsed.scheme.lower() not in {"http", "https"} or not parsed.netloc:
            return None
        if parsed.username or parsed.password:
            return None
        return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"
    except Exception:
        return None


@app.before_request
def leasing_and_auth_csrf_origin_guard():
    """Block cross-origin browser mutations on Leasing and account-security APIs.

    Same-origin browser requests send Origin; Referer is a safe fallback for compatible
    clients. Non-browser clients must deliberately supply a trusted Origin/Referer rather
    than implicitly bypassing session-cookie CSRF checks.
    """
    guarded_paths = request.path.startswith("/api/leasing/") or request.path in {
        "/api/login", "/api/register", "/api/change-password", "/api/logout"
    }
    if not guarded_paths or request.method.upper() in {"GET", "HEAD", "OPTIONS"}:
        return None
    expected_origins = {_normalized_origin(request.host_url)}
    expected_origins.update(origin for origin in (_normalized_origin(x) for x in _ALLOWED_CORS_ORIGINS) if origin)
    supplied = request.headers.get("Origin")
    if not supplied:
        supplied = request.headers.get("Referer")
    request_origin = _normalized_origin(supplied)
    if not request_origin or request_origin not in expected_origins:
        return jsonify({"success": False, "code": "CSRF_ORIGIN_REJECTED",
                        "message": "Permintaan perubahan ditolak karena origin tidak dikenal. Muat ulang aplikasi dan coba dari alamat resmi."}), 403
    return None

# Gunicorn creates one pool per worker. Keep per-process defaults conservative so a
# 4-worker deployment does not silently allocate 80+ connections to the identity DB.
def _leasing_pool_bounds(prefix, default_min=1, default_max=5):
    try:
        minimum = int(os.getenv(f"{prefix}_POOL_MIN", str(default_min)))
        maximum = int(os.getenv(f"{prefix}_POOL_MAX", str(default_max)))
    except ValueError as exc:
        raise RuntimeError(f"{prefix}_POOL_MIN/MAX harus berupa bilangan bulat.") from exc
    if minimum < 1 or maximum < minimum:
        raise RuntimeError(f"Konfigurasi {prefix} pool tidak valid: pastikan 1 <= MIN <= MAX.")
    return minimum, maximum

PRESOURCING_POOL_MIN, PRESOURCING_POOL_MAX = _leasing_pool_bounds("PRESOURCING_DB")
LEASING_POOL_MIN, LEASING_POOL_MAX = _leasing_pool_bounds("LEASING_DB")

db_pool = ThreadedConnectionPool(
    PRESOURCING_POOL_MIN, PRESOURCING_POOL_MAX,
    host=DB_HOST,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASS
)

@contextlib.contextmanager
def get_db_connection():
    """Borrow a connection and return it to the pool with a clean transaction state."""
    conn = None
    try:
        conn = db_pool.getconn()
        yield conn
    except Exception:
        if conn is not None:
            try: conn.rollback()
            except Exception: app.logger.exception("Identity/M&S connection rollback failed")
        raise
    finally:
        if conn is not None:
            try: conn.rollback()
            except Exception: app.logger.exception("Identity/M&S connection reset failed")
            db_pool.putconn(conn)

# Leasing uses its own PostgreSQL database; user identity remains in presourcing_db.public.users.
LEASING_DB_NAME = os.getenv("LEASING_DB_NAME", "leasing_db").strip()
leasing_db_pool = ThreadedConnectionPool(
    LEASING_POOL_MIN, LEASING_POOL_MAX,
    host=DB_HOST,
    database=LEASING_DB_NAME,
    user=DB_USER,
    password=DB_PASS,
)

@contextlib.contextmanager
def get_leasing_db_connection():
    """Borrow a Leasing connection and return it to the pool cleanly."""
    conn = None
    try:
        conn = leasing_db_pool.getconn()
        yield conn
    except Exception:
        if conn is not None:
            try: conn.rollback()
            except Exception: app.logger.exception("Leasing connection rollback failed")
        raise
    finally:
        if conn is not None:
            try: conn.rollback()
            except Exception: app.logger.exception("Leasing connection reset failed")
            leasing_db_pool.putconn(conn)

# ============================================================================
# EXCEL TEMPLATE CONFIGURATION (14 KOLOM RIGID)
# ============================================================================
BOQ_CORE_COLUMNS = [
    "Item No", "Deskripsi Item", "Qty", "UoM", "Preferred Brand",
    "Delivery Time (RFS)", "SPH Awal / Unit", "SPH Final / Unit",
]
BOQ_OPTIONAL_COLUMNS = ["Scope of Work (Opsional)", "Bill of Quantity (Opsional)", "Vendor (Opsional)"]
BOQ_DERIVED_COLUMNS = ["Total SPH Awal", "Total SPH Final"]
BOQ_SYSTEM_COLUMN = "Item ID (System)"
BOQ_TEMPLATE_FILENAME = "Template_BoQ_Presourcing.xlsx"

# ============================================================================
# EXCEL HELPERS
# ============================================================================
def _excel_text(value):
    if value is None: 
        return ""
    try:
        if pd.isna(value): 
            return ""
    except (TypeError, ValueError): 
        pass
    
    if isinstance(value, pd.Timestamp): 
        return value.strftime("%Y-%m-%d")
    
    if isinstance(value, float) and value.is_integer(): 
        return str(int(value))
    
    return str(value).strip()

def _excel_qty(value, default=0):
    text = _excel_text(value)
    if text == "": 
        return default
    
    try: 
        number = float(value)
    except (TypeError, ValueError): 
        raise ValueError("Qty harus berupa angka.")
    
    if number < 0: 
        raise ValueError("Qty tidak boleh negatif.")
    
    return number

def optional_number(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    text = _excel_text(value)
    if text == "":
        return None

    cleaned_text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")

    try:
        number = float(cleaned_text)
    except (TypeError, ValueError):
        raise ValueError(f"Nilai harga harus berupa angka (diterima: '{text}').")

    if number < 0:
        raise ValueError("Harga tidak boleh negatif.")

    return number

def calculate_sph_total(qty, unit_price):
    if qty is None or unit_price is None: 
        return None
    try:
        qty = float(qty)
        unit_price = float(unit_price)
    except (TypeError, ValueError): 
        return None
    
    return qty * unit_price

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

def resolve_sph_values(qty, unit_price, legacy_total=None):
    unit_price = optional_number(unit_price)
    if unit_price is not None:
        return (unit_price, calculate_sph_total(qty, unit_price))
    
    return (None, optional_number(legacy_total))

def _read_boq_excel(file, require_system_id=False):
    file.stream.seek(0)
    df = pd.read_excel(file, sheet_name=0, header=None)
    
    header_row_idx = 0
    for idx, row in df.iterrows():
        row_str_values = [str(val).strip() for val in row.values]
        if "Deskripsi Item" in row_str_values or "Item No" in row_str_values:
            header_row_idx = idx
            break

    df.columns = df.iloc[header_row_idx]
    df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
    df.columns = [_excel_text(col) for col in df.columns]

    required_columns = BOQ_CORE_COLUMNS + BOQ_DERIVED_COLUMNS
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError("Format template tidak sesuai. Kolom wajib tidak ditemukan: " + ", ".join(missing))

    if require_system_id and BOQ_SYSTEM_COLUMN not in df.columns:
        raise ValueError(f"Kolom '{BOQ_SYSTEM_COLUMN}' wajib ada untuk file revisi.")

    if BOQ_SYSTEM_COLUMN not in df.columns:
        df[BOQ_SYSTEM_COLUMN] = ""

    for col in BOQ_OPTIONAL_COLUMNS:
        if col not in df.columns: 
            df[col] = ""

    for col in BOQ_DERIVED_COLUMNS:
        if col not in df.columns: 
            df[col] = ""

    return df.fillna("")

def _parse_boq_rows(df):
    rows = []
    issues = []
    seen_ids = {}

    for excel_idx, row in df.iterrows():
        excel_row = excel_idx + 2
        description = _excel_text(row.get("Deskripsi Item"))
        
        if not description: 
            continue

        item_id = _excel_text(row.get(BOQ_SYSTEM_COLUMN))
        if item_id:
            if item_id in seen_ids:
                issues.append({"row": excel_row, "severity": "error", "message": f"Item ID duplikat dengan row {seen_ids[item_id]}."})
            else:
                seen_ids[item_id] = excel_row

        qty_raw = row.get("Qty", "")
        qty = 0
        if _excel_text(qty_raw):
            try: 
                qty = _excel_qty(qty_raw)
            except ValueError as exc: 
                issues.append({"row": excel_row, "severity": "error", "message": str(exc)})
        else:
            issues.append({"row": excel_row, "severity": "warning", "message": "Qty kosong; sistem menyimpan Qty = 0."})

        uom = _excel_text(row.get("UoM"))
        if not uom: 
            issues.append({"row": excel_row, "severity": "warning", "message": "UoM kosong."})

        sph_awal_unit = None
        sph_final_unit = None

        try: 
            sph_awal_unit = optional_number(row.get("SPH Awal / Unit"))
        except ValueError as exc: 
            issues.append({"row": excel_row, "severity": "error", "message": f"SPH Awal / Unit: {exc}"})

        try: 
            sph_final_unit = optional_number(row.get("SPH Final / Unit"))
        except ValueError as exc: 
            issues.append({"row": excel_row, "severity": "error", "message": f"SPH Final / Unit: {exc}"})

        rows.append({
            "excelRow": excel_row,
            "id": item_id,
            "itemNo": _excel_text(row.get("Item No")),
            "product": description,
            "qty": qty,
            "uom": uom,
            "preferredBrand": _excel_text(row.get("Preferred Brand")),
            "deliveryTime": _excel_text(row.get("Delivery Time (RFS)")),
            "sowName": _excel_text(row.get("Scope of Work (Opsional)")) or "General Scope of Work",
            "boqName": _excel_text(row.get("Bill of Quantity (Opsional)")) or "General Items",
            "vendor": _excel_text(row.get("Vendor (Opsional)")),
            "sphAwalUnit": sph_awal_unit,
            "sphAwalTotal": calculate_sph_total(qty, sph_awal_unit),
            "sphFinalUnit": sph_final_unit,
            "sphFinalTotal": calculate_sph_total(qty, sph_final_unit)
        })

    for idx, item in enumerate(rows, start=1):
        if not item["itemNo"]: 
            item["itemNo"] = str(idx)

    return rows, issues

# ============================================================================
# WORKSPACE ACCESS & PAGE ROUTES
# ============================================================================
# Keep the legacy `admin` role mapped to Presourcing M&S for backward compatibility.
# Leasing gets separate roles; `platform_admin` is the only built-in cross-workspace role.
MS_ADMIN_ROLES = frozenset({"admin", "ms_admin", "platform_admin"})
LEASING_ROLES = frozenset({"buyer", "leasing_admin", "platform_admin"})


def has_ms_access(role):
    return role in MS_ADMIN_ROLES


def has_leasing_access(role):
    return role in LEASING_ROLES


def preferred_landing_endpoint(role):
    """Resolve a user's default workspace after login or when /portal is requested."""
    if role in {"buyer", "leasing_admin"}:
        return "leasing_dashboard_page"
    if has_ms_access(role):
        # A cross-workspace platform admin defaults to M&S and can switch to Leasing.
        return "index"
    return "sa_portal"


@app.route("/")
def index():
    if not session.get("username"):
        return redirect(url_for("login_page"))
    if session.get("password_must_change"):
        return redirect(url_for("change_password_page"))
    if not has_ms_access(session.get("role")):
        return redirect(url_for(preferred_landing_endpoint(session.get("role"))))
    return render_template(
        "presourcing-dashboard.html",
        can_access_leasing=has_leasing_access(session.get("role")),
    )


@app.route("/login")
def login_page():
    if "username" in session:
        return redirect(url_for(preferred_landing_endpoint(session.get("role"))))
    return render_template("login.html")


@app.route("/portal")
def sa_portal():
    if "username" not in session:
        return redirect(url_for("login_page"))
    if session.get("password_must_change"):
        return redirect(url_for("change_password_page"))
    # Also catches legacy login.html scripts that always redirect to /portal.
    # Buyer/Leasing Admin goes to Leasing; M&S admins go to M&S; SA remains in portal.
    target = preferred_landing_endpoint(session.get("role"))
    if target != "sa_portal":
        return redirect(url_for(target))
    return render_template("sa-portal.html")


@app.route("/leasing")
def leasing_dashboard_page():
    """Dedicated Leasing workspace for Buyer/Leasing Admin; M&S stays separate."""
    if not session.get("username"):
        return redirect(url_for("login_page"))
    if session.get("password_must_change"):
        return redirect(url_for("change_password_page"))
    if not has_leasing_access(session.get("role")):
        return "Akses Leasing hanya untuk Buyer/Admin Leasing.", 403
    return render_template(
        "leasing-dashboard.html",
        can_access_ms=has_ms_access(session.get("role")),
    )


@app.route("/leasing/work-items/<int:work_item_id>")
def leasing_work_item_page(work_item_id):
    """Full-page permalink for large Work Items; every data API still rechecks scope."""
    if not session.get("username"):
        return redirect(url_for("login_page"))
    if session.get("password_must_change"):
        return redirect(url_for("change_password_page"))
    if not has_leasing_access(session.get("role")):
        return "Akses Leasing hanya untuk Buyer/Admin Leasing.", 403
    if not _is_leasing_admin() and not leasing_user_can_access_work_item(work_item_id, session.get("username")):
        return redirect(url_for("leasing_dashboard_page"))
    return render_template("leasing-dashboard.html", can_access_ms=has_ms_access(session.get("role")),
                           initial_work_item_id=work_item_id, dedicated_work_item_page=True)

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================
def init_db():
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""CREATE TABLE IF NOT EXISTS dashboard_state (id SERIAL PRIMARY KEY, data_type TEXT UNIQUE, json_data TEXT)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS users (id SERIAL PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, full_name TEXT NOT NULL, department TEXT, role TEXT NOT NULL)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS requests (id SERIAL PRIMARY KEY, ticket_id TEXT UNIQUE NOT NULL, title TEXT NOT NULL, client_name TEXT, competitor_info TEXT, sla_date TEXT NOT NULL, notes TEXT, status TEXT DEFAULT 'unassigned', requester_username TEXT NOT NULL, pic_username TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS request_items (id SERIAL PRIMARY KEY, ticket_id TEXT NOT NULL, sow_name TEXT DEFAULT 'General Scope', boq_section TEXT DEFAULT 'General Items', item_no TEXT, description TEXT NOT NULL, preferred_brand TEXT, quantity REAL, uom TEXT, delivery_time TEXT, vendor TEXT, sph_awal_unit REAL, sph_final_unit REAL, FOREIGN KEY (ticket_id) REFERENCES requests(ticket_id) ON DELETE CASCADE)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS notifications (id SERIAL PRIMARY KEY, target_user TEXT NOT NULL, message TEXT NOT NULL, is_read INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT, requestor_name TEXT, requestor_dept TEXT, priority TEXT, status TEXT, lead_id TEXT, sph_mode TEXT, project_sph_awal REAL, project_sph_final REAL, created_at TEXT, closed_at TEXT, target_rfs TEXT, pipeline_stage TEXT, progress_pct INTEGER)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS sows (id TEXT PRIMARY KEY, project_id TEXT, name TEXT, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS boqs (id TEXT PRIMARY KEY, sow_id TEXT, name TEXT, FOREIGN KEY(sow_id) REFERENCES sows(id) ON DELETE CASCADE)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, boq_id TEXT, product TEXT, qty REAL, uom TEXT, vendor TEXT, sph_awal REAL, sph_final REAL, notes TEXT, pic_ids TEXT, item_no TEXT, preferred_brand TEXT, delivery_time TEXT, sph_awal_unit REAL, sph_final_unit REAL, FOREIGN KEY(boq_id) REFERENCES boqs(id) ON DELETE CASCADE)""")
            cursor.execute("""CREATE TABLE IF NOT EXISTS comparison_docs (id SERIAL PRIMARY KEY, project_id TEXT, vendor_name TEXT, offered_price REAL, file_path TEXT, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
            
            # Do not seed known default credentials automatically. Provision users using the secured admin workflow.
            conn.commit()

init_db()

# ============================================================================
# RELATIONAL DATA HELPER (Bulk Fetch)
# ============================================================================
def get_projects_relational(cursor):
    cursor.execute("SELECT * FROM projects")
    projects = [dict(row) for row in cursor.fetchall()]
    if not projects: 
        return []
    
    project_ids = tuple(p["id"] for p in projects)

    cursor.execute("SELECT * FROM comparison_docs WHERE project_id IN %s", (project_ids,))
    docs = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT id, project_id, name FROM sows WHERE project_id IN %s", (project_ids,))
    sows = [dict(row) for row in cursor.fetchall()]
    sow_ids = tuple(s["id"] for s in sows)

    boqs = []
    if sow_ids:
        cursor.execute("SELECT id, sow_id, name FROM boqs WHERE sow_id IN %s", (sow_ids,))
        boqs = [dict(row) for row in cursor.fetchall()]
    boq_ids = tuple(b["id"] for b in boqs)

    items = []
    if boq_ids:
        cursor.execute("SELECT * FROM items WHERE boq_id IN %s", (boq_ids,))
        raw_items = [dict(row) for row in cursor.fetchall()]
        for i in raw_items:
            i["picIds"] = json.loads(i["pic_ids"]) if i["pic_ids"] else []
            i["sphAwal"] = i.pop("sph_awal")
            i["sphFinal"] = i.pop("sph_final")
            i["sphAwalUnit"] = i.pop("sph_awal_unit", None) or derive_unit_price(i.get("qty"), i["sphAwal"])
            i["sphFinalUnit"] = i.pop("sph_final_unit", None) or derive_unit_price(i.get("qty"), i["sphFinal"])
            i["itemNo"] = i.pop("item_no", "")
            i["preferredBrand"] = i.pop("preferred_brand", "")
            i["deliveryTime"] = i.pop("delivery_time", "")
            items.append(i)

    items_by_boq = {}
    for item in items: 
        items_by_boq.setdefault(item["boq_id"], []).append(item)
    for b in boqs: 
        b["items"] = items_by_boq.get(b["id"], [])

    boqs_by_sow = {}
    for b in boqs: 
        boqs_by_sow.setdefault(b["sow_id"], []).append(b)
    for s in sows: 
        s["boqs"] = boqs_by_sow.get(s["id"], [])

    sows_by_project = {}
    for s in sows: 
        sows_by_project.setdefault(s["project_id"], []).append(s)
    
    docs_by_project = {}
    for d in docs: 
        docs_by_project.setdefault(d["project_id"], []).append(d)

    for p in projects:
        p["comparison_docs"] = docs_by_project.get(p["id"], [])
        p["sows"] = sows_by_project.get(p["id"], [])
        p["requestorName"] = p.pop("requestor_name")
        p["requestorDept"] = p.pop("requestor_dept")
        p["leadId"] = p.pop("lead_id")
        p["sphMode"] = p.pop("sph_mode")
        p["projectSphAwal"] = p.pop("project_sph_awal")
        p["projectSphFinal"] = p.pop("project_sph_final")
        p["createdAt"] = p.pop("created_at")
        p["closedAt"] = p.pop("closed_at")
        p["targetRfs"] = p.pop("target_rfs", None)
        p["pipelineStage"] = p.pop("pipeline_stage", None)
        p["progressPct"] = p.pop("progress_pct", None)
        
    return projects

# ============================================================================
# AUTH & NOTIFICATIONS
# ============================================================================
@app.route("/api/register", methods=["POST"])
def register():
    """No public self-registration. Only a platform admin may provision identity accounts."""
    if not session.get("username"):
        return jsonify({"success": False, "message": "Login diperlukan."}), 401
    if session.get("role") != "platform_admin":
        return jsonify({"success": False, "message": "Registrasi akun hanya dapat dilakukan Platform Admin."}), 403
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip().lower()
    full_name = str(payload.get("full_name") or "").strip()
    department = str(payload.get("department") or "").strip()
    password = str(payload.get("password") or "")
    role = str(payload.get("role") or "sa").strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,49}", username):
        return jsonify({"success": False, "message": "Username harus 3–50 karakter: huruf kecil, angka, titik, _ atau -."}), 400
    if not full_name:
        return jsonify({"success": False, "message": "Nama lengkap wajib diisi."}), 400
    if len(password) < 12:
        return jsonify({"success": False, "message": "Password minimal 12 karakter."}), 400
    if role not in {"sa", "buyer", "leasing_admin", "platform_admin", "admin", "ms_admin"}:
        return jsonify({"success": False, "message": "Role tidak diizinkan."}), 400
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    "INSERT INTO public.users (username, password, password_hash, password_must_change, full_name, department, role) "
                    "VALUES (%s, NULL, %s, FALSE, %s, %s, %s) RETURNING id, username, full_name, department, role",
                    (username, generate_password_hash(password), full_name, department, role)
                )
                user = dict(cursor.fetchone())
            conn.commit()
        return jsonify({"success": True, "user": user, "message": "Akun berhasil dibuat."}), 201
    except psycopg2.IntegrityError:
        return jsonify({"success": False, "message": "Username sudah terdaftar."}), 409


@app.route("/api/login", methods=["POST"])
def login():
    payload = request.get_json(silent=True) or {}
    username = str(payload.get("username") or "").strip()
    supplied_password = str(payload.get("password") or "")
    if not username or not supplied_password:
        return jsonify({"success": False, "message": "Username dan password wajib diisi."}), 400
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("""SELECT id, username, password, password_hash, password_must_change,
                    full_name, department, role FROM public.users WHERE username = %s""", (username,))
            row = cursor.fetchone()
            if not row:
                # Perform a real hash check so an unknown user is not significantly faster than
                # a wrong password for an existing user. Keep response text/status identical.
                check_password_hash(_LOGIN_DUMMY_PASSWORD_HASH, supplied_password)
                return jsonify({"success": False, "message": "Username atau password salah."}), 401
            stored_hash = row.get("password_hash")
            if stored_hash:
                valid_password = check_password_hash(stored_hash, supplied_password)
            else:
                legacy = str(row.get("password") or "")
                valid_password = bool(legacy) and hmac.compare_digest(legacy, supplied_password)
            if not valid_password:
                return jsonify({"success": False, "message": "Username atau password salah."}), 401
            # Migrate a legacy password only after successful authentication.
            if not stored_hash:
                cursor.execute("UPDATE public.users SET password_hash=%s, password=NULL WHERE id=%s",
                               (generate_password_hash(supplied_password), row["id"]))
            safe_user = {k: row.get(k) for k in ("username", "full_name", "department", "role", "password_must_change")}
            session.clear()
            session.update({"username": row["username"], "full_name": row["full_name"],
                            "department": row["department"], "role": row["role"],
                            "password_must_change": bool(row.get("password_must_change"))})
            conn.commit()
    dest = "change_password_page" if safe_user["password_must_change"] else preferred_landing_endpoint(safe_user["role"])
    return jsonify({"success": True, "user": safe_user, "redirect_url": url_for(dest),
                    "password_change_required": bool(safe_user["password_must_change"])}), 200


@app.route("/change-password")
def change_password_page():
    if not session.get("username"):
        return redirect(url_for("login_page"))
    if not session.get("password_must_change"):
        return redirect(url_for(preferred_landing_endpoint(session.get("role"))))
    return render_template("change-password.html")


@app.route("/api/change-password", methods=["POST"])
def change_password_api():
    if not session.get("username"):
        return jsonify({"success": False, "message": "Login diperlukan."}), 401
    payload = request.get_json(silent=True) or {}
    current_password = str(payload.get("current_password") or "")
    new_password = str(payload.get("new_password") or "")
    confirm_password = str(payload.get("confirm_password") or "")
    if len(new_password) < 12:
        return jsonify({"success": False, "message": "Password baru minimal 12 karakter."}), 400
    if new_password != confirm_password:
        return jsonify({"success": False, "message": "Konfirmasi password tidak cocok."}), 400
    if new_password == current_password:
        return jsonify({"success": False, "message": "Password baru harus berbeda dari password saat ini."}), 400
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, password, password_hash FROM public.users WHERE username=%s FOR UPDATE",
                            (session["username"],))
                row = cur.fetchone()
                if not row:
                    session.clear()
                    return jsonify({"success": False, "message": "Akun tidak ditemukan."}), 401
                stored_hash = row.get("password_hash")
                valid = check_password_hash(stored_hash, current_password) if stored_hash else hmac.compare_digest(str(row.get("password") or ""), current_password)
                if not valid:
                    return jsonify({"success": False, "message": "Password saat ini salah."}), 400
                cur.execute("UPDATE public.users SET password_hash=%s, password=NULL, password_must_change=FALSE, password_changed_at=NOW() WHERE id=%s",
                            (generate_password_hash(new_password), row["id"]))
            conn.commit()
        session["password_must_change"] = False
        return jsonify({"success": True, "message": "Password berhasil diperbarui.",
                        "redirect_url": url_for(preferred_landing_endpoint(session.get("role")))}), 200
    except psycopg2.Error:
        app.logger.exception("Password update failed")
        return jsonify({"success": False, "message": "Gagal memperbarui password. Coba lagi."}), 500

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Berhasil logout"})

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    target = request.args.get("username")
    if not target: 
        return jsonify({"success": False, "message": "Target user diperlukan"}), 400
    
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                if target == "admin":
                    cursor.execute("SELECT id, name, target_rfs FROM projects WHERE status = 'ongoing' AND target_rfs IS NOT NULL AND target_rfs != ''")
                    for p in cursor.fetchall():
                        try:
                            rfs_date = datetime.strptime(p["target_rfs"], "%Y-%m-%d").date()
                            days_left = (rfs_date - datetime.now().date()).days
                            msg = ""
                            if days_left < 0: 
                                msg = f"🚨 OVERDUE: Project '{p['name']}' telah melewati batas Target RFS!"
                            elif days_left <= 14: 
                                msg = f"⚠️ AT RISK: Project '{p['name']}' tersisa {days_left} hari menuju RFS."
                            
                            if msg:
                                cursor.execute("SELECT COUNT(*) FROM notifications WHERE target_user = 'admin' AND message = %s AND date(created_at) = CURRENT_DATE", (msg,))
                                if cursor.fetchone()["count"] == 0:
                                    cursor.execute("INSERT INTO notifications (target_user, message) VALUES ('admin', %s)", (msg,))
                        except Exception: 
                            pass
                conn.commit()
                
                cursor.execute("SELECT * FROM notifications WHERE target_user = %s OR target_user = 'broadcast' ORDER BY created_at DESC LIMIT 20", (target,))
                return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]}), 200
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def mark_notification_read(notif_id):
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("UPDATE notifications SET is_read = 1 WHERE id = %s", (notif_id,))
            conn.commit()
    return jsonify({"success": True})

# ============================================================================
# REQUESTS
# ============================================================================
@app.route("/api/requests", methods=["POST"])
def create_request():
    payload = request.json or {}
    ticket_id = f"REQ-{datetime.now().strftime('%y%m')}-{uuid.uuid4().hex[:4].upper()}"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("INSERT INTO requests (ticket_id, title, client_name, competitor_info, sla_date, notes, requester_username, status) VALUES (%s, %s, %s, %s, %s, %s, %s, 'unassigned')", (ticket_id, payload.get("title"), payload.get("client_name"), payload.get("competitor_info"), payload.get("sla_date"), payload.get("notes"), payload.get("requester_username")))
                cursor.execute("INSERT INTO notifications (target_user, message) VALUES ('admin', %s)", (f"Request Baru: {ticket_id} dari @{payload.get('requester_username')}",))
                conn.commit()
                return jsonify({"success": True, "message": "Request berhasil dibuat", "ticket_id": ticket_id}), 201
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/requests", methods=["GET"])
def get_requests():
    username, role = request.args.get("username"), request.args.get("role")
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                query = "SELECT r.*, u.full_name, u.department, p.pipeline_stage, p.progress_pct, p.target_rfs FROM requests r LEFT JOIN users u ON r.requester_username = u.username LEFT JOIN projects p ON r.ticket_id = p.id"
                
                if role not in MS_ADMIN_ROLES:
                    cursor.execute(query + " WHERE r.requester_username = %s ORDER BY r.created_at DESC", (username,))
                else:
                    cursor.execute(query + " ORDER BY r.created_at DESC")
                return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]})
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/upload_boq", methods=["POST"])
def upload_boq():
    ticket_id = request.form.get("ticket_id")
    if not ticket_id or "file" not in request.files: 
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    
    file = request.files["file"]
    if not file.filename: 
        return jsonify({"success": False, "message": "Nama file tidak valid."}), 400
    
    try:
        df = _read_boq_excel(file, require_system_id=False)
        rows, issues = _parse_boq_rows(df)
        for item in rows:
            if item["id"]: 
                issues.append({"row": item["excelRow"], "severity": "error", "message": f"'{BOQ_SYSTEM_COLUMN}' harus kosong untuk Initial Request."})
        
        errors = [x for x in issues if x["severity"] == "error"]
        if errors: 
            with get_db_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("DELETE FROM requests WHERE ticket_id = %s", (ticket_id,))
                    conn.commit()
            return jsonify({"success": False, "message": "Excel memiliki error. Perbaiki file terlebih dahulu.", "issues": issues[:50]}), 400

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM request_items WHERE ticket_id = %s", (ticket_id,))
                
                # OPTIMASI: Bulk Insert untuk request_items
                items_data = [
                    (ticket_id, item["sowName"], item["boqName"], item["itemNo"], item["product"], item["preferredBrand"], item["qty"], item["uom"], item["deliveryTime"], item["vendor"] or None, item["sphAwalUnit"], item["sphFinalUnit"])
                    for item in rows
                ]
                if items_data:
                    execute_values(cursor, "INSERT INTO request_items (ticket_id, sow_name, boq_section, item_no, description, preferred_brand, quantity, uom, delivery_time, vendor, sph_awal_unit, sph_final_unit) VALUES %s", items_data)
                conn.commit()
            
        return jsonify({"success": True, "message": "File BoQ berhasil diunggah.", "summary": {"items": len(rows), "warnings": sum(1 for x in issues if x["severity"] == "warning")}}), 200
        
    except Exception as e: 
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM requests WHERE ticket_id = %s", (ticket_id,))
                conn.commit()
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/request_items/<ticket_id>", methods=["GET"])
def get_request_items(ticket_id):
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT * FROM request_items WHERE ticket_id = %s", (ticket_id,))
            return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]}), 200

@app.route("/api/requests/assign", methods=["POST"])
def assign_ticket():
    payload = request.json or {}
    ticket_id, pic_username = payload.get("ticket_id"), payload.get("pic_username")
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("UPDATE requests SET pic_username = %s, status = 'ongoing' WHERE ticket_id = %s", (pic_username, ticket_id))
                cursor.execute("SELECT r.*, u.full_name, u.department FROM requests r LEFT JOIN users u ON r.requester_username = u.username WHERE r.ticket_id = %s", (ticket_id,))
                req = cursor.fetchone()
                
                if req:
                    cursor.execute("SELECT COUNT(*) FROM projects WHERE id = %s", (ticket_id,))
                    if cursor.fetchone()["count"] == 0:
                        created_at_val = str(req["created_at"])[:10] if req["created_at"] else datetime.now().strftime("%Y-%m-%d")
                        target_rfs_val = req["sla_date"] if req["sla_date"] else ""
                        title_val = f"{req['title']} ({req['client_name'] or 'Klien Umum'})"
                        req_name_val = req["full_name"] or req["requester_username"]
                        req_dept_val = req["department"] or "Presales Team"

                        cursor.execute(
                            "INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, created_at, target_rfs, pipeline_stage, progress_pct) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                            (ticket_id, title_val, req_name_val, req_dept_val, "High", "ongoing", pic_username, "item", created_at_val, target_rfs_val, "1 - Project Identification", 0)
                        )
                        
                        cursor.execute("SELECT * FROM request_items WHERE ticket_id = %s", (ticket_id,))
                        grouped_data = {}
                        for it in cursor.fetchall():
                            grouped_data.setdefault(it["sow_name"] or "General Scope of Work", {}).setdefault(it["boq_section"] or "General Items", []).append(it)
                        
                        # OPTIMASI: Bulk Insert untuk proses Assign
                        sows_data, boqs_data, items_data = [], [], []
                        for s_name, boqs in grouped_data.items():
                            sow_id = f"sow_{uuid.uuid4().hex[:8]}"
                            sows_data.append((sow_id, ticket_id, s_name))
                            for b_name, items_list in boqs.items():
                                boq_id = f"boq_{uuid.uuid4().hex[:8]}"
                                boqs_data.append((boq_id, sow_id, b_name))
                                for it in items_list:
                                    items_data.append((
                                        f"item_{uuid.uuid4().hex[:8]}", boq_id, it["description"], it["quantity"], it["uom"], 
                                        it["vendor"] or "", calculate_sph_total(it["quantity"], it["sph_awal_unit"]), 
                                        calculate_sph_total(it["quantity"], it["sph_final_unit"]), "", json.dumps([pic_username]), 
                                        it["item_no"] or "", it["preferred_brand"] or "", it["delivery_time"] or "", 
                                        it["sph_awal_unit"], it["sph_final_unit"]
                                    ))
                        
                        if sows_data: execute_values(cursor, "INSERT INTO sows (id, project_id, name) VALUES %s", sows_data)
                        if boqs_data: execute_values(cursor, "INSERT INTO boqs (id, sow_id, name) VALUES %s", boqs_data)
                        if items_data: execute_values(cursor, "INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time, sph_awal_unit, sph_final_unit) VALUES %s", items_data)
                        
                        cursor.execute("INSERT INTO notifications (target_user, message) VALUES (%s, %s)", (req["requester_username"], f"Tiket {ticket_id} sudah di-assign ke PIC: {pic_username}"))
                conn.commit()
        return jsonify({"success": True, "message": "Tiket berhasil di-assign!"}), 200
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# PRESOURCING API (TEROPTIMASI: BULK INSERT / BATCH EXECUTION)
# ============================================================================
@app.route("/api/presourcing", methods=["GET", "POST"])
def api_presourcing():
    if request.method == "GET":
        try:
            with get_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'team'")
                    team_row = cursor.fetchone()
                    team_data = json.loads(team_row["json_data"]) if team_row and team_row["json_data"] else []
                    return jsonify({"projects": get_projects_relational(cursor), "team": team_data}), 200
        except Exception as e: 
            return jsonify({"error": str(e)}), 500

    data = request.json or {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                # 1. Simpan konfigurasi Tim (Upsert 1 Baris)
                cursor.execute("INSERT INTO dashboard_state (data_type, json_data) VALUES ('team', %s) ON CONFLICT (data_type) DO UPDATE SET json_data = EXCLUDED.json_data", (json.dumps(data.get("team", [])),))

                incoming_projects = data.get("projects", [])
                
                # 2. Persiapan Data Hapus Massal (Bulk Delete)
                cursor.execute("SELECT id FROM projects")
                existing_db_ids = {row[0] for row in cursor.fetchall()}
                incoming_ids = {p["id"] for p in incoming_projects}
                
                del_ids = tuple(existing_db_ids - incoming_ids)
                if del_ids:
                    # Menghapus parent project otomatis menghapus SOW, BoQ, dll via ON DELETE CASCADE PostgreSQL
                    cursor.execute("DELETE FROM projects WHERE id IN %s", (del_ids,))
                    cursor.execute("DELETE FROM request_items WHERE ticket_id IN %s", (del_ids,))
                    cursor.execute("DELETE FROM requests WHERE ticket_id IN %s", (del_ids,))

                # Hapus project yang diupdate untuk ditimpa ulang (bersih)
                incoming_tuple = tuple(incoming_ids)
                if incoming_tuple:
                    cursor.execute("DELETE FROM projects WHERE id IN %s", (incoming_tuple,))

                # 3. Penyusunan Array untuk Bulk Insert
                projects_data, sows_data, boqs_data, items_data, docs_data = [], [], [], [], []
                
                for p in incoming_projects:
                    projects_data.append((
                        p["id"], p.get("name"), p.get("requestorName"), p.get("requestorDept"), 
                        p.get("priority"), p.get("status"), p.get("leadId"), p.get("sphMode"), 
                        p.get("projectSphAwal"), p.get("projectSphFinal"), p.get("createdAt"), 
                        p.get("closedAt"), p.get("targetRfs"), p.get("pipelineStage"), p.get("progressPct")
                    ))

                    for sow in p.get("sows", []):
                        sows_data.append((sow["id"], p["id"], sow.get("name")))
                        for boq in sow.get("boqs", []):
                            boqs_data.append((boq["id"], sow["id"], boq.get("name")))
                            for it in boq.get("items", []):
                                sph_awal_unit, sph_awal_total = resolve_sph_values(it.get("qty"), optional_number(it.get("sphAwalUnit")), it.get("sphAwal"))
                                sph_final_unit, sph_final_total = resolve_sph_values(it.get("qty"), optional_number(it.get("sphFinalUnit")), it.get("sphFinal"))

                                items_data.append((
                                    it["id"], boq["id"], it.get("product"), it.get("qty"), it.get("uom"), it.get("vendor"), 
                                    sph_awal_total, sph_final_total, it.get("notes"), json.dumps(it.get("picIds", [])), 
                                    it.get("itemNo", ""), it.get("preferredBrand", ""), it.get("deliveryTime", ""), 
                                    sph_awal_unit, sph_final_unit
                                ))

                    for doc in p.get("comparison_docs", []):
                        docs_data.append((p["id"], doc.get("vendor_name"), doc.get("offered_price"), doc.get("file_path")))

                # 4. Eksekusi Masif (Hanya 5 Query untuk Seluruh Tabel)
                if projects_data:
                    execute_values(cursor, "INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, project_sph_awal, project_sph_final, created_at, closed_at, target_rfs, pipeline_stage, progress_pct) VALUES %s", projects_data)
                
                if sows_data:
                    execute_values(cursor, "INSERT INTO sows (id, project_id, name) VALUES %s", sows_data)
                
                if boqs_data:
                    execute_values(cursor, "INSERT INTO boqs (id, sow_id, name) VALUES %s", boqs_data)
                
                if items_data:
                    execute_values(cursor, "INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time, sph_awal_unit, sph_final_unit) VALUES %s", items_data)
                
                if docs_data:
                    execute_values(cursor, "INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES %s", docs_data)

                conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e: 
        return jsonify({"error": str(e)}), 500

@app.route("/api/projects/<project_id>/download_boq_template", methods=["GET"])
def download_project_boq_template(project_id):
    if "username" not in session: 
        return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    try:
        template_path = os.path.join(app.static_folder, BOQ_TEMPLATE_FILENAME)
        if not os.path.isfile(template_path): 
            return jsonify({"success": False, "message": "Template BoQ tidak ditemukan."}), 404

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT i.item_no, i.product, i.qty, i.uom, i.preferred_brand, i.delivery_time, i.vendor, i.sph_awal, i.sph_final, i.sph_awal_unit, i.sph_final_unit, i.id AS item_id, s.name AS sow_name, b.name AS boq_name FROM items i JOIN boqs b ON i.boq_id = b.id JOIN sows s ON b.sow_id = s.id WHERE s.project_id = %s ORDER BY s.name, b.name, i.item_no", (project_id,))
                items = [dict(row) for row in cursor.fetchall()]

        wb = load_workbook(template_path)
        ws = wb["BoQ Request"]
        
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=14):
            for cell in row: 
                if not isinstance(cell, MergedCell):
                    cell.value = None

        style_row = min(51, ws.max_row)

        for excel_row, item in enumerate(items, start=2):
            awal_unit = item.get("sph_awal_unit") if item.get("sph_awal_unit") is not None else derive_unit_price(item.get("qty"), item.get("sph_awal"))
            final_unit = item.get("sph_final_unit") if item.get("sph_final_unit") is not None else derive_unit_price(item.get("qty"), item.get("sph_final"))

            values = {
                1: item.get("item_no", ""), 2: item.get("product", ""), 3: item.get("qty", 0), 4: item.get("uom", ""), 
                5: item.get("preferred_brand", ""), 6: item.get("delivery_time", ""), 7: item.get("sow_name", ""), 
                8: item.get("boq_name", ""), 9: item.get("vendor", ""), 10: awal_unit, 12: final_unit, 14: item.get("item_id", "")
            }

            if excel_row > style_row:
                for col in range(1, 15):
                    source, target = ws.cell(style_row, col), ws.cell(excel_row, col)
                    if not isinstance(source, MergedCell) and not isinstance(target, MergedCell):
                        if source.has_style: 
                            target._style = copy(source._style)
                        target.number_format = source.number_format

            for col, value in values.items():
                cell = ws.cell(excel_row, col)
                if not isinstance(cell, MergedCell):
                    if col == 6 and value:
                        try:
                            cell.value = datetime.strptime(str(value), "%Y-%m-%d").date()
                            cell.number_format = "yyyy-mm-dd"
                        except ValueError: 
                            cell.value = value
                    else: 
                        cell.value = value

            formula_cell_k = ws.cell(excel_row, 11)
            formula_cell_m = ws.cell(excel_row, 13)
            if not isinstance(formula_cell_k, MergedCell):
                formula_cell_k.value = f'=IF(OR(C{excel_row}="",J{excel_row}=""),"",C{excel_row}*J{excel_row})'
            if not isinstance(formula_cell_m, MergedCell):
                formula_cell_m.value = f'=IF(OR(C{excel_row}="",L{excel_row}=""),"",C{excel_row}*L{excel_row})'

        if "BoQInputTable" in ws.tables: 
            ws.tables["BoQInputTable"].ref = f"A1:N{max(2, len(items) + 1)}"

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"BoQ_Revisi_{project_id}.xlsx")
    
    except Exception as e: 
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    if "username" not in session: 
        return jsonify({"success": False, "message": "Akses ditolak! Silakan login."}), 403
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM projects WHERE id = %s", (project_id,))
                cursor.execute("DELETE FROM request_items WHERE ticket_id = %s", (project_id,))
                cursor.execute("DELETE FROM requests WHERE ticket_id = %s", (project_id,))
                if cursor.rowcount > 0:
                    conn.commit()
                    return jsonify({"success": True, "message": "Project berhasil dihapus dari database!"}), 200
                return jsonify({"success": False, "message": "Project tidak ditemukan atau sudah terhapus."}), 404
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# PROJECT REPORT
# ============================================================================
@app.route("/api/download_report", methods=["GET"])
def download_report():
    if 'username' not in session or not has_ms_access(session.get('role')):
        return jsonify({"success": False, "message": "Akses ditolak!"}), 403

    target_project_id = str(request.args.get("project_id") or "").strip()
    if not target_project_id:
        return jsonify({"success": False, "message": "Project ID wajib diberikan."}), 400

    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                projects = get_projects_relational(cursor)

        project = next((p for p in projects if str(p.get("id") or "") == target_project_id), None)
        if project is None:
            return jsonify({"success": False, "message": "Project tidak ditemukan."}), 404

        items = []
        for sow in project.get("sows") or []:
            for boq in sow.get("boqs") or []:
                for item in boq.get("items") or []:
                    items.append({"sow": sow.get("name", ""), "boq": boq.get("name", ""), **item})

        sph_mode = project.get("sphMode") or "item"
        if sph_mode == "project":
            total_sph_awal = project.get("projectSphAwal")
            total_sph_final = project.get("projectSphFinal")
        else:
            total_sph_awal = 0
            total_sph_final = 0
            has_awal = False
            has_final = True

            for item in items:
                awal = item.get("sphAwal")
                final = item.get("sphFinal")

                if awal is not None:
                    total_sph_awal += float(awal)
                    has_awal = True

                if final is None:
                    has_final = False
                else:
                    total_sph_final += float(final)

            total_sph_awal = total_sph_awal if has_awal else None
            total_sph_final = total_sph_final if has_final and items else None

        efficiency = None
        if total_sph_awal is not None and total_sph_final is not None and float(total_sph_awal) > 0:
            efficiency = (float(total_sph_awal) - float(total_sph_final)) / float(total_sph_awal)

        total_qty = sum(float(item.get("qty") or 0) for item in items)
        vendors = sorted({str(item.get("vendor") or "").strip() for item in items if str(item.get("vendor") or "").strip()})
        pics = sorted({str(pic).strip() for item in items for pic in (item.get("picIds") or []) if str(pic).strip()})
        lead_id = project.get("leadId") or ""

        if lead_id and lead_id not in pics:
            pics.insert(0, lead_id)

        wb = Workbook()
        ws = wb.active
        ws.title = "Project Summary"
        detail_ws = wb.create_sheet("BoQ Detail")

        title_fill = PatternFill("solid", fgColor="1F4E78")
        section_fill = PatternFill("solid", fgColor="D9EAF7")
        header_fill = PatternFill("solid", fgColor="5B9BD5")
        white_font = Font(color="FFFFFF", bold=True, size=14)
        section_font = Font(bold=True, size=11)
        header_font = Font(color="FFFFFF", bold=True)
        normal_font = Font(size=10)
        thin_side = Side(style="thin", color="D9E1F2")
        border = Border(left=thin_side, right=thin_side, top=thin_side, bottom=thin_side)
        currency_format = '"Rp" #,##0;"-Rp" #,##0;-'
        number_format = '#,##0.##'
        percent_format = '0.0%;-0.0%;-'

        ws.merge_cells("A1:F1")
        ws["A1"] = "PROJECT REPORT"
        ws["A1"].fill = title_fill
        ws["A1"].font = white_font
        ws["A1"].alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 26

        ws.merge_cells("A2:F2")
        ws["A2"] = project.get("name") or "-"
        ws["A2"].font = Font(bold=True, size=13)
        ws["A2"].alignment = Alignment(vertical="center")

        ws.merge_cells("A4:F4")
        ws["A4"] = "PROJECT INFORMATION"
        ws["A4"].fill = section_fill
        ws["A4"].font = section_font

        project_info = [
            ("Ticket ID", project.get("id")), ("Requestor / SA", project.get("requestorName")),
            ("Department", project.get("requestorDept")), ("PIC / Lead Presource", project.get("leadId")),
            ("Outcome", project.get("status")), ("Pipeline Stage", project.get("pipelineStage")),
            ("Progress", project.get("progressPct")), ("Target RFS", project.get("targetRfs")),
            ("Created Date", project.get("createdAt")), ("Priority", project.get("priority")),
        ]

        row = 5
        for label, value in project_info:
            ws.cell(row=row, column=1).value = label
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.cell(row=row, column=2).value = value if value not in (None, "") else "-"
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
            if label == "Progress" and value is not None:
                ws.cell(row=row, column=2).value = float(value) / 100
                ws.cell(row=row, column=2).number_format = "0%"
            row += 1

        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws.cell(row=row, column=1).value = "COMMERCIAL SUMMARY"
        ws.cell(row=row, column=1).fill = section_fill
        ws.cell(row=row, column=1).font = section_font

        row += 1
        commercial = [
            ("Total Item", len(items), None), ("Total Qty", total_qty, number_format),
            ("Total SPH Awal", total_sph_awal, currency_format), ("Total SPH Final", total_sph_final, currency_format),
            ("Efficiency", efficiency, percent_format), ("Vendor", ", ".join(vendors) if vendors else "-", None),
            ("PIC Terlibat", ", ".join(pics) if pics else "-", None),
        ]

        for label, value, fmt in commercial:
            ws.cell(row=row, column=1).value = label
            ws.cell(row=row, column=1).font = Font(bold=True)
            ws.merge_cells(start_row=row, start_column=2, end_row=row, end_column=6)
            ws.cell(row=row, column=2).value = value if value not in (None, "") else "-"
            if fmt and value is not None:
                ws.cell(row=row, column=2).number_format = fmt
            row += 1

        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=6)
        ws.cell(row=row, column=1).value = "REPORT SCOPE"
        ws.cell(row=row, column=1).fill = section_fill
        ws.cell(row=row, column=1).font = section_font
        row += 1
        ws.merge_cells(start_row=row, start_column=1, end_row=row + 1, end_column=6)
        ws.cell(row=row, column=1).value = "Report ini berisi informasi project dan detail BoQ berdasarkan data Presourcing saat report dibuat."
        ws.cell(row=row, column=1).alignment = Alignment(wrap_text=True, vertical="top")

        detail_headers = [
            "SoW", "BoQ", "Item No", "Item ID", "Description", "Qty", "UoM", "Preferred Brand", 
            "Delivery Time (RFS)", "Vendor", "SPH Awal / Unit", "Total SPH Awal", "SPH Final / Unit", 
            "Total SPH Final", "Efficiency", "PIC"
        ]

        for col_idx, header in enumerate(detail_headers, start=1):
            cell = detail_ws.cell(row=1, column=col_idx, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            cell.border = border

        for row_idx, item in enumerate(items, start=2):
            awal_unit, awal_total = item.get("sphAwalUnit"), item.get("sphAwal")
            final_unit, final_total = item.get("sphFinalUnit"), item.get("sphFinal")
            item_efficiency = None
            if awal_total is not None and final_total is not None and float(awal_total) > 0:
                item_efficiency = (float(awal_total) - float(final_total)) / float(awal_total)

            row_values = [
                item.get("sow") or "-", item.get("boq") or "-", item.get("itemNo") or "-", item.get("id") or "-", 
                item.get("product") or "-", item.get("qty") if item.get("qty") is not None else "-", item.get("uom") or "-", 
                item.get("preferredBrand") or "-", item.get("deliveryTime") or "-", item.get("vendor") or "-", 
                awal_unit, awal_total, final_unit, final_total, item_efficiency, ", ".join(item.get("picIds") or []) or lead_id or "-"
            ]

            for col_idx, value in enumerate(row_values, start=1):
                cell = detail_ws.cell(row=row_idx, column=col_idx, value=value)
                cell.border = border
                cell.font = normal_font
                cell.alignment = Alignment(vertical="top", wrap_text=True)

            detail_ws.cell(row=row_idx, column=6).number_format = number_format
            for col_idx in (11, 12, 13, 14):
                detail_ws.cell(row=row_idx, column=col_idx).number_format = currency_format
            detail_ws.cell(row=row_idx, column=15).number_format = percent_format

        detail_ws.freeze_panes = "A2"
        detail_ws.auto_filter.ref = detail_ws.dimensions
        detail_ws.row_dimensions[1].height = 30

        detail_widths = {"A": 22, "B": 24, "C": 12, "D": 22, "E": 34, "F": 10, "G": 10, "H": 22, "I": 20, "J": 25, "K": 20, "L": 20, "M": 20, "N": 20, "O": 14, "P": 24}
        for column, width in detail_widths.items(): detail_ws.column_dimensions[column].width = width

        summary_widths = {"A": 25, "B": 24, "C": 18, "D": 18, "E": 18, "F": 18}
        for column, width in summary_widths.items(): ws.column_dimensions[column].width = width
        ws.freeze_panes = "A5"

        for row_cells in ws.iter_rows(min_row=5, max_row=ws.max_row, min_col=1, max_col=6):
            for cell in row_cells: cell.border = border

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        safe_project_id = target_project_id.replace("/", "_").replace("\\", "_").replace(" ", "_")

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"Project_Report_{safe_project_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )

    except Exception as exc:
        return jsonify(str(exc), 500)

@app.route("/api/project_import_boq/preview", methods=["POST"])
def preview_project_import_boq():
    if "file" not in request.files: 
        return jsonify({"success": False, "message": "File Excel tidak ditemukan."}), 400
    
    file = request.files["file"]
    if not file.filename: 
        return jsonify({"success": False, "message": "Nama file tidak valid."}), 400
    
    try:
        df = _read_boq_excel(file, require_system_id=False)
        rows, issues = _parse_boq_rows(df)
        
        for item in rows:
            if item["id"]: 
                issues.append({"row": item["excelRow"], "severity": "error", "message": f"'{BOQ_SYSTEM_COLUMN}' harus kosong untuk Project Baru."})

        sows = {}
        for item in rows:
            sows.setdefault(item["sowName"], {}).setdefault(item["boqName"], []).append({
                "id": f"item_{uuid.uuid4().hex[:8]}", 
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
                "sphAwal": calculate_sph_total(item["qty"], item["sphAwalUnit"]), 
                "sphFinal": calculate_sph_total(item["qty"], item["sphFinalUnit"]),
            })

        result_sows = [
            {
                "id": f"sow_{uuid.uuid4().hex[:8]}", 
                "name": s_name, 
                "boqs": [
                    {
                        "id": f"boq_{uuid.uuid4().hex[:8]}", 
                        "name": b_name, 
                        "items": items
                    } for b_name, items in boq_groups.items()
                ]
            } for s_name, boq_groups in sows.items()
        ]

        errors = sum(1 for x in issues if x["severity"] == "error")
        warnings = sum(1 for x in issues if x["severity"] == "warning")
        total_boqs = sum(len(s["boqs"]) for s in result_sows)
        total_items = sum(len(b["items"]) for s in result_sows for b in s["boqs"])

        return jsonify({
            "success": True, 
            "data": {
                "summary": {
                    "rows": len(df), "items": total_items, "sows": len(result_sows), 
                    "boqs": total_boqs, "errors": errors, "warnings": warnings
                }, 
                "issues": issues[:50], 
                "has_errors": errors > 0, 
                "sows": result_sows
            }
        }), 200
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 400

def _revision_items_for_project(cursor, ticket_id):
    cursor.execute("SELECT i.*, b.name AS boq_name, s.name AS sow_name FROM items i JOIN boqs b ON i.boq_id = b.id JOIN sows s ON b.sow_id = s.id WHERE s.project_id = %s", (ticket_id,))
    return [dict(row) for row in cursor.fetchall()]

@app.route("/api/revisi_boq/preview", methods=["POST"])
def preview_revisi_boq():
    ticket_id = request.form.get("ticket_id")
    if "file" not in request.files or not ticket_id: 
        return jsonify({"success": False, "message": "Data tidak valid."}), 400
    
    try:
        df = _read_boq_excel(request.files["file"], require_system_id=True)
        incoming, issues = _parse_boq_rows(df)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id FROM projects WHERE id = %s", (ticket_id,))
                if not cursor.fetchone(): 
                    return jsonify({"success": False, "message": "Project tidak ditemukan."}), 404
                
                existing_rows = _revision_items_for_project(cursor, ticket_id)

        existing = {str(row["id"]).strip(): row for row in existing_rows if row["id"]}
        incoming_ids = {item["id"] for item in incoming if item["id"]}

        for item in incoming:
            if item["id"] and item["id"] not in existing:
                issues.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID '{item['id']}' tidak ditemukan di project."})

        added, updated, unchanged = [], [], []

        def norm(value, is_number=False):
            if is_number:
                if value is None or value == "": 
                    return None
                try: 
                    return float(value)
                except (TypeError, ValueError): 
                    return None
            return _excel_text(value).lower()

        for item in incoming:
            if not item["id"]:
                added.append({"description": item["product"], "qty": item["qty"], "uom": item["uom"], "vendor": item["vendor"], "sphAwalUnit": item["sphAwalUnit"], "sphFinalUnit": item["sphFinalUnit"]})
                continue

            old = existing.get(item["id"])
            if not old: 
                continue

            changes = {}
            comparisons = [
                ("Item No", old.get("item_no"), item["itemNo"], False), 
                ("Deskripsi Item", old.get("product"), item["product"], False), 
                ("Qty", old.get("qty"), item["qty"], True), 
                ("UoM", old.get("uom"), item["uom"], False), 
                ("Preferred Brand", old.get("preferred_brand"), item["preferredBrand"], False), 
                ("Delivery Time (RFS)", old.get("delivery_time"), item["deliveryTime"], False), 
                ("Scope of Work", old.get("sow_name"), item["sowName"], False), 
                ("Bill of Quantity", old.get("boq_name"), item["boqName"], False), 
                ("Vendor", old.get("vendor"), item["vendor"], False), 
                ("SPH Awal / Unit", old.get("sph_awal_unit"), item["sphAwalUnit"], True), 
                ("SPH Final / Unit", old.get("sph_final_unit"), item["sphFinalUnit"], True),
            ]

            for (label, old_value, new_value, is_number) in comparisons:
                if norm(old_value, is_number) != norm(new_value, is_number): 
                    changes[label] = [_excel_text(old_value), _excel_text(new_value)]

            if changes: 
                updated.append({"id": item["id"], "description": item["product"], "qty": item["qty"], "uom": item["uom"], "vendor": item["vendor"], "changes": changes})
            else: 
                unchanged.append({"id": item["id"], "description": item["product"]})

        removed = [{"id": row["id"], "description": row["product"], "itemNo": row.get("item_no", "")} for item_id, row in existing.items() if item_id not in incoming_ids]
        errors = sum(1 for x in issues if x["severity"] == "error")
        warnings = sum(1 for x in issues if x["severity"] == "warning")

        return jsonify({
            "success": True, 
            "data": {
                "summary": {
                    "added": len(added), "updated": len(updated), "removed": len(removed), 
                    "unchanged": len(unchanged), "errors": errors, "warnings": warnings
                }, 
                "issues": issues[:50], 
                "has_errors": errors > 0, 
                "added": added, "updated": updated, "removed": removed, "unchanged": unchanged
            }
        }), 200
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/revisi_boq", methods=["POST"])
def revisi_boq():
    ticket_id = request.form.get("ticket_id")
    if "file" not in request.files or not ticket_id: 
        return jsonify({"success": False, "message": "Data tidak valid."}), 400
    
    try:
        df = _read_boq_excel(request.files["file"], require_system_id=True)
        incoming, issues = _parse_boq_rows(df)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT id FROM projects WHERE id = %s", (ticket_id,))
                if not cursor.fetchone(): 
                    return jsonify({"success": False, "message": "Project tidak ditemukan."}), 404

                existing = {str(row["id"]).strip(): row for row in _revision_items_for_project(cursor, ticket_id) if row["id"]}
                validation_errors = list(issues)
                seen_ids = set()

                for item in incoming:
                    item_id = item["id"]
                    if not item_id: 
                        continue
                    if item_id in seen_ids: 
                        validation_errors.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID duplikat: {item_id}."})
                    seen_ids.add(item_id)
                    if item_id not in existing: 
                        validation_errors.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID '{item_id}' tidak ditemukan di project."})

                if any(x["severity"] == "error" for x in validation_errors):
                    return jsonify({"success": False, "message": "Excel revisi memiliki error. Perbaiki file lalu upload kembali.", "issues": validation_errors[:50]}), 400

                sow_map, boq_map = {}, {}
                cursor.execute("SELECT id, name FROM sows WHERE project_id = %s", (ticket_id,))
                for s_row in cursor.fetchall():
                    sow_map[s_row["name"]] = s_row["id"]
                    cursor.execute("SELECT id, name FROM boqs WHERE sow_id = %s", (s_row["id"],))
                    for b_row in cursor.fetchall(): 
                        boq_map[(s_row["name"], b_row["name"])] = b_row["id"]

                incoming_existing_ids = set()

                for item in incoming:
                    s_name, b_name = item["sowName"], item["boqName"]
                    if s_name not in sow_map:
                        sow_id = f"sow_{uuid.uuid4().hex[:8]}"
                        cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (%s, %s, %s)", (sow_id, ticket_id, s_name))
                        sow_map[s_name] = sow_id
                    
                    sow_id = sow_map[s_name]

                    boq_key = (s_name, b_name)
                    if boq_key not in boq_map:
                        boq_id = f"boq_{uuid.uuid4().hex[:8]}"
                        cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (%s, %s, %s)", (boq_id, sow_id, b_name))
                        boq_map[boq_key] = boq_id
                    
                    boq_id = boq_map[boq_key]

                    item_id = item["id"]
                    old = existing[item_id] if item_id else None

                    if old is not None:
                        sph_awal_unit, sph_awal_total = resolve_sph_values(item["qty"], item["sphAwalUnit"], old["sph_awal"])
                        sph_final_unit, sph_final_total = resolve_sph_values(item["qty"], item["sphFinalUnit"], old["sph_final"])
                    else:
                        sph_awal_unit, sph_final_unit = item["sphAwalUnit"], item["sphFinalUnit"]
                        sph_awal_total = calculate_sph_total(item["qty"], sph_awal_unit)
                        sph_final_total = calculate_sph_total(item["qty"], sph_final_unit)

                    if item_id:
                        incoming_existing_ids.add(item_id)
                        cursor.execute(
                            "UPDATE items SET boq_id = %s, product = %s, qty = %s, uom = %s, vendor = %s, item_no = %s, preferred_brand = %s, delivery_time = %s, sph_awal = %s, sph_final = %s, sph_awal_unit = %s, sph_final_unit = %s WHERE id = %s", 
                            (boq_id, item["product"], item["qty"], item["uom"], item["vendor"], item["itemNo"], item["preferredBrand"], item["deliveryTime"], sph_awal_total, sph_final_total, sph_awal_unit, sph_final_unit, old["id"])
                        )
                    else:
                        cursor.execute(
                            "INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time, sph_awal_unit, sph_final_unit) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)", 
                            (f"item_{uuid.uuid4().hex[:8]}", boq_id, item["product"], item["qty"], item["uom"], item["vendor"], sph_awal_total, sph_final_total, "", "[]", item["itemNo"], item["preferredBrand"], item["deliveryTime"], sph_awal_unit, sph_final_unit)
                        )

                for item_id in (set(existing) - incoming_existing_ids):
                    cursor.execute("DELETE FROM items WHERE id = %s", (item_id,))

                cursor.execute("DELETE FROM boqs WHERE id NOT IN (SELECT DISTINCT boq_id FROM items)")
                cursor.execute("DELETE FROM sows WHERE id NOT IN (SELECT DISTINCT sow_id FROM boqs)")
                conn.commit()

        return jsonify({"success": True, "message": "BoQ berhasil direvisi!"}), 200
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/download_template_boq", methods=["GET"])
def download_template_boq():
    if "username" not in session: 
        return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    
    path = os.path.join(app.static_folder, BOQ_TEMPLATE_FILENAME)
    if not os.path.isfile(path): 
        return jsonify({"success": False, "message": f"Template '{BOQ_TEMPLATE_FILENAME}' belum tersedia di folder static."}), 404
    
    return send_from_directory(app.static_folder, BOQ_TEMPLATE_FILENAME, as_attachment=True, download_name=BOQ_TEMPLATE_FILENAME)

@app.route("/api/upload_comparison", methods=["POST"])
def upload_comparison():
    ticket_id = request.form.get("ticket_id")
    vendor_name = request.form.get("vendor_name")
    offered_price = request.form.get("offered_price")
    
    if "file" not in request.files or not ticket_id or not vendor_name or not offered_price: 
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    
    file = request.files["file"]
    if file.filename == "": 
        return jsonify({"success": False, "message": "File tidak valid"}), 400
    
    try:
        save_dir = os.path.join("secure_data", "comparisons")
        os.makedirs(save_dir, exist_ok=True)
        safe_filename_base = secure_filename(file.filename)
        ext = safe_filename_base.rsplit(".", 1)[1].lower() if "." in safe_filename_base else "bin"
        safe_filename = f"{ticket_id}_{uuid.uuid4().hex[:8]}.{ext}"
        file.save(os.path.join(save_dir, safe_filename))
        web_file_path = f"/api/downloads/comparisons/{safe_filename}"

        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES (%s, %s, %s, %s)", 
                    (ticket_id, str(vendor_name).strip(), float(offered_price), web_file_path)
                )
                conn.commit()
            
        return jsonify({"success": True, "message": "Dokumen pembanding berhasil diunggah"}), 200
    except Exception as e: 
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/downloads/comparisons/<filename>")
def download_comparison(filename):
    if "username" not in session: 
        return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    return send_from_directory(os.path.join(app.root_path, "secure_data", "comparisons"), secure_filename(filename))

# ============================================================================
# LEASING MVP API (isolated from Presourcing M&S routes/tables)
# Apply leasing_mvp_schema.sql to the separate leasing_db database before using these endpoints.
# ============================================================================
from functools import wraps

LEASING_STAGES = {
    "request_received", "requirement_review", "vendor_sourcing",
    "response_monitoring", "commercial_review", "result_submission"
}
LEASING_CASE_STATUSES = {"open", "closed", "cancelled"}
LEASING_REQUIREMENT_STATUSES = {"open", "in_progress", "resolved", "stopped"}


def _leasing_resource_work_item_id(kwargs):
    """Resolve resource URL IDs to a Work Item for centralized buyer-scope enforcement."""
    if kwargs.get("work_item_id") is not None:
        return int(kwargs["work_item_id"])
    lookup = None
    if kwargs.get("requirement_id") is not None:
        lookup = ("SELECT work_item_id FROM leasing.requirements WHERE id=%s", int(kwargs["requirement_id"]))
    elif kwargs.get("outreach_id") is not None:
        lookup = ("SELECT work_item_id FROM leasing.partner_outreaches WHERE id=%s", int(kwargs["outreach_id"]))
    elif kwargs.get("offer_line_id") is not None:
        lookup = ("""SELECT o.work_item_id FROM leasing.partner_offer_lines pol
            JOIN leasing.partner_offers po ON po.id=pol.offer_id
            JOIN leasing.partner_outreaches o ON o.id=po.outreach_id WHERE pol.id=%s""", int(kwargs["offer_line_id"]))
    elif kwargs.get("service_line_id") is not None:
        lookup = ("""SELECT o.work_item_id FROM leasing.partner_offer_service_lines osl
            JOIN leasing.partner_offers po ON po.id=osl.offer_id
            JOIN leasing.partner_outreaches o ON o.id=po.outreach_id WHERE osl.id=%s""", int(kwargs["service_line_id"]))
    if not lookup:
        return None
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(lookup[0], (lookup[1],))
                row = cur.fetchone()
                return int(row[0]) if row else -1
    except psycopg2.Error:
        app.logger.exception("Leasing resource scope lookup failed")
        return -1


def leasing_user_can_access_work_item(work_item_id, username):
    if not username or not work_item_id or work_item_id < 1:
        return False
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""SELECT 1 FROM leasing.work_items w
                    WHERE w.id=%s AND w.archived_at IS NULL AND (
                        w.buyer_owner_id=%s OR EXISTS (
                            SELECT 1 FROM leasing.partner_outreaches o
                            WHERE o.work_item_id=w.id AND o.follow_up_owner_id=%s
                        )
                    ) LIMIT 1""", (work_item_id, username, username))
                return cur.fetchone() is not None
    except psycopg2.Error:
        app.logger.exception("Leasing buyer-scope authorization failed")
        return False


def _is_leasing_admin():
    return session.get("role") in {"leasing_admin", "platform_admin"}


def _leasing_scope_sql(username=None, alias="w"):
    """Return a parametrized SQL condition for visible, non-archived Leasing records."""
    base = f"{alias}.archived_at IS NULL AND "
    if session.get("role") in LEASING_ADMIN_ROLES:
        return base + "TRUE", []
    username = username or session.get("username")
    return (base + f"({alias}.buyer_owner_id=%s OR EXISTS (SELECT 1 FROM leasing.partner_outreaches scope_o "
            f"WHERE scope_o.work_item_id={alias}.id AND scope_o.follow_up_owner_id=%s))",
            [username, username])


def _leasing_query_int(value, default, minimum, maximum):
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _leasing_user_can_access_specific_resource(kwargs, username):
    """Authorize a nested resource against its exact outreach, not any outreach on the same item."""
    if not username:
        return False
    if _is_leasing_admin():
        return True
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor() as cur:
                if kwargs.get("outreach_id") is not None:
                    cur.execute("""SELECT w.buyer_owner_id,o.follow_up_owner_id
                        FROM leasing.partner_outreaches o JOIN leasing.work_items w ON w.id=o.work_item_id
                        WHERE o.id=%s AND w.archived_at IS NULL""", (int(kwargs["outreach_id"]),))
                elif kwargs.get("offer_line_id") is not None:
                    cur.execute("""SELECT w.buyer_owner_id,o.follow_up_owner_id
                        FROM leasing.partner_offer_lines pol
                        JOIN leasing.partner_offers po ON po.id=pol.offer_id
                        JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                        JOIN leasing.work_items w ON w.id=o.work_item_id
                        WHERE pol.id=%s AND w.archived_at IS NULL""", (int(kwargs["offer_line_id"]),))
                elif kwargs.get("service_line_id") is not None:
                    cur.execute("""SELECT w.buyer_owner_id,o.follow_up_owner_id
                        FROM leasing.partner_offer_service_lines osl
                        JOIN leasing.partner_offers po ON po.id=osl.offer_id
                        JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                        JOIN leasing.work_items w ON w.id=o.work_item_id
                        WHERE osl.id=%s AND w.archived_at IS NULL""", (int(kwargs["service_line_id"]),))
                else:
                    resource_id = _leasing_resource_work_item_id(kwargs)
                    if resource_id is None:
                        return True
                    cur.execute("""SELECT w.buyer_owner_id,NULL::TEXT AS follow_up_owner_id
                        FROM leasing.work_items w WHERE w.id=%s AND w.archived_at IS NULL""", (int(resource_id),))
                row = cur.fetchone()
                if not row:
                    return False
                owner, pic = row[0], row[1]
                return owner == username or pic == username
    except psycopg2.Error:
        app.logger.exception("Leasing resource-specific authorization failed")
        return False


def _leasing_user_is_work_item_owner_or_admin(work_item_id, username=None):
    """Mutation permission for active Work Items; follow-up PIC is read-only there."""
    username = username or session.get("username")
    if not work_item_id or not username:
        return False
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT buyer_owner_id FROM leasing.work_items WHERE id=%s AND archived_at IS NULL", (int(work_item_id),))
                row = cur.fetchone()
                return bool(row and (_is_leasing_admin() or row[0] == username))
    except psycopg2.Error:
        app.logger.exception("Leasing Work Item mutation authorization failed")
        return False


def _leasing_owner_mutation_denied():
    return jsonify({"success": False, "message": "Hanya owner Work Item atau admin Leasing yang boleh mengubah data site, target komersial, hasil, dan metadata Work Item. PIC follow-up hanya dapat memperbarui outreach yang ditugaskan kepadanya."}), 403

def leasing_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            return jsonify({"success": False, "message": "Login diperlukan."}), 401
        if session.get("password_must_change"):
            return jsonify({"success": False, "message": "Ganti password sementara terlebih dahulu.", "redirect_url": url_for("change_password_page")}), 428
        if not has_leasing_access(session.get("role")):
            return jsonify({"success": False, "message": "Akses Leasing hanya untuk Buyer/Admin Leasing."}), 403
        # Resource-level authorization. Buyers may access a Work Item they own or one where
        # they are assigned as a partner follow-up PIC. Admins can access all Work Items.
        if session.get("role") not in LEASING_ADMIN_ROLES:
            resource_id = _leasing_resource_work_item_id(kwargs)
            if resource_id is not None:
                if kwargs.get("outreach_id") is not None or kwargs.get("offer_line_id") is not None or kwargs.get("service_line_id") is not None:
                    allowed = _leasing_user_can_access_specific_resource(kwargs, session.get("username"))
                else:
                    allowed = leasing_user_can_access_work_item(resource_id, session.get("username"))
                if not allowed:
                    return jsonify({"success": False, "message": "Work Item atau resource tidak ditemukan, atau kamu tidak memiliki akses."}), 404
        return fn(*args, **kwargs)
    return wrapper


LEASING_ADMIN_ROLES = frozenset({"leasing_admin", "platform_admin"})


def leasing_admin_required(fn):
    """Restrict destructive/master-data administration to Leasing/platform admins."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            return jsonify({"success": False, "message": "Login diperlukan."}), 401
        if session.get("password_must_change"):
            return jsonify({"success": False, "message": "Ganti password sementara terlebih dahulu.", "redirect_url": url_for("change_password_page")}), 428
        if session.get("role") not in LEASING_ADMIN_ROLES:
            return jsonify({"success": False, "message": "Fitur ini hanya untuk Leasing Admin atau Platform Admin."}), 403
        return fn(*args, **kwargs)
    return wrapper



def leasing_owner_is_valid(username):
    if not username:
        return False
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM public.users WHERE username=%s AND role IN ('buyer','leasing_admin','platform_admin')", (username,))
                return cur.fetchone() is not None
    except psycopg2.Error:
        app.logger.exception("Leasing owner identity validation failed")
        return False

def _leasing_assert_request_id_available(cur, request_id):
    """Serialize concurrent Request ID creation and reject a case-insensitive duplicate."""
    rid = re.sub(r"\s+", " ", str(request_id or "")).strip()
    if not rid:
        raise ValueError("Request ID wajib diisi.")
    if len(rid) > 120:
        raise ValueError("Request ID maksimal 120 karakter.")
    cur.execute("SELECT pg_advisory_xact_lock(hashtext('leasing_request_id:' || LOWER(BTRIM(%s))))", (rid,))
    cur.execute("SELECT id, request_id FROM leasing.work_items WHERE LOWER(BTRIM(request_id))=LOWER(BTRIM(%s)) LIMIT 1", (rid,))
    existing = cur.fetchone()
    if existing:
        existing_id = existing.get("request_id") if isinstance(existing, dict) else existing[1]
        raise ValueError(f"Request ID {existing_id!r} sudah digunakan di Leasing. Gunakan ID yang unik.")
    return rid


def leasing_activity(cursor, work_item_id, event_type, summary, actor, metadata=None):
    cursor.execute(
        "INSERT INTO leasing.activity_events (work_item_id, event_type, event_summary, actor_id, metadata) "
        "VALUES (%s, %s, %s, %s, %s::jsonb)",
        (work_item_id, event_type, summary, actor, json.dumps(metadata or {}))
    )


def _leasing_field_audit(cur, entity_type, entity_id, work_item_id, action, actor, before=None, after=None, reason=None):
    """Append field-level audit data; call inside the same transaction as the mutation."""
    cur.execute("""INSERT INTO leasing.field_audit_events
        (entity_type, entity_id, work_item_id, action, actor_id, reason, before_values, after_values)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
        (entity_type, int(entity_id), int(work_item_id) if work_item_id else None, action, actor,
         reason, json.dumps(before or {}, default=str), json.dumps(after or {}, default=str)))


@app.route("/api/leasing/dashboard", methods=["GET"])
@leasing_login_required
def leasing_dashboard():
    """Small, scoped dashboard payload; large lists are loaded through paginated endpoints."""
    try:
        scope_sql, scope_params = _leasing_scope_sql()
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"""SELECT
                    COUNT(*) FILTER (WHERE w.case_status='open') AS open_cases,
                    COUNT(*) FILTER (WHERE w.case_status='open' AND w.request_due_date < CURRENT_DATE) AS overdue_cases,
                    COUNT(*) FILTER (WHERE w.case_status='open' AND w.request_due_date = CURRENT_DATE) AS due_today,
                    COUNT(*) FILTER (WHERE w.case_status='open' AND w.current_stage='result_submission') AS pending_submission,
                    COUNT(*) AS total_cases,
                    COUNT(*) FILTER (WHERE w.case_status='closed') AS closed_cases,
                    COUNT(*) FILTER (WHERE w.case_status='cancelled') AS cancelled_cases
                    FROM leasing.work_items w WHERE {scope_sql}""", tuple(scope_params))
                summary = dict(cur.fetchone() or {})
                cur.execute(f"""SELECT w.id, w.request_id, w.work_type, w.project_name, c.customer_name,
                    w.requester_name, w.requester_division, w.request_due_date, w.current_stage, w.case_status,
                    w.buyer_owner_id, w.created_at, w.updated_at,
                    COUNT(DISTINCT r.id) AS requirement_count,
                    COUNT(DISTINCT r.id) FILTER (WHERE r.status IN ('resolved','stopped')) AS resolved_count,
                    COUNT(DISTINCT o.id) FILTER (WHERE o.response_status IN ('sent','awaiting_response','partial_response')) AS pending_partner_responses,
                    MIN(o.next_follow_up_at) FILTER (WHERE o.next_follow_up_at IS NOT NULL AND o.response_status IN ('sent','awaiting_response','partial_response')) AS next_follow_up_at
                    FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    LEFT JOIN leasing.requirements r ON r.work_item_id=w.id
                    LEFT JOIN leasing.partner_outreaches o ON o.work_item_id=w.id
                    WHERE {scope_sql}
                    GROUP BY w.id,c.customer_name
                    ORDER BY CASE WHEN w.case_status='open' AND w.request_due_date < CURRENT_DATE THEN 0 ELSE 1 END,
                    w.request_due_date NULLS LAST,w.updated_at DESC LIMIT 20""", tuple(scope_params))
                recent_items = [dict(row) for row in cur.fetchall()]
                # Workload across all buyers is admin-only. A buyer must not infer another buyer's portfolio.
                if _is_leasing_admin():
                    cur.execute("""SELECT COALESCE(NULLIF(w.buyer_owner_id,''),'__unassigned__') AS buyer_owner_id,
                        COUNT(*) FILTER (WHERE w.case_status='open') AS open_cases,
                        COUNT(*) FILTER (WHERE w.case_status='open' AND w.request_due_date<CURRENT_DATE) AS overdue_cases,
                        COUNT(*) FILTER (WHERE w.case_status='open' AND w.request_due_date=CURRENT_DATE) AS due_today,
                        COUNT(*) FILTER (WHERE w.case_status='open' AND w.current_stage='result_submission') AS pending_submission
                        FROM leasing.work_items w WHERE w.archived_at IS NULL
                        GROUP BY COALESCE(NULLIF(w.buyer_owner_id,''),'__unassigned__') ORDER BY open_cases DESC,buyer_owner_id""")
                    buyer_workload = [dict(row) for row in cur.fetchall()]
                    cur.execute("""SELECT COALESCE(NULLIF(o.follow_up_owner_id,''),NULLIF(w.buyer_owner_id,''),'__unassigned__') AS buyer_owner_id,
                        COUNT(*) AS pending_followups FROM leasing.partner_outreaches o JOIN leasing.work_items w ON w.id=o.work_item_id
                        WHERE w.archived_at IS NULL AND w.case_status='open' AND o.response_status IN ('sent','awaiting_response','partial_response')
                        GROUP BY COALESCE(NULLIF(o.follow_up_owner_id,''),NULLIF(w.buyer_owner_id,''),'__unassigned__')""")
                    followup_counts = {r['buyer_owner_id']: r['pending_followups'] for r in cur.fetchall()}
                    for row in buyer_workload:
                        row['pending_followups'] = followup_counts.get(row['buyer_owner_id'], 0)
                else:
                    buyer_workload = []
                follow_filter = "(o.follow_up_owner_id=%s OR (NULLIF(o.follow_up_owner_id,'') IS NULL AND w.buyer_owner_id=%s))" if not _is_leasing_admin() else "TRUE"
                follow_params = [session['username'], session['username']] if not _is_leasing_admin() else []
                cur.execute(f"""SELECT o.id,o.work_item_id,w.request_id,p.partner_name,o.response_status,o.next_follow_up_at,o.sent_at,
                    COALESCE(NULLIF(o.follow_up_owner_id,''),NULLIF(w.buyer_owner_id,''),'__unassigned__') AS buyer_owner_id,c.customer_name
                    FROM leasing.partner_outreaches o JOIN leasing.work_items w ON w.id=o.work_item_id
                    JOIN leasing.partners p ON p.id=o.partner_id LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    WHERE w.case_status='open' AND o.response_status IN ('sent','awaiting_response','partial_response')
                      AND {scope_sql} AND {follow_filter}
                    ORDER BY CASE WHEN o.next_follow_up_at IS NULL THEN 0 WHEN o.next_follow_up_at<NOW() THEN 1 ELSE 2 END,
                    o.next_follow_up_at NULLS LAST LIMIT 20""", tuple(scope_params + follow_params))
                followups = [dict(row) for row in cur.fetchall()]
                # Action list is server-driven so overdue items outside the current page are not missed.
                cur.execute(f"""SELECT work_item_id,request_id,customer_name,outreach_id,partner_name,action_type,due_at,action_owner,action_status
                    FROM (
                        SELECT ranked_actions.*,
                            ROW_NUMBER() OVER (
                                PARTITION BY work_item_id, action_type, COALESCE(partner_name,'')
                                ORDER BY CASE WHEN due_at IS NULL THEN 0 WHEN due_at<NOW() THEN 1 ELSE 2 END,
                                         due_at NULLS FIRST, outreach_id NULLS FIRST
                            ) AS action_rank
                        FROM (
                            SELECT w.id AS work_item_id,w.request_id,c.customer_name,NULL::BIGINT AS outreach_id,
                                NULL::TEXT AS partner_name,'work_due'::TEXT AS action_type,w.request_due_date::timestamptz AS due_at,
                                w.buyer_owner_id AS action_owner,w.case_status AS action_status
                            FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id
                            WHERE w.case_status='open' AND w.request_due_date IS NOT NULL AND w.request_due_date<=CURRENT_DATE+3 AND {scope_sql}
                            UNION ALL
                            SELECT w.id AS work_item_id,w.request_id,c.customer_name,o.id AS outreach_id,p.partner_name,
                                'partner_followup'::TEXT AS action_type,o.next_follow_up_at AS due_at,
                                COALESCE(NULLIF(o.follow_up_owner_id,''),NULLIF(w.buyer_owner_id,'')) AS action_owner,
                                o.response_status AS action_status
                            FROM leasing.partner_outreaches o JOIN leasing.work_items w ON w.id=o.work_item_id
                            LEFT JOIN leasing.customers c ON c.id=w.customer_id JOIN leasing.partners p ON p.id=o.partner_id
                            WHERE w.case_status='open' AND o.response_status IN ('sent','awaiting_response','partial_response')
                              AND (o.next_follow_up_at IS NULL OR o.next_follow_up_at<=NOW()+INTERVAL '3 days') AND {scope_sql}
                        ) ranked_actions
                    ) deduped_actions WHERE action_rank=1
                    ORDER BY CASE WHEN due_at IS NULL THEN 0 WHEN due_at<NOW() THEN 1 ELSE 2 END,due_at NULLS FIRST,work_item_id LIMIT 12""",
                    tuple(scope_params + scope_params))
                priority_actions = [dict(row) for row in cur.fetchall()]
        try:
            with get_db_connection() as identity_conn:
                with identity_conn.cursor(cursor_factory=RealDictCursor) as identity_cur:
                    if _is_leasing_admin():
                        identity_cur.execute("""SELECT username,full_name,department,role FROM public.users
                            WHERE role IN ('buyer','leasing_admin','platform_admin') ORDER BY full_name,username""")
                    else:
                        identity_cur.execute("""SELECT username,full_name,department,role FROM public.users
                            WHERE username=%s AND role IN ('buyer','leasing_admin','platform_admin')""", (session['username'],))
                    assignees = [dict(row) for row in identity_cur.fetchall()]
        except psycopg2.Error:
            app.logger.exception("Unable to load Leasing assignees")
            assignees = []
        if _is_leasing_admin():
            workload_by_owner = {row['buyer_owner_id']: row for row in buyer_workload}
            expanded = []
            for user in assignees:
                owner = user['username']
                expanded.append(workload_by_owner.pop(owner, {"buyer_owner_id": owner,"open_cases": 0,"overdue_cases": 0,"due_today": 0,"pending_submission": 0,"pending_followups": 0}))
            if '__unassigned__' in workload_by_owner: expanded.append(workload_by_owner.pop('__unassigned__'))
            expanded.extend(workload_by_owner.values())
            buyer_workload = expanded
        return jsonify({"success": True,"summary": summary,"work_items": recent_items,"follow_ups": followups,
                        "priority_actions": priority_actions,"buyer_workload": buyer_workload,"assignees": assignees,
                        "list_hint": "Daftar lengkap dimuat melalui endpoint Work Items dengan server-side pagination."})
    except psycopg2.Error:
        app.logger.exception("Leasing dashboard query failed")
        return jsonify({"success": False,"message": "Gagal memuat dashboard Leasing. Pastikan schema/migration tersedia."}), 500


@app.route("/api/leasing/follow-ups", methods=["GET"])
@leasing_login_required
def leasing_followups_list():
    page = _leasing_query_int(request.args.get("page"), 1, 1, 1_000_000)
    page_size = _leasing_query_int(request.args.get("page_size"), 50, 10, 100)
    q = (request.args.get("q") or "").strip()[:200]
    owner = (request.args.get("owner") or "all").strip()
    if not _is_leasing_admin() and owner not in {"", "all", "mine"}:
        return jsonify({"success": False, "message": "Buyer hanya dapat memfilter follow-up miliknya."}), 403
    where = ["w.case_status='open'", "o.response_status IN ('sent','awaiting_response','partial_response')"]
    params = []
    scope_sql, scope_params = _leasing_scope_sql()
    where.append(scope_sql); params.extend(scope_params)
    if not _is_leasing_admin():
        where.append("(o.follow_up_owner_id=%s OR (NULLIF(o.follow_up_owner_id,'') IS NULL AND w.buyer_owner_id=%s))")
        params.extend([session["username"], session["username"]])
    elif owner == "mine":
        where.append("COALESCE(NULLIF(o.follow_up_owner_id,''),NULLIF(w.buyer_owner_id,''))=%s")
        params.append(session["username"])
    elif owner not in {"", "all", "mine"}:
        where.append("COALESCE(NULLIF(o.follow_up_owner_id,''),NULLIF(w.buyer_owner_id,''))=%s")
        params.append(owner)
    if q:
        like=f"%{q}%"
        where.append("(w.request_id ILIKE %s OR p.partner_name ILIKE %s OR c.customer_name ILIKE %s OR COALESCE(o.notes,'') ILIKE %s)")
        params.extend([like,like,like,like])
    where_sql=" AND ".join(where)
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                from_sql="""FROM leasing.partner_outreaches o JOIN leasing.work_items w ON w.id=o.work_item_id
                    JOIN leasing.partners p ON p.id=o.partner_id LEFT JOIN leasing.customers c ON c.id=w.customer_id"""
                cur.execute(f"SELECT COUNT(*) AS total {from_sql} WHERE {where_sql}", tuple(params))
                total=int(cur.fetchone()["total"] or 0)
                pages=max(1,math.ceil(total/page_size)); page=min(page,pages)
                cur.execute(f"""SELECT o.id,o.work_item_id,w.request_id,w.work_type,w.project_name,p.partner_name,
                    o.response_status,o.next_follow_up_at,o.sent_at,o.outreach_round,o.follow_up_owner_id,o.created_by,
                    COALESCE(NULLIF(o.follow_up_owner_id,''),NULLIF(w.buyer_owner_id,''),'__unassigned__') AS buyer_owner_id,c.customer_name
                    {from_sql} WHERE {where_sql}
                    ORDER BY CASE WHEN o.next_follow_up_at IS NULL THEN 0 WHEN o.next_follow_up_at<NOW() THEN 1 ELSE 2 END,
                    o.next_follow_up_at NULLS LAST,o.created_at DESC,o.id DESC LIMIT %s OFFSET %s""",
                    tuple(params+[page_size,(page-1)*page_size]))
                rows=[dict(r) for r in cur.fetchall()]
        return jsonify({"success":True,"follow_ups":rows,"pagination":{"page":page,"page_size":page_size,"total":total,"total_pages":pages,
            "has_previous":page>1,"has_next":page<pages}})
    except psycopg2.Error:
        app.logger.exception("Leasing follow-up list query failed")
        return jsonify({"success":False,"message":"Gagal memuat antrean follow-up."}),500


@app.route("/api/leasing/assignees", methods=["GET"])
@leasing_login_required
def leasing_assignees():
    """List accounts eligible for Leasing ownership from the shared identity database."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if _is_leasing_admin():
                    cur.execute("""SELECT username, full_name, department, role
                        FROM public.users WHERE role IN ('buyer','leasing_admin','platform_admin')
                        ORDER BY CASE role WHEN 'buyer' THEN 0 WHEN 'leasing_admin' THEN 1 ELSE 2 END,
                                 full_name, username""")
                else:
                    cur.execute("""SELECT username, full_name, department, role
                        FROM public.users WHERE username=%s AND role='buyer'""", (session.get("username"),))
                return jsonify({"success": True, "assignees": [dict(row) for row in cur.fetchall()]})
    except psycopg2.Error:
        app.logger.exception("Leasing assignee list failed")
        return jsonify({"success": False, "message": "Gagal memuat daftar Buyer/PIC."}), 500


@app.route("/api/leasing/work-items", methods=["GET", "POST"])
@leasing_login_required
def leasing_work_items():
    if request.method == "GET":
        page = _leasing_query_int(request.args.get("page"), 1, 1, 1_000_000)
        page_size = _leasing_query_int(request.args.get("page_size"), 50, 10, 100)
        q = (request.args.get("q") or "").strip()[:200]
        status = (request.args.get("status") or "all").strip().lower()
        work_type = (request.args.get("work_type") or "all").strip().lower()
        owner = (request.args.get("owner") or "all").strip()
        queue_filter = (request.args.get("queue") or "all").strip().lower()
        if queue_filter not in {"all", "my_queue", "overdue", "follow_up_today", "waiting_partner", "partial_response", "ready_to_submit", "unassigned"}:
            return jsonify({"success": False, "message": "Filter antrean tidak valid."}), 400
        if status not in {"all", *LEASING_CASE_STATUSES}:
            return jsonify({"success": False, "message": "Filter status tidak valid."}), 400
        if work_type not in {"all", "project", "non_project"}:
            return jsonify({"success": False, "message": "Filter work_type tidak valid."}), 400
        if not _is_leasing_admin() and owner not in {"", "all", "mine"}:
            if owner == "unassigned":
                return jsonify({"success": False, "message": "Buyer tidak dapat melihat antrean global yang belum di-assign."}), 403
            if owner != session.get("username"):
                return jsonify({"success": False, "message": "Filter owner hanya dapat melihat pekerjaan milik sendiri."}), 403
        where, params = [], []
        scope_sql, scope_params = _leasing_scope_sql()
        where.append(scope_sql); params.extend(scope_params)
        if queue_filter == "my_queue":
            where.append("w.buyer_owner_id=%s"); params.append(session.get("username"))
            where.append("w.case_status='open'")
        elif queue_filter == "overdue":
            where.append("w.case_status='open' AND w.request_due_date < CURRENT_DATE")
        elif queue_filter == "follow_up_today":
            where.append("EXISTS (SELECT 1 FROM leasing.partner_outreaches qfo WHERE qfo.work_item_id=w.id AND qfo.next_follow_up_at::date=CURRENT_DATE AND qfo.response_status IN ('sent','awaiting_response','partial_response'))")
        elif queue_filter == "waiting_partner":
            where.append("EXISTS (SELECT 1 FROM leasing.partner_outreaches qwp WHERE qwp.work_item_id=w.id AND qwp.response_status IN ('sent','awaiting_response'))")
        elif queue_filter == "partial_response":
            where.append("EXISTS (SELECT 1 FROM leasing.partner_outreaches qpr WHERE qpr.work_item_id=w.id AND qpr.response_status='partial_response')")
        elif queue_filter == "ready_to_submit":
            where.append("w.case_status='open' AND EXISTS (SELECT 1 FROM leasing.requirements qrr WHERE qrr.work_item_id=w.id) AND NOT EXISTS (SELECT 1 FROM leasing.requirements qrr WHERE qrr.work_item_id=w.id AND qrr.status NOT IN ('resolved','stopped')) AND NOT EXISTS (SELECT 1 FROM leasing.result_submissions qrs WHERE qrs.work_item_id=w.id AND qrs.submission_status='sent')")
        elif queue_filter == "unassigned":
            if not _is_leasing_admin():
                return jsonify({"success": False, "message": "Antrean belum di-assign hanya tersedia untuk admin."}), 403
            where.append("(w.buyer_owner_id IS NULL OR BTRIM(w.buyer_owner_id)='')")
        if status != "all": where.append("w.case_status=%s"); params.append(status)
        if work_type != "all": where.append("w.work_type=%s"); params.append(work_type)
        if owner == "mine" or (owner not in {"", "all", "unassigned"}):
            owner_value = session.get("username") if owner == "mine" else owner
            where.append("w.buyer_owner_id=%s"); params.append(owner_value)
        elif owner == "unassigned":
            if not _is_leasing_admin():
                where.append("FALSE")
            else:
                where.append("(w.buyer_owner_id IS NULL OR BTRIM(w.buyer_owner_id)='')")
        if q:
            pattern = f"%{q}%"
            where.append("(w.request_id ILIKE %s OR COALESCE(w.project_name,'') ILIKE %s OR COALESCE(c.customer_name,'') ILIKE %s OR COALESCE(w.requester_name,'') ILIKE %s OR COALESCE(w.requester_division,'') ILIKE %s OR COALESCE(w.buyer_owner_id,'') ILIKE %s OR EXISTS (SELECT 1 FROM leasing.requirements qr WHERE qr.work_item_id=w.id AND (COALESCE(qr.site_name,'') ILIKE %s OR COALESCE(qr.address,'') ILIKE %s OR COALESCE(qr.external_reference,'') ILIKE %s)))")
            params.extend([pattern] * 9)
        where_sql = " AND ".join(where) if where else "TRUE"
        try:
            with get_leasing_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute(f"SELECT COUNT(*) AS total FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id WHERE {where_sql}", tuple(params))
                    total = int(cur.fetchone()["total"] or 0)
                    pages = max(1, math.ceil(total / page_size))
                    page = min(page, pages)
                    cur.execute(f"""SELECT w.*, c.customer_name,
                        COUNT(DISTINCT r.id) AS requirement_count,
                        COUNT(DISTINCT r.id) FILTER (WHERE r.status IN ('resolved','stopped')) AS resolved_count,
                        COUNT(DISTINCT o.id) FILTER (WHERE o.response_status IN ('sent','awaiting_response','partial_response')) AS pending_partner_responses,
                        MIN(o.next_follow_up_at) FILTER (WHERE o.next_follow_up_at IS NOT NULL AND o.response_status IN ('sent','awaiting_response','partial_response')) AS next_follow_up_at
                        FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id
                        LEFT JOIN leasing.requirements r ON r.work_item_id=w.id
                        LEFT JOIN leasing.partner_outreaches o ON o.work_item_id=w.id
                        WHERE {where_sql}
                        GROUP BY w.id,c.customer_name
                        ORDER BY CASE WHEN w.case_status='open' AND w.request_due_date<CURRENT_DATE THEN 0 ELSE 1 END,
                            w.request_due_date NULLS LAST,w.updated_at DESC,w.id DESC
                        LIMIT %s OFFSET %s""", tuple(params + [page_size, (page - 1) * page_size]))
                    items = [dict(x) for x in cur.fetchall()]
                    return jsonify({"success": True,"work_items": items,"pagination": {"page": page,"page_size": page_size,
                        "total": total,"total_pages": pages,"has_previous": page > 1,"has_next": page < pages},
                        "filters": {"q": q,"status": status,"work_type": work_type,"owner": owner,"queue": queue_filter}})
        except psycopg2.Error:
            app.logger.exception("Leasing paginated work item list failed")
            return jsonify({"success": False, "message": "Gagal memuat daftar Work Item. Periksa log server."}), 500

    payload = request.get_json(silent=True) or {}
    requester_name = str(payload.get("requester_name") or "").strip()
    customer_name = str(payload.get("customer_name") or "").strip()
    requirements = payload.get("requirements") or []
    if not requester_name or not customer_name or not isinstance(requirements, list) or not requirements:
        return jsonify({"success": False, "message": "customer_name, requester_name, dan minimal satu requirement wajib diisi."}), 400
    try:
        normalized_requirements = []
        for idx, req in enumerate(requirements, start=1):
            if not isinstance(req, dict):
                raise ValueError(f"Requirement {idx} harus berupa object.")
            normalized_requirements.append(_leasing_validate_requirement_payload(req, f"Requirement {idx}"))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    request_id = str(payload.get("request_id") or ("LEA-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6].upper())).strip()
    owner = str(payload.get("buyer_owner_id") or session["username"]).strip()
    if not _is_leasing_admin() and owner != session.get("username"):
        return jsonify({"success": False, "message": "Buyer hanya boleh membuat Work Item untuk dirinya sendiri; assignment antar-buyer dilakukan admin."}), 403
    if not leasing_owner_is_valid(owner):
        return jsonify({"success": False, "message": "Buyer/PIC tidak ditemukan atau tidak memiliki role Leasing. Pilih akun pada daftar Buyer/PIC."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                request_id = _leasing_assert_request_id_available(cur, request_id)
                # Reuse the customer directory record, but never use customer name to group Work Items.
                cur.execute("SELECT id FROM leasing.customers WHERE customer_name=%s ORDER BY id LIMIT 1", (customer_name,))
                customer = cur.fetchone()
                if not customer:
                    cur.execute("INSERT INTO leasing.customers (customer_name) VALUES (%s) RETURNING id", (customer_name,))
                    customer = cur.fetchone()
                cur.execute("""INSERT INTO leasing.work_items
                    (request_id, customer_id, requester_name, requester_email, requester_division,
                     requester_role, request_due_date, buyer_owner_id, source_reference, notes, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (request_id, customer["id"], requester_name, payload.get("requester_email"),
                     payload.get("requester_division"), payload.get("requester_role"),
                     payload.get("request_due_date") or None, owner,
                     payload.get("source_reference"), payload.get("notes"), session["username"]))
                work_item_id = cur.fetchone()["id"]
                for idx, req in enumerate(normalized_requirements, start=1):
                    cur.execute("""INSERT INTO leasing.requirements
                        (work_item_id, requirement_no, order_type, si, area, address, gedung_kawasan, latitude, longitude,
                         a_end, z_end, bandwidth, bandwidth_unit, service_type, special_features,
                         existing_mrc_amount, existing_mrc_currency, existing_mrc_inet_dedicated_25_amount,
                         existing_mrc_metro_25_amount, external_reference, requested_services)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (work_item_id, idx, req["order_type"], req["si"], req["area"], req["address"],
                         req["gedung_kawasan"], req["latitude"], req["longitude"], req["a_end"], req["z_end"], req["bandwidth"],
                         req["bandwidth_unit"], req["service_type"], req["special_features"],
                         req["existing_mrc_amount"], req["existing_mrc_currency"],
                         req.get("existing_mrc_inet_dedicated_25_amount"), req.get("existing_mrc_metro_25_amount"),
                         req.get("external_reference"), req.get("requested_services") or []))
                leasing_activity(cur, work_item_id, "work_item_created", "Work Item Leasing dibuat", session["username"], {"request_id": request_id})
            conn.commit()
        return jsonify({"success": True, "id": work_item_id, "request_id": request_id, "message": "Work Item Leasing berhasil dibuat."}), 201
    except (psycopg2.Error, ValueError) as exc:
        app.logger.exception("Leasing work item create failed")
        return jsonify({"success": False, "message": str(exc) if isinstance(exc, ValueError) else "Gagal membuat Work Item. Periksa schema dan data yang dikirim."}), 400


@app.route("/api/leasing/work-items/<int:work_item_id>", methods=["GET", "PATCH"])
@leasing_login_required
def leasing_work_item_detail(work_item_id):
    if request.method == "PATCH":
        if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
            return _leasing_owner_mutation_denied()
        payload = request.get_json(silent=True) or {}
        allowed = {"current_stage", "case_status", "closure_reason", "request_due_date", "buyer_owner_id", "notes"}
        changes = {k: payload[k] for k in allowed if k in payload}
        if not changes:
            return jsonify({"success": False, "message": "Tidak ada field yang diperbarui."}), 400
        if "current_stage" in changes and changes["current_stage"] not in LEASING_STAGES:
            return jsonify({"success": False, "message": "Stage tidak valid."}), 400
        if "case_status" in changes and changes["case_status"] not in LEASING_CASE_STATUSES:
            return jsonify({"success": False, "message": "Status case tidak valid."}), 400
        if "buyer_owner_id" in changes:
            owner = str(changes.get("buyer_owner_id") or "").strip()
            if not _is_leasing_admin() and owner != session.get("username"):
                return jsonify({"success": False, "message": "Buyer tidak dapat melepas atau mengalihkan ownership. Assignment dikelola admin Leasing."}), 403
            if owner and not leasing_owner_is_valid(owner):
                return jsonify({"success": False, "message": "Buyer/PIC tidak ditemukan atau tidak memiliki role Leasing."}), 400
            changes["buyer_owner_id"] = owner or None
        if changes.get("case_status") == "closed" and not str(changes.get("closure_reason") or payload.get("closure_reason") or "").strip():
            return jsonify({"success": False, "message": "closure_reason wajib diisi untuk menutup case."}), 400
        if "case_status" in changes:
            changes["closed_at"] = "NOW()" if changes["case_status"] == "closed" else None
        try:
            with get_leasing_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("SELECT * FROM leasing.work_items WHERE id=%s AND archived_at IS NULL FOR UPDATE", (work_item_id,))
                    current_item = cur.fetchone()
                    if not current_item: return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                    if changes.get("case_status") == "closed":
                        cur.execute("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status IN ('resolved','stopped')) AS done FROM leasing.requirements WHERE work_item_id=%s", (work_item_id,))
                        progress = cur.fetchone()
                        if progress["total"] == 0 or progress["total"] != progress["done"]:
                            return jsonify({"success": False, "code": "REQUIREMENTS_OPEN", "message": "Case belum bisa ditutup: semua requirement harus resolved/stopped."}), 409
                        cur.execute("""SELECT COUNT(*) AS total,
                            COUNT(*) FILTER (WHERE next_follow_up_at < NOW()) AS overdue,
                            MIN(next_follow_up_at) AS next_due
                            FROM leasing.partner_outreaches
                            WHERE work_item_id=%s AND response_status IN ('sent','awaiting_response','partial_response')""", (work_item_id,))
                        outstanding = dict(cur.fetchone())
                        outstanding_count = int(outstanding.get("total") or 0)
                        if outstanding_count and not payload.get("override_open_followups"):
                            return jsonify({"success": False, "code": "OPEN_FOLLOWUPS", "requires_override": True,
                                "open_followups": outstanding_count, "overdue_followups": int(outstanding.get("overdue") or 0),
                                "next_follow_up_at": outstanding.get("next_due"),
                                "message": f"Masih ada {outstanding_count} follow-up partner terbuka ({int(outstanding.get('overdue') or 0)} overdue). Konfirmasi override atau selesaikan follow-up terlebih dahulu."}), 409
                        if outstanding_count and len(str(payload.get("override_reason") or "").strip()) < 10:
                            return jsonify({"success": False, "code": "OVERRIDE_REASON_REQUIRED", "message": "Alasan override penutupan dengan follow-up terbuka wajib minimal 10 karakter."}), 400
                        if outstanding_count:
                            changes["closure_override_reason"] = str(payload.get("override_reason") or "").strip()
                    audit_changes = dict(changes)
                    override_reason = audit_changes.pop("closure_override_reason", None)
                    assignments, values = [], []
                    for key, value in audit_changes.items():
                        if key == "closed_at":
                            assignments.append("closed_at = NOW()" if value == "NOW()" else "closed_at = NULL")
                        else:
                            assignments.append(f"{key} = %s")
                            values.append(value or None if key == "request_due_date" else value)
                    values.append(work_item_id)
                    assignments.append("updated_at=NOW()")
                    cur.execute(f"UPDATE leasing.work_items SET {', '.join(assignments)} WHERE id=%s", values)
                    before_values = {k: current_item.get(k) for k in audit_changes if k in current_item}
                    after_values = {k: v for k, v in audit_changes.items() if k != "closed_at"}
                    if override_reason:
                        after_values["closure_override_reason"] = override_reason
                    _leasing_field_audit(cur, "work_item", work_item_id, work_item_id, "update", session["username"], before_values, after_values, override_reason)
                    leasing_activity(cur, work_item_id, "work_item_updated", "Work Item diperbarui", session["username"], audit_changes)
                conn.commit()
            return jsonify({"success": True, "message": "Work Item diperbarui."})
        except psycopg2.Error:
            app.logger.exception("Leasing work item update failed")
            return jsonify({"success": False, "message": "Gagal memperbarui Work Item."}), 400

    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT w.*, c.customer_name FROM leasing.work_items w
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id WHERE w.id=%s AND w.archived_at IS NULL""", (work_item_id,))
                work_item = cur.fetchone()
                if not work_item: return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                # The initial detail route is intentionally compact. Large projects should not
                # transfer all offers, negotiation events, result lines and activity on first open.
                if request.args.get("view") == "summary":
                    compact_scope = "full"
                    compact_owner = _is_leasing_admin() or work_item.get("buyer_owner_id") == session.get("username")
                    if not compact_owner:
                        cur.execute("""SELECT COUNT(DISTINCT o.id) AS outreach_count
                            FROM leasing.partner_outreaches o
                            WHERE o.work_item_id=%s AND o.follow_up_owner_id=%s
                              AND EXISTS (SELECT 1 FROM leasing.outreach_requirements oro WHERE oro.outreach_id=o.id)""",
                            (work_item_id, session.get("username")))
                        assigned_count = int((cur.fetchone() or {}).get("outreach_count") or 0)
                        if assigned_count < 1:
                            return jsonify({"success": False, "message": "Work Item tidak ditemukan atau tidak memiliki outreach yang ditugaskan kepadamu."}), 404
                        compact_scope = "assigned_follow_up"
                    requirement_scope = " AND EXISTS (SELECT 1 FROM leasing.outreach_requirements oro JOIN leasing.partner_outreaches o ON o.id=oro.outreach_id WHERE oro.requirement_id=r.id AND o.work_item_id=r.work_item_id AND o.follow_up_owner_id=%s)" if compact_scope == "assigned_follow_up" else ""
                    requirement_params = (work_item_id, session.get("username")) if requirement_scope else (work_item_id,)
                    cur.execute(f"""SELECT COUNT(*) AS requirement_total,
                        COUNT(*) FILTER (WHERE r.status IN ('resolved','stopped')) AS requirement_done,
                        COUNT(*) FILTER (WHERE r.status='open') AS requirement_open
                        FROM leasing.requirements r WHERE r.work_item_id=%s{requirement_scope}""", requirement_params)
                    compact_counts = dict(cur.fetchone() or {})
                    outreach_scope = " AND follow_up_owner_id=%s" if compact_scope == "assigned_follow_up" else ""
                    outreach_params = (work_item_id, session.get("username")) if outreach_scope else (work_item_id,)
                    cur.execute(f"""SELECT COUNT(*) AS outreach_total,
                        COUNT(*) FILTER (WHERE response_status IN ('sent','awaiting_response','partial_response')) AS outreach_open,
                        COUNT(*) FILTER (WHERE response_status='partial_response') AS outreach_partial
                        FROM leasing.partner_outreaches WHERE work_item_id=%s{outreach_scope}""", outreach_params)
                    compact_counts.update(dict(cur.fetchone() or {}))
                    cur.execute("SELECT COUNT(*) AS target_count FROM leasing.commercial_targets WHERE work_item_id=%s", (work_item_id,))
                    compact_counts["target_count"] = int((cur.fetchone() or {}).get("target_count") or 0) if compact_scope == "full" else None
                    work_item = dict(work_item)
                    work_item["detail_scope"] = compact_scope
                    work_item["summary_counts"] = compact_counts
                    work_item["total_requirement_count"] = int(compact_counts.get("requirement_total") or 0)
                    work_item["scope_requirement_count"] = int(compact_counts.get("requirement_total") or 0)
                    return jsonify({"success": True, "view": "summary", "detail_scope": compact_scope,
                        "work_item": work_item, "summary_counts": compact_counts, "requirements": [],
                        "partner_outreaches": [], "outreach_requirements": [], "offers": [], "offer_lines": [],
                        "offer_service_lines": [], "commercial_targets": [], "negotiation_events": [],
                        "result_submissions": [], "submission_lines": [], "activity": [], "data_loaded": False})
                cur.execute("SELECT * FROM leasing.requirements WHERE work_item_id=%s ORDER BY requirement_no", (work_item_id,))
                requirements = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT o.*, p.partner_name FROM leasing.partner_outreaches o
                    JOIN leasing.partners p ON p.id=o.partner_id WHERE o.work_item_id=%s ORDER BY o.created_at DESC""", (work_item_id,))
                outreaches = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT oro.outreach_id, oro.requirement_id,
                    CASE
                        WHEN EXISTS (
                            SELECT 1 FROM leasing.partner_offers po_s
                            JOIN leasing.partner_offer_service_lines osl_s ON osl_s.offer_id=po_s.id
                            WHERE po_s.outreach_id=oro.outreach_id AND po_s.offer_status='current'
                              AND osl_s.requirement_id=oro.requirement_id
                        ) THEN oro.response_status
                        ELSE CASE current_line.feasibility_status
                            WHEN 'can_provide' THEN 'can_provide' WHEN 'cannot_provide' THEN 'cannot_provide'
                            WHEN 'needs_clarification' THEN 'needs_clarification' ELSE oro.response_status END
                    END AS requirement_response_status,
                    COALESCE(current_line.notes, oro.response_note) AS response_note,
                    r.requirement_no, r.order_type, r.si, r.area, r.address, r.gedung_kawasan, r.a_end, r.z_end,
                    r.bandwidth, r.bandwidth_unit, r.service_type, r.status AS requirement_status
                    FROM leasing.outreach_requirements oro
                    JOIN leasing.requirements r ON r.id=oro.requirement_id
                    JOIN leasing.partner_outreaches o ON o.id=oro.outreach_id
                    LEFT JOIN LATERAL (SELECT pol.feasibility_status, pol.notes
                        FROM leasing.partner_offers po JOIN leasing.partner_offer_lines pol ON pol.offer_id=po.id
                        WHERE po.outreach_id=o.id AND po.offer_status='current' AND pol.requirement_id=oro.requirement_id
                        ORDER BY po.version_no DESC LIMIT 1) current_line ON TRUE
                    WHERE o.work_item_id=%s ORDER BY o.created_at DESC, r.requirement_no""", (work_item_id,))
                outreach_requirements = [dict(x) for x in cur.fetchall()]
                cur.execute("SELECT * FROM leasing.activity_events WHERE work_item_id=%s ORDER BY occurred_at DESC LIMIT 200", (work_item_id,))
                activity = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT ct.*, r.requirement_no, r.gedung_kawasan FROM leasing.commercial_targets ct
                    LEFT JOIN leasing.requirements r ON r.id=ct.requirement_id
                    WHERE ct.work_item_id=%s ORDER BY ct.requirement_id NULLS FIRST, ct.metric, ct.created_at DESC""", (work_item_id,))
                commercial_targets = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT po.*, o.work_item_id, p.partner_name FROM leasing.partner_offers po
                    JOIN leasing.partner_outreaches o ON o.id=po.outreach_id JOIN leasing.partners p ON p.id=o.partner_id
                    WHERE o.work_item_id=%s ORDER BY po.created_at DESC""", (work_item_id,))
                offers = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT pol.*, po.outreach_id, po.version_no, po.offer_status, po.received_at, po.valid_until,
                    po.notes AS offer_notes, po.created_at AS offer_created_at,
                    o.partner_id, p.partner_name, r.requirement_no, r.order_type, r.si, r.area, r.address, r.gedung_kawasan, r.zone,
                    r.site_name, r.postal_code, r.project_mrc_inet_dedicated_25, r.project_mrc_metro_25, r.requested_otc,
                    r.a_end, r.z_end, r.bandwidth, r.bandwidth_unit, r.service_type
                    FROM leasing.partner_offer_lines pol
                    JOIN leasing.partner_offers po ON po.id=pol.offer_id
                    JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                    JOIN leasing.partners p ON p.id=o.partner_id
                    JOIN leasing.requirements r ON r.id=pol.requirement_id
                    WHERE o.work_item_id=%s ORDER BY po.created_at DESC, r.requirement_no""", (work_item_id,))
                offer_lines = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT ne.*, pol.requirement_id, r.requirement_no, p.partner_name
                    FROM leasing.negotiation_events ne
                    JOIN leasing.partner_offer_lines pol ON pol.id=ne.offer_line_id
                    JOIN leasing.requirements r ON r.id=pol.requirement_id
                    JOIN leasing.partner_offers po ON po.id=pol.offer_id
                    JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                    JOIN leasing.partners p ON p.id=o.partner_id
                    WHERE o.work_item_id=%s ORDER BY ne.occurred_at DESC""", (work_item_id,))
                negotiation_events = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT sne.*, o.id AS outreach_id, osl.id AS service_line_id,
                    osl.requirement_id, osl.service_name, r.requirement_no, p.partner_name
                    FROM leasing.partner_service_negotiation_events sne
                    JOIN leasing.partner_offer_service_lines osl ON osl.id=sne.service_line_id
                    JOIN leasing.partner_offers po ON po.id=osl.offer_id
                    JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                    JOIN leasing.partners p ON p.id=o.partner_id
                    JOIN leasing.requirements r ON r.id=osl.requirement_id
                    WHERE o.work_item_id=%s ORDER BY sne.occurred_at DESC,sne.id DESC""", (work_item_id,))
                generic_negotiation_events = [dict(x) for x in cur.fetchall()]
                negotiation_events.extend(generic_negotiation_events)
                negotiation_events.sort(key=lambda x: str(x.get("occurred_at") or ""), reverse=True)
                offer_service_lines = []  # Loaded separately through paginated service-coverage API.
                cur.execute("SELECT * FROM leasing.result_submissions WHERE work_item_id=%s ORDER BY submission_no DESC", (work_item_id,))
                submissions = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT rsl.*, r.requirement_no, r.gedung_kawasan, pol.mrc_amount,
                    pol.otc_amount, pol.currency, p.partner_name
                    FROM leasing.result_submission_lines rsl
                    JOIN leasing.result_submissions rs ON rs.id=rsl.submission_id
                    JOIN leasing.requirements r ON r.id=rsl.requirement_id
                    LEFT JOIN leasing.partner_offer_lines pol ON pol.id=rsl.offer_line_id
                    LEFT JOIN leasing.partner_offers po ON po.id=pol.offer_id
                    LEFT JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                    LEFT JOIN leasing.partners p ON p.id=o.partner_id
                    WHERE rs.work_item_id=%s ORDER BY rs.submission_no DESC, r.requirement_no""", (work_item_id,))
                submission_lines = [dict(x) for x in cur.fetchall()]
        work_item = dict(work_item)
        detail_scope = "full"
        if not _is_leasing_admin() and work_item.get("buyer_owner_id") != session.get("username"):
            # A delegated follow-up PIC receives only the exact outreach/site context assigned to them.
            assigned_outreaches = [o for o in outreaches if o.get("follow_up_owner_id") == session.get("username")]
            assigned_outreach_ids = {int(o["id"]) for o in assigned_outreaches}
            if not assigned_outreach_ids:
                return jsonify({"success": False, "message": "Work Item tidak ditemukan atau tidak memiliki outreach yang ditugaskan kepadamu."}), 404
            all_requirement_count = len(requirements)
            allowed_requirement_ids = {int(x["requirement_id"]) for x in outreach_requirements
                                       if int(x["outreach_id"]) in assigned_outreach_ids}
            requirements = [r for r in requirements if int(r["id"]) in allowed_requirement_ids]
            outreaches = assigned_outreaches
            outreach_requirements = [x for x in outreach_requirements if int(x["outreach_id"]) in assigned_outreach_ids]
            offers = [x for x in offers if int(x["outreach_id"]) in assigned_outreach_ids]
            offer_lines = [x for x in offer_lines if int(x["outreach_id"]) in assigned_outreach_ids]
            allowed_offer_line_ids = {int(x["id"]) for x in offer_lines}
            negotiation_events = [x for x in negotiation_events if
                (x.get("offer_line_id") is not None and int(x.get("offer_line_id") or 0) in allowed_offer_line_ids)
                or (x.get("service_line_id") is not None and int(x.get("outreach_id") or 0) in assigned_outreach_ids)]
            # Targets, result submissions and other actors' activity are owner/admin data.
            commercial_targets = []
            submissions = []
            submission_lines = []
            activity = [x for x in activity if x.get("actor_id") == session.get("username")]
            work_item["detail_scope"] = "assigned_follow_up"
            work_item["total_requirement_count"] = all_requirement_count
            work_item["scope_requirement_count"] = len(allowed_requirement_ids)
            detail_scope = "assigned_follow_up"
        return jsonify({"success": True, "detail_scope": detail_scope, "work_item": work_item, "requirements": requirements,
                        "partner_outreaches": outreaches, "outreach_requirements": outreach_requirements,
                        "offers": offers, "offer_lines": offer_lines, "offer_service_lines": offer_service_lines,
                        "commercial_targets": commercial_targets, "negotiation_events": negotiation_events, "result_submissions": submissions,
                        "submission_lines": submission_lines, "activity": activity})
    except psycopg2.Error:
        app.logger.exception("Leasing work item detail failed")
        return jsonify({"success": False, "message": "Gagal memuat detail Work Item."}), 500


@app.route("/api/leasing/work-items/<int:work_item_id>/service-coverage", methods=["GET"])
@leasing_login_required
def leasing_service_coverage(work_item_id):
    """Paginated site × partner × arbitrary-service coverage, independent of service names/prices."""
    page=_leasing_query_int(request.args.get("page"),1,1,1_000_000)
    page_size=_leasing_query_int(request.args.get("page_size"),100,10,200)
    q=(request.args.get("q") or "").strip()[:200]
    limited_to_assigned_outreach = not _leasing_user_is_work_item_owner_or_admin(work_item_id)
    coverage_scope_filter = " AND o.follow_up_owner_id=%s" if limited_to_assigned_outreach else ""
    base_params = (work_item_id, session.get("username")) if limited_to_assigned_outreach else (work_item_id,)
    base_cte=f"""WITH latest_partner_site AS (
        SELECT DISTINCT ON (o.partner_id, oro.requirement_id)
            o.id AS outreach_id,o.work_item_id,o.partner_id,p.partner_name,o.outreach_round,
            o.sent_at,o.responded_at,o.created_at,o.response_status AS outreach_status,o.next_follow_up_at,
            w.request_id,c.customer_name,oro.requirement_id,oro.response_status AS site_response_status,
            o.follow_up_owner_id,w.buyer_owner_id
        FROM leasing.outreach_requirements oro
        JOIN leasing.partner_outreaches o ON o.id=oro.outreach_id
        JOIN leasing.partners p ON p.id=o.partner_id
        JOIN leasing.work_items w ON w.id=o.work_item_id
        LEFT JOIN leasing.customers c ON c.id=w.customer_id
        WHERE w.id=%s AND COALESCE(o.response_status,'') <> 'cancelled'{coverage_scope_filter}
        ORDER BY o.partner_id,oro.requirement_id,
          CASE WHEN (o.sent_at IS NOT NULL OR o.responded_at IS NOT NULL) AND o.response_status NOT IN ('draft','cancelled') THEN 0 ELSE 1 END,
          GREATEST(COALESCE(o.sent_at,o.created_at),COALESCE(o.responded_at,o.created_at)) DESC,o.id DESC
    ), service_catalog AS (
        SELECT lps.*,r.requirement_no,r.site_name,r.zone,r.address,r.postal_code,r.si,r.area,r.service_type,
            svc.service_name,CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN TRUE
                 ELSE COALESCE(NULLIF(BTRIM(r.service_type),''),'')<>'' END AS is_requested_service,
            CARDINALITY(CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                 ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END) AS service_count
        FROM latest_partner_site lps
        JOIN leasing.requirements r ON r.id=lps.requirement_id
        CROSS JOIN LATERAL unnest(
            CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                 ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END
        ) AS svc(service_name)
    ), expanded AS (
        SELECT * FROM service_catalog
        UNION ALL
        SELECT lps.*,r.requirement_no,r.site_name,r.zone,r.address,r.postal_code,r.si,r.area,r.service_type,
            osl.service_name,FALSE AS is_requested_service,
            CARDINALITY(CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                 ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END) AS service_count
        FROM latest_partner_site lps
        JOIN leasing.requirements r ON r.id=lps.requirement_id
        JOIN leasing.partner_offers po ON po.outreach_id=lps.outreach_id AND po.offer_status='current'
        JOIN leasing.partner_offer_service_lines osl ON osl.offer_id=po.id AND osl.requirement_id=r.id
        WHERE NOT EXISTS (
            SELECT 1 FROM unnest(CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                 ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END) AS requested_service(n)
            WHERE LOWER(BTRIM(requested_service.n))=LOWER(BTRIM(osl.service_name))
        )
    )"""
    q_where=""
    q_params=[]
    if q:
        q_where=" WHERE (request_id ILIKE %s OR customer_name ILIKE %s OR partner_name ILIKE %s OR service_name ILIKE %s OR COALESCE(site_name,'') ILIKE %s OR COALESCE(address,'') ILIKE %s OR COALESCE(zone,'') ILIKE %s OR COALESCE(site_response_status,'') ILIKE %s)"
        like=f"%{q}%";q_params=[like]*8

    # Keep the visible rows and the all-results status summary on the exact same
    # service-level status rules. Counts intentionally distinguish requested
    # services from additional services suggested by a partner.
    coverage_status_case = """CASE
        WHEN x.site_response_status='no_bid' OR x.outreach_status='no_bid' THEN 'no_bid'
        WHEN osl.feasibility_status IS NOT NULL AND osl.feasibility_status <> 'pending' THEN osl.feasibility_status
        WHEN pol.feasibility_status='cannot_provide' OR x.site_response_status='cannot_provide' THEN 'cannot_provide'
        WHEN pol.feasibility_status='can_provide' AND x.service_count<=1 THEN 'can_provide'
        WHEN x.site_response_status='can_provide' AND x.service_count<=1 THEN 'can_provide'
        WHEN pol.feasibility_status='can_provide' OR x.site_response_status='can_provide' THEN 'needs_clarification'
        WHEN pol.feasibility_status='needs_clarification' OR x.site_response_status='needs_clarification' THEN 'needs_clarification'
        WHEN x.outreach_status='responded' AND COALESCE(x.site_response_status,'awaiting_response')='awaiting_response' THEN 'response_not_logged'
        WHEN x.sent_at IS NULL AND x.outreach_status='draft' THEN 'draft'
        WHEN osl.feasibility_status='pending' THEN 'pending'
        ELSE 'awaiting_response'
    END"""
    coverage_status_joins = """LEFT JOIN LATERAL (
        SELECT po2.id,po2.version_no,osl2.id AS service_line_id,osl2.feasibility_status,
               osl2.mrc_amount,osl2.otc_amount,osl2.currency,osl2.notes
        FROM leasing.partner_offers po2
        JOIN leasing.partner_offer_service_lines osl2 ON osl2.offer_id=po2.id
        WHERE po2.outreach_id=x.outreach_id AND po2.offer_status='current'
          AND osl2.requirement_id=x.requirement_id
          AND LOWER(BTRIM(osl2.service_name))=LOWER(BTRIM(x.service_name))
        ORDER BY po2.version_no DESC LIMIT 1
    ) osl ON TRUE
    LEFT JOIN LATERAL (
        SELECT po3.id,po3.version_no,pol3.feasibility_status
        FROM leasing.partner_offers po3
        JOIN leasing.partner_offer_lines pol3 ON pol3.offer_id=po3.id
        WHERE po3.outreach_id=x.outreach_id AND po3.offer_status='current'
          AND pol3.requirement_id=x.requirement_id
        ORDER BY po3.version_no DESC LIMIT 1
    ) pol ON TRUE"""
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(base_cte+f"""
                    SELECT COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE x.is_requested_service) AS required_services,
                        COUNT(*) FILTER (WHERE NOT x.is_requested_service
                            AND LOWER(BTRIM(x.service_name)) <> 'service belum ditentukan') AS additional_services,
                        COUNT(*) FILTER (WHERE LOWER(BTRIM(x.service_name)) = 'service belum ditentukan') AS unspecified_services,
                        COUNT(*) FILTER (WHERE x.is_requested_service AND ({coverage_status_case})='can_provide') AS covered,
                        COUNT(*) FILTER (WHERE x.is_requested_service AND ({coverage_status_case})='cannot_provide') AS not_covered,
                        COUNT(*) FILTER (WHERE x.is_requested_service AND ({coverage_status_case})='needs_clarification') AS needs_clarification,
                        COUNT(*) FILTER (WHERE x.is_requested_service AND ({coverage_status_case}) IN ('awaiting_response','pending','draft','response_not_logged')) AS waiting,
                        COUNT(*) FILTER (WHERE x.is_requested_service AND ({coverage_status_case})='no_bid') AS no_bid
                    FROM expanded x
                    {coverage_status_joins}
                    {q_where}
                """,(*base_params,*q_params))
                summary_row=cur.fetchone() or {}
                summary={key:int(summary_row.get(key) or 0) for key in (
                    "total","required_services","additional_services","unspecified_services","covered","not_covered",
                    "needs_clarification","waiting","no_bid")}
                total=summary["total"]
                pages=max(1,math.ceil(total/page_size));page=min(page,pages)
                cur.execute(base_cte+f"""
                    SELECT x.outreach_id,x.work_item_id,x.request_id,x.customer_name,x.partner_id,x.partner_name,
                        x.outreach_round,x.sent_at,x.created_at,x.outreach_status,x.next_follow_up_at,
                        COALESCE(NULLIF(x.follow_up_owner_id,''),NULLIF(x.buyer_owner_id,''),'__unassigned__') AS follow_up_owner,
                        x.requirement_id,x.requirement_no,x.site_name,x.zone,x.address,x.postal_code,x.si,x.area,
                        x.service_type,x.service_name,x.is_requested_service,
                        osl.service_line_id,osl.feasibility_status AS service_status,osl.mrc_amount AS service_mrc,osl.otc_amount AS service_otc,
                        osl.currency AS service_currency,osl.notes AS service_notes,COALESCE(osl.version_no,pol.version_no) AS version_no,
                        sn.event_type AS latest_negotiation_event,sn.mrc_amount AS latest_negotiated_mrc,
                        sn.otc_amount AS latest_negotiated_otc,sn.currency AS latest_negotiated_currency,
                        sn.occurred_at AS latest_negotiation_at,sn.notes AS latest_negotiation_notes,
                        pol.feasibility_status AS overall_site_status,
                        {coverage_status_case} AS coverage_status,
                        mt.target_amount AS target_mrc,mt.currency AS target_mrc_currency,
                        ot.target_amount AS target_otc,ot.currency AS target_otc_currency
                    FROM expanded x
                    {coverage_status_joins}
                    LEFT JOIN LATERAL (
                        SELECT sne.event_type,sne.mrc_amount,sne.otc_amount,sne.currency,sne.occurred_at,sne.notes
                        FROM leasing.partner_service_negotiation_events sne
                        WHERE sne.service_line_id=osl.service_line_id
                        ORDER BY sne.occurred_at DESC,sne.id DESC LIMIT 1
                    ) sn ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT ct.target_amount,ct.currency FROM leasing.commercial_targets ct
                        WHERE ct.work_item_id=x.work_item_id AND ct.metric='mrc'
                          AND (ct.requirement_id=x.requirement_id OR ct.requirement_id IS NULL)
                          AND (ct.service_name IS NULL OR LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(x.service_name)))
                        ORDER BY CASE
                            WHEN ct.requirement_id IS NOT NULL AND ct.service_name IS NOT NULL THEN 4
                            WHEN ct.requirement_id IS NOT NULL THEN 3
                            WHEN ct.service_name IS NOT NULL THEN 2
                            ELSE 1 END DESC, ct.created_at DESC, ct.id DESC LIMIT 1
                    ) mt ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT ct.target_amount,ct.currency FROM leasing.commercial_targets ct
                        WHERE ct.work_item_id=x.work_item_id AND ct.metric='otc'
                          AND (ct.requirement_id=x.requirement_id OR ct.requirement_id IS NULL)
                          AND (ct.service_name IS NULL OR LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(x.service_name)))
                        ORDER BY CASE
                            WHEN ct.requirement_id IS NOT NULL AND ct.service_name IS NOT NULL THEN 4
                            WHEN ct.requirement_id IS NOT NULL THEN 3
                            WHEN ct.service_name IS NOT NULL THEN 2
                            ELSE 1 END DESC, ct.created_at DESC, ct.id DESC LIMIT 1
                    ) ot ON TRUE
                    {q_where}
                    ORDER BY x.requirement_no,x.partner_name,x.service_name
                    LIMIT %s OFFSET %s""",(*base_params,*q_params,page_size,(page-1)*page_size))
                rows=[dict(row) for row in cur.fetchall()]
        return jsonify({"success":True,"rows":rows,"summary":summary,"pagination":{"page":page,"page_size":page_size,
            "total":total,"total_pages":pages,"has_previous":page>1,"has_next":page<pages},
            "semantics":{"cover_status":"Coverage per requested service; prices are independent/optional.",
              "draft":"Partner has a saved outreach draft but it has not been sent.",
              "needs_clarification":"Site-level response does not identify coverage for each requested service."}})
    except psycopg2.Error:
        app.logger.exception("Leasing service coverage query failed")
        return jsonify({"success":False,"message":"Gagal memuat matrix coverage per jasa. Pastikan migration coverage generic sudah diterapkan."}),500


@app.route("/api/leasing/partners", methods=["GET", "POST"])
@leasing_login_required
def leasing_partners():
    if request.method == "POST" and not _is_leasing_admin():
        return jsonify({"success": False, "message": "Hanya admin Leasing yang boleh mengubah master Partner."}), 403
    payload = request.get_json(silent=True) or {}
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if request.method == "POST":
                    name = str(payload.get("partner_name") or "").strip()
                    if not name: return jsonify({"success": False, "message": "partner_name wajib diisi."}), 400
                    cur.execute("""INSERT INTO leasing.partners (partner_name, partner_code, contact_name, contact_email, contact_phone, notes)
                        VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""", (name, payload.get("partner_code"), payload.get("contact_name"), payload.get("contact_email"), payload.get("contact_phone"), payload.get("notes")))
                    partner = dict(cur.fetchone())
                    _leasing_field_audit(cur, "partner", partner["id"], None, "create", session["username"], {},
                        {key: partner.get(key) for key in ("partner_name", "partner_code", "contact_name", "contact_email", "contact_phone", "notes")},
                        "Partner created through Leasing directory")
                    conn.commit()
                    return jsonify({"success": True, "partner": partner}), 201
                cur.execute("SELECT * FROM leasing.partners WHERE is_active=TRUE ORDER BY partner_name")
                return jsonify({"success": True, "partners": [dict(x) for x in cur.fetchall()]})
    except psycopg2.IntegrityError:
        return jsonify({"success": False, "message": "Partner code sudah digunakan."}), 409
    except psycopg2.Error:
        app.logger.exception("Leasing partners query failed")
        return jsonify({"success": False, "message": "Gagal memproses data partner."}), 500


@app.route("/api/leasing/partners/<int:partner_id>", methods=["PATCH"])
@leasing_admin_required
def leasing_update_partner(partner_id):
    """Edit a partner master record without changing historical outreach/offer references."""
    payload = request.get_json(silent=True) or {}
    allowed = {"partner_name", "partner_code", "contact_name", "contact_email", "contact_phone", "notes"}
    if not any(key in payload for key in allowed):
        return jsonify({"success": False, "message": "Tidak ada field partner yang diperbarui."}), 400

    changes = {}
    for key in allowed:
        if key not in payload:
            continue
        value = payload.get(key)
        value = str(value).strip() if value is not None else ""
        changes[key] = value or None
    if "partner_name" in changes and not changes["partner_name"]:
        return jsonify({"success": False, "message": "Nama partner wajib diisi."}), 400
    email = changes.get("contact_email")
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify({"success": False, "message": "Format email kontak tidak valid."}), 400

    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leasing.partners WHERE id=%s AND is_active=TRUE FOR UPDATE", (partner_id,))
                before_partner = cur.fetchone()
                if not before_partner:
                    return jsonify({"success": False, "message": "Partner aktif tidak ditemukan."}), 404
                before_partner = dict(before_partner)
                assignments = [f"{key}=%s" for key in changes]
                values = list(changes.values()) + [partner_id]
                cur.execute(
                    f"UPDATE leasing.partners SET {', '.join(assignments)} WHERE id=%s RETURNING *",
                    values,
                )
                partner = dict(cur.fetchone())
                _leasing_field_audit(cur, "partner", partner_id, None, "update", session["username"],
                    {key: before_partner.get(key) for key in changes},
                    {key: partner.get(key) for key in changes}, "Partner master updated")
            conn.commit()
        return jsonify({"success": True, "partner": partner, "message": "Data partner berhasil diperbarui."})
    except psycopg2.IntegrityError:
        return jsonify({"success": False, "message": "Kode partner sudah digunakan partner lain."}), 409
    except psycopg2.Error:
        app.logger.exception("Leasing partner update failed")
        return jsonify({"success": False, "message": "Gagal memperbarui data partner."}), 500


def _leasing_archive_work_item_in_cursor(cur, work_item_id, actor, reason, typed_request_id=None):
    cur.execute("SELECT id, request_id, archived_at FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
    item = cur.fetchone()
    if not item:
        raise LookupError(f"Work Item ID {work_item_id} tidak ditemukan.")
    if item["archived_at"]:
        raise ValueError(f"Work Item {item['request_id']} sudah diarsipkan.")
    if typed_request_id is not None and str(typed_request_id).strip() != str(item["request_id"]).strip():
        raise ValueError("Request ID yang diketik tidak cocok. Tidak ada data yang diubah.")
    cur.execute("""UPDATE leasing.work_items SET archived_at=NOW(), archived_by=%s,
        archive_reason=%s, updated_at=NOW() WHERE id=%s""", (actor, reason, work_item_id))
    _leasing_field_audit(cur, "work_item", work_item_id, work_item_id, "archive", actor,
                         {"archived_at": None}, {"archived_at": "NOW()", "archive_reason": reason}, reason)
    leasing_activity(cur, work_item_id, "work_item_archived", "Work Item diarsipkan (data dipertahankan)", actor,
                     {"reason": reason, "request_id": item["request_id"]})
    return {"id": work_item_id, "request_id": item["request_id"]}


@app.route("/api/leasing/archived-work-items", methods=["GET"])
@leasing_admin_required
def leasing_archived_work_items():
    page=_leasing_query_int(request.args.get("page"),1,1,100000); size=_leasing_query_int(request.args.get("page_size"),20,10,100)
    q=(request.args.get("q") or "").strip()[:200]; params=[]; where="w.archived_at IS NOT NULL"
    if q:
        where += " AND (w.request_id ILIKE %s OR COALESCE(w.project_name,'') ILIKE %s OR COALESCE(c.customer_name,'') ILIKE %s OR COALESCE(w.archive_reason,'') ILIKE %s)"
        params.extend([f"%{q}%"]*4)
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"SELECT COUNT(*) AS n FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id WHERE {where}",tuple(params)); total=int(cur.fetchone()["n"] or 0)
                pages=max(1,math.ceil(total/size)); page=min(page,pages)
                cur.execute(f"""SELECT w.id,w.request_id,w.project_name,w.work_type,w.buyer_owner_id,w.archived_at,w.archived_by,w.archive_reason,c.customer_name,
                    (SELECT COUNT(*) FROM leasing.requirements r WHERE r.work_item_id=w.id) AS requirement_count
                    FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id WHERE {where}
                    ORDER BY w.archived_at DESC,w.id DESC LIMIT %s OFFSET %s""",tuple(params+[size,(page-1)*size]))
                rows=[dict(x) for x in cur.fetchall()]
        return jsonify({"success":True,"work_items":rows,"pagination":{"page":page,"page_size":size,"total":total,"total_pages":pages}})
    except psycopg2.Error:
        app.logger.exception("Leasing archived Work Item list failed")
        return jsonify({"success":False,"message":"Daftar arsip belum tersedia. Pastikan migration reliability telah diterapkan."}),503


@app.route("/api/leasing/work-items/<int:work_item_id>/restore", methods=["POST"])
@leasing_admin_required
def leasing_restore_work_item(work_item_id):
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 10:
        return jsonify({"success": False, "message": "Alasan restore wajib minimal 10 karakter."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id,request_id,archived_at,archive_reason FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
                item = cur.fetchone()
                if not item: return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                if not item["archived_at"]: return jsonify({"success": False, "message": "Work Item tidak sedang diarsipkan."}), 409
                before = {"archived_at": item["archived_at"], "archive_reason": item["archive_reason"]}
                cur.execute("UPDATE leasing.work_items SET archived_at=NULL, archived_by=NULL, archive_reason=NULL, updated_at=NOW() WHERE id=%s", (work_item_id,))
                _leasing_field_audit(cur, "work_item", work_item_id, work_item_id, "restore", session["username"], before,
                                     {"archived_at": None, "archive_reason": None}, reason)
                leasing_activity(cur, work_item_id, "work_item_restored", "Work Item dipulihkan dari arsip", session["username"], {"reason": reason})
            conn.commit()
        return jsonify({"success": True, "message": f"Work Item {item['request_id']} berhasil dipulihkan."})
    except psycopg2.Error:
        app.logger.exception("Leasing Work Item restore failed")
        return jsonify({"success": False, "message": "Restore gagal; transaksi dibatalkan."}), 500


@app.route("/api/leasing/work-items/<int:work_item_id>", methods=["DELETE"])
@leasing_admin_required
def leasing_delete_work_item(work_item_id):
    """Soft-archive a mistaken Work Item; its history stays recoverable."""
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    typed_request_id = str(payload.get("confirm_request_id") or "").strip()
    if len(reason) < 10:
        return jsonify({"success": False, "message": "Alasan arsip wajib minimal 10 karakter."}), 400
    if not typed_request_id:
        return jsonify({"success": False, "message": "Ketik Request ID untuk mengonfirmasi arsip."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                archived = _leasing_archive_work_item_in_cursor(cur, work_item_id, session["username"], reason, typed_request_id)
            conn.commit()
        return jsonify({"success": True, "archived": [archived], "message": f"Work Item {archived['request_id']} diarsipkan. Data tetap tersimpan dan dapat dipulihkan admin."})
    except LookupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing Work Item archive failed")
        return jsonify({"success": False, "message": "Arsip gagal dan transaksi dibatalkan."}), 500

@app.route("/api/leasing/work-items/bulk-delete", methods=["POST"])
@leasing_admin_required
def leasing_bulk_delete_work_items():
    """Atomically soft-archive selected Work Items; never hard-delete operational data."""
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("work_item_ids")
    reason = str(payload.get("reason") or "").strip()
    confirm_text = str(payload.get("confirm_text") or "").strip()
    if not isinstance(raw_ids, list) or not raw_ids:
        return jsonify({"success": False, "message": "Pilih minimal satu Work Item."}), 400
    if len(raw_ids) > 200:
        return jsonify({"success": False, "message": "Maksimal 200 Work Item per batch arsip."}), 400
    try:
        ids = list(dict.fromkeys(int(value) for value in raw_ids))
        if len(ids) != len(raw_ids) or any(value <= 0 for value in ids): raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Daftar Work Item tidak valid atau berisi ID duplikat."}), 400
    if len(reason) < 10:
        return jsonify({"success": False, "message": "Alasan arsip wajib minimal 10 karakter."}), 400
    if confirm_text != f"ARCHIVE {len(ids)}":
        return jsonify({"success": False, "message": f"Ketik ARCHIVE {len(ids)} untuk mengonfirmasi arsip batch."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM leasing.work_items WHERE id = ANY(%s) AND archived_at IS NULL FOR UPDATE", (ids,))
                found_ids = {int(row["id"]) for row in cur.fetchall()}
                missing = sorted(set(ids) - found_ids)
                if missing: raise LookupError("Sebagian Work Item tidak ditemukan atau sudah diarsipkan: " + ", ".join(map(str, missing)))
                archived = [_leasing_archive_work_item_in_cursor(cur, work_item_id, session["username"], reason) for work_item_id in ids]
            conn.commit()
        return jsonify({"success": True, "archived": archived,
                        "message": f"{len(archived)} Work Item diarsipkan. Data operasional dan histori tetap disimpan; admin dapat memulihkan item."}), 200
    except LookupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing bulk Work Item archive failed")
        return jsonify({"success": False, "message": "Batch arsip gagal; transaksi dibatalkan."}), 500

@app.route("/api/leasing/work-items/<int:work_item_id>/outreaches", methods=["POST"])
@leasing_login_required
def leasing_create_outreach(work_item_id):
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    payload = request.get_json(silent=True) or {}
    try:
        partner_id = int(payload.get("partner_id"))
        response_status = str(payload.get("response_status") or "draft").strip().lower()
        if response_status not in {"draft", "sent", "awaiting_response", "partial_response", "responded", "no_bid", "cancelled"}:
            return jsonify({"success": False, "message": "Status outreach tidak valid."}), 400
        raw_requirement_ids = payload.get("requirement_ids") or []
        if not isinstance(raw_requirement_ids, list):
            raise ValueError("requirement_ids harus berupa daftar.")
        requirement_ids = list(dict.fromkeys(int(x) for x in raw_requirement_ids))
        if not requirement_ids:
            return jsonify({"success": False, "message": "Pilih minimal satu requirement yang benar-benar dikirim ke partner."}), 400
        follow_up_owner_id = str(payload.get("follow_up_owner_id") or session["username"]).strip()
        if not _is_leasing_admin() and follow_up_owner_id != session.get("username"):
            return jsonify({"success": False, "message": "Buyer hanya boleh menugaskan follow-up kepada dirinya sendiri; admin dapat menetapkan PIC lain."}), 403
        if not leasing_owner_is_valid(follow_up_owner_id):
            return jsonify({"success": False, "message": "PIC follow-up tidak ditemukan atau tidak memiliki role Leasing."}), 400
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM leasing.work_items WHERE id=%s AND case_status='open'", (work_item_id,))
                if not cur.fetchone(): return jsonify({"success": False, "message": "Work Item tidak ditemukan atau sudah ditutup."}), 404
                cur.execute("SELECT id FROM leasing.partners WHERE id=%s AND is_active=TRUE", (partner_id,))
                if not cur.fetchone(): return jsonify({"success": False, "message": "Partner tidak ditemukan."}), 404
                if requirement_ids:
                    cur.execute("SELECT id FROM leasing.requirements WHERE work_item_id=%s AND id = ANY(%s)", (work_item_id, requirement_ids))
                    if len(cur.fetchall()) != len(set(requirement_ids)):
                        return jsonify({"success": False, "message": "Ada requirement yang bukan milik Work Item ini."}), 400
                cur.execute("SELECT COALESCE(MAX(outreach_round),0)+1 AS round FROM leasing.partner_outreaches WHERE work_item_id=%s AND partner_id=%s", (work_item_id, partner_id))
                round_no = cur.fetchone()["round"]
                cur.execute("""INSERT INTO leasing.partner_outreaches
                    (work_item_id, partner_id, outreach_round, sent_at, response_status, follow_up_owner_id, next_follow_up_at, notes, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (work_item_id, partner_id, round_no,
                     payload.get("sent_at") or (datetime.now() if response_status in {"sent", "awaiting_response", "partial_response", "responded", "no_bid"} else None),
                     response_status, follow_up_owner_id,
                     payload.get("next_follow_up_at") or None, payload.get("notes"), session["username"]))
                outreach_id = cur.fetchone()["id"]
                for req_id in requirement_ids:
                    cur.execute("INSERT INTO leasing.outreach_requirements (outreach_id, requirement_id, response_status) VALUES (%s,%s,'awaiting_response')", (outreach_id, req_id))
                leasing_activity(cur, work_item_id, "partner_outreach_created", "Outreach partner dicatat", session["username"], {"outreach_id": outreach_id, "partner_id": partner_id})
            conn.commit()
        return jsonify({"success": True, "outreach_id": outreach_id}), 201
    except (TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc) or "partner_id harus berupa angka."}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing outreach create failed")
        return jsonify({"success": False, "message": "Gagal mencatat outreach partner."}), 400


@app.route("/api/leasing/outreaches/<int:outreach_id>", methods=["PATCH"])
@leasing_login_required
def leasing_update_outreach(outreach_id):
    payload = request.get_json(silent=True) or {}
    allowed = {"response_status", "sent_at", "next_follow_up_at", "responded_at", "follow_up_owner_id", "notes"}
    changes = {k: payload[k] for k in allowed if k in payload}
    if not changes:
        return jsonify({"success": False, "message": "Tidak ada field yang diperbarui."}), 400
    allowed_statuses = {"draft", "sent", "awaiting_response", "partial_response", "responded", "no_bid", "cancelled"}
    if "response_status" in changes:
        changes["response_status"] = str(changes["response_status"] or "").strip().lower()
        if changes["response_status"] not in allowed_statuses:
            return jsonify({"success": False, "message": "response_status tidak valid."}), 400
    if "follow_up_owner_id" in changes:
        owner = str(changes.get("follow_up_owner_id") or "").strip()
        if not _is_leasing_admin() and owner and owner != session.get("username"):
            return jsonify({"success": False, "message": "Buyer hanya boleh menugaskan follow-up kepada dirinya sendiri; admin dapat menetapkan PIC lain."}), 403
        if owner and not leasing_owner_is_valid(owner):
            return jsonify({"success": False, "message": "PIC follow-up tidak ditemukan atau tidak memiliki role Leasing."}), 400
        changes["follow_up_owner_id"] = owner or None
    # A blank date from an older frontend should not erase an existing sent timestamp.
    for date_key in ("sent_at", "next_follow_up_at", "responded_at"):
        if date_key in changes and changes[date_key] in (None, ""):
            changes[date_key] = None
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leasing.partner_outreaches WHERE id=%s FOR UPDATE", (outreach_id,))
                row = cur.fetchone()
                if not row:
                    return jsonify({"success": False, "message": "Outreach tidak ditemukan."}), 404
                previous_status = str(row["response_status"] or "draft")
                next_status = changes.get("response_status", previous_status)
                if next_status == "no_bid":
                    # A No Bid disposition may replace a draft/empty offer snapshot, but must not
                    # silently discard a real quote or an explicit can-provide response.
                    cur.execute("""SELECT 1
                        FROM leasing.partner_offers po
                        WHERE po.outreach_id=%s AND po.offer_status='current' AND (
                            EXISTS (SELECT 1 FROM leasing.partner_offer_lines pol
                                WHERE pol.offer_id=po.id AND (
                                    pol.feasibility_status='can_provide' OR pol.mrc_amount IS NOT NULL OR pol.otc_amount IS NOT NULL
                                    OR pol.mrc_inet_dedicated_25_amount IS NOT NULL OR pol.mrc_metro_25_amount IS NOT NULL
                                ))
                            OR EXISTS (SELECT 1 FROM leasing.partner_offer_service_lines osl
                                WHERE osl.offer_id=po.id AND (
                                    osl.feasibility_status='can_provide' OR osl.mrc_amount IS NOT NULL OR osl.otc_amount IS NOT NULL
                                ))
                        ) LIMIT 1""", (outreach_id,))
                    if cur.fetchone():
                        return jsonify({"success": False, "message": "Outreach ini masih memiliki respons Can Provide atau harga aktif. Perbarui/tarik quote dan respons tersebut terlebih dahulu sebelum menandainya No Bid."}), 409
                    cur.execute("""UPDATE leasing.outreach_requirements SET response_status='no_bid',
                        response_note=COALESCE(NULLIF(%s,''),response_note)
                        WHERE outreach_id=%s""", (str(changes.get("notes") or "").strip(), outreach_id))
                    changes["next_follow_up_at"] = None
                    if not row.get("responded_at") and changes.get("responded_at") in (None, ""):
                        changes["responded_at"] = datetime.now()
                elif next_status in {"sent", "awaiting_response", "partial_response", "responded"}:
                    # When a draft is sent by changing the status in the UI, timestamp it even
                    # though the current editor does not expose a sent-at field.
                    if not row.get("sent_at") and changes.get("sent_at") in (None, ""):
                        changes["sent_at"] = datetime.now()
                    if previous_status in {"draft", "no_bid", "cancelled"}:
                        cur.execute("""UPDATE leasing.outreach_requirements SET response_status='awaiting_response',
                            response_note=NULL, sent_at=COALESCE(sent_at,%s)
                            WHERE outreach_id=%s AND response_status='no_bid'""", (changes.get("sent_at") or datetime.now(), outreach_id))
                if next_status == "responded" and not row.get("responded_at") and changes.get("responded_at") in (None, ""):
                    changes["responded_at"] = datetime.now()
                if next_status in {"responded", "no_bid", "cancelled"}:
                    changes["next_follow_up_at"] = None
                sets, vals = [], []
                for key, value in changes.items():
                    sets.append(f"{key}=%s")
                    vals.append(value)
                sets.append("updated_at=NOW()")
                vals.append(outreach_id)
                cur.execute(f"UPDATE leasing.partner_outreaches SET {', '.join(sets)} WHERE id=%s RETURNING *", vals)
                updated_outreach = dict(cur.fetchone())
                audit_keys = set(changes) | {"response_status", "sent_at", "responded_at", "next_follow_up_at", "follow_up_owner_id", "notes"}
                _leasing_field_audit(cur, "partner_outreach", outreach_id, row["work_item_id"], "update", session["username"],
                    {key: row.get(key) for key in audit_keys}, {key: updated_outreach.get(key) for key in audit_keys},
                    str(payload.get("audit_reason") or "Partner outreach status/follow-up updated").strip()[:1000])
                leasing_activity(cur, row["work_item_id"], "partner_outreach_updated", "Status atau follow-up partner diperbarui", session["username"], changes)
            conn.commit()
        return jsonify({"success": True})
    except psycopg2.Error:
        app.logger.exception("Leasing outreach update failed")
        return jsonify({"success": False, "message": "Gagal memperbarui outreach."}), 400


@app.route("/api/leasing/outreaches/<int:outreach_id>/offers", methods=["POST"])
@leasing_login_required
def leasing_create_offer(outreach_id):
    payload = request.get_json(silent=True) or {}
    lines = payload.get("lines") or []
    service_lines = payload.get("service_lines") or []
    if not isinstance(lines, list) or not isinstance(service_lines, list):
        return jsonify({"success": False, "message": "Format baris penawaran tidak valid."}), 400
    if not lines and not service_lines:
        return jsonify({"success": False, "message": "Minimal satu baris respons site atau jasa harus dicatat."}), 400
    allowed_feasibility = {"pending", "can_provide", "cannot_provide", "needs_clarification"}
    try:
        normalized_lines = []
        seen = set()
        for index, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise ValueError(f"Baris {index}: format line harus berupa object.")
            requirement_id = int(line.get("requirement_id"))
            if requirement_id in seen:
                raise ValueError(f"Requirement ID {requirement_id} muncul lebih dari sekali.")
            seen.add(requirement_id)
            feasibility = str(line.get("feasibility_status") or "pending").strip().lower()
            if feasibility not in allowed_feasibility:
                raise ValueError(f"Baris {index}: status feasibility tidak valid.")
            amounts = {}
            price_fields = (("mrc_amount", "MRC"), ("mrc_inet_dedicated_25_amount", "MRC Inet Dedicated 25 Mbps"),
                            ("mrc_metro_25_amount", "MRC Metro 25 Mbps"), ("otc_amount", "OTC"))
            for field, label in price_fields:
                raw = line.get(field)
                if raw in (None, ""):
                    amounts[field] = None
                else:
                    try: number = float(raw)
                    except (TypeError, ValueError): raise ValueError(f"Baris {index}: {label} harus berupa angka.")
                    if not math.isfinite(number) or number < 0:
                        raise ValueError(f"Baris {index}: {label} tidak boleh negatif dan harus berupa angka valid.")
                    amounts[field] = number
            currency = str(line.get("currency") or "").strip().upper()
            notes = str(line.get("notes") or "").strip() or None
            clear_existing_prices = line.get("clear_existing_prices") is True or str(line.get("clear_existing_prices") or "").strip().lower() in {"1", "true", "yes", "on"}
            has_price = any(amounts[field] is not None for field, _ in price_fields)
            if has_price and feasibility == "pending":
                raise ValueError(f"Baris {index}: pilih Can Provide sebelum memasukkan harga.")
            if has_price and feasibility == "cannot_provide":
                raise ValueError(f"Baris {index}: harga tidak boleh diisi jika status Cannot Provide.")
            if has_price:
                if not re.fullmatch(r"[A-Z]{3}", currency):
                    raise ValueError(f"Baris {index}: currency wajib berupa kode 3 huruf saat harga diisi.")
            else:
                currency = None
            if feasibility == "pending" and not notes and not clear_existing_prices:
                continue
            normalized_lines.append({"requirement_id": requirement_id, **amounts, "feasibility_status": feasibility,
                                     "currency": currency, "notes": notes, "clear_existing_prices": clear_existing_prices})
        normalized_service_lines = service_lines
        if not normalized_lines and not normalized_service_lines:
            raise ValueError("Isi setidaknya satu hasil penawaran.")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                result = _leasing_record_offer_version(
                    cur, outreach_id, normalized_lines, session["username"], "manual",
                    offer_notes=payload.get("notes"), received_at=payload.get("received_at"),
                    valid_until=payload.get("valid_until"), source_label="manual input",
                    incoming_service_lines=normalized_service_lines)
            conn.commit()
        return jsonify({"success": True, **result}), 201
    except LookupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc) or "Format offer tidak valid."}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing offer save failed")
        return jsonify({"success": False, "message": "Gagal mencatat penawaran partner."}), 400


@app.route("/api/leasing/work-items/<int:work_item_id>/commercial-targets", methods=["GET", "POST"])
@leasing_login_required
def leasing_commercial_targets(work_item_id):
    # Targets are buyer/admin commercial data. Delegated follow-up PICs do not receive
    # targets via this standalone API, even if they can open limited outreach context.
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    if request.method == "GET":
        try:
            with get_leasing_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""SELECT ct.*, r.requirement_no, r.gedung_kawasan, r.address, r.site_name, r.zone, r.postal_code
                        FROM leasing.commercial_targets ct LEFT JOIN leasing.requirements r ON r.id=ct.requirement_id
                        WHERE ct.work_item_id=%s ORDER BY ct.requirement_id NULLS FIRST, ct.metric, ct.created_at DESC""", (work_item_id,))
                    return jsonify({"success": True, "commercial_targets": [dict(x) for x in cur.fetchall()]})
        except psycopg2.Error:
            app.logger.exception("Leasing commercial targets query failed")
            return jsonify({"success": False, "message": "Gagal memuat commercial target."}), 500

    payload = request.get_json(silent=True) or {}
    metric = str(payload.get("metric") or "").strip().lower()
    if metric not in {"mrc", "otc"}:
        return jsonify({"success": False, "message": "metric harus mrc atau otc."}), 400
    try:
        amount = float(payload.get("target_amount"))
        if not math.isfinite(amount) or amount < 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "target_amount harus angka non-negatif."}), 400
    currency = str(payload.get("currency") or "IDR").strip().upper()
    if not re.fullmatch(r"[A-Z]{3}", currency):
        return jsonify({"success": False, "message": "currency harus kode 3 huruf, misalnya IDR."}), 400
    service_name = str(payload.get("service_name") or "").strip() or None
    if service_name and len(service_name) > 160:
        return jsonify({"success": False, "message": "Nama jasa maksimal 160 karakter."}), 400
    raw_target_ids = payload.get("requirement_ids")
    if raw_target_ids is None and payload.get("requirement_id") not in (None, ""):
        raw_target_ids = [payload.get("requirement_id")]
    scope = str(payload.get("scope") or ("selected" if raw_target_ids else "work_item")).strip().lower()
    requirement_ids = []
    if scope == "selected":
        raw_ids = raw_target_ids
        if not isinstance(raw_ids, list) or not raw_ids:
            return jsonify({"success": False, "message": "Pilih minimal satu requirement untuk target terpilih."}), 400
        if len(raw_ids) > 3000:
            return jsonify({"success": False, "message": "Maksimal 3.000 requirement per operasi target."}), 400
        try:
            requirement_ids = list(dict.fromkeys(int(value) for value in raw_ids))
            if len(requirement_ids) != len(raw_ids) or any(value <= 0 for value in requirement_ids):
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Daftar requirement tidak valid atau berisi ID duplikat."}), 400
    elif scope != "work_item":
        return jsonify({"success": False, "message": "scope harus work_item atau selected."}), 400

    target_source = str(payload.get("target_source") or "requester").strip().lower()
    if target_source not in {"requester", "buyer_benchmark", "other"}:
        return jsonify({"success": False, "message": "Sumber target tidak valid."}), 400
    notes = str(payload.get("notes") or "").strip() or None
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
                if not cur.fetchone():
                    return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                if requirement_ids:
                    cur.execute("SELECT id, requested_services, service_type FROM leasing.requirements WHERE work_item_id=%s AND id = ANY(%s)", (work_item_id, requirement_ids))
                    target_requirements = [dict(row) for row in cur.fetchall()]
                    found = {int(row["id"]) for row in target_requirements}
                    missing = sorted(set(requirement_ids) - found)
                    if missing:
                        return jsonify({"success": False, "message": "Ada requirement yang bukan milik Work Item ini: " + ", ".join(map(str, missing))}), 400
                    if service_name:
                        service_key = re.sub(r"\s+", " ", service_name).strip().casefold()
                        mismatched = []
                        for target_requirement in target_requirements:
                            names = _leasing_normalize_service_names(target_requirement.get("requested_services"), target_requirement.get("service_type"))
                            if service_key not in {re.sub(r"\s+", " ", name).strip().casefold() for name in names}:
                                mismatched.append(int(target_requirement["id"]))
                        if mismatched:
                            return jsonify({"success": False, "message": "Target jasa spesifik hanya bisa diterapkan ke site yang meminta jasa tersebut. Site tidak cocok: " + ", ".join(map(str, mismatched)) + ". Kosongkan Nama jasa untuk target umum."}), 400
                    target_scopes = requirement_ids
                else:
                    target_scopes = [None]
                    if service_name:
                        cur.execute("SELECT requested_services, service_type FROM leasing.requirements WHERE work_item_id=%s", (work_item_id,))
                        service_key = re.sub(r"\s+", " ", service_name).strip().casefold()
                        present_anywhere = any(
                            service_key in {re.sub(r"\s+", " ", item).strip().casefold()
                                            for item in _leasing_normalize_service_names(row.get("requested_services"), row.get("service_type"))}
                            for row in cur.fetchall()
                        )
                        if not present_anywhere:
                            return jsonify({"success": False, "message": "Nama jasa target tidak ditemukan pada requirement Work Item ini. Pilih nama jasa yang diminta atau kosongkan Nama jasa untuk target umum."}), 400
                created_ids = []
                for requirement_id in target_scopes:
                    cur.execute("""INSERT INTO leasing.commercial_targets
                        (work_item_id, requirement_id, metric, target_amount, currency, target_source, notes, created_by, service_name)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (work_item_id, requirement_id, metric, amount, currency,
                         target_source, notes, session["username"], service_name))
                    target_id = int(cur.fetchone()["id"])
                    created_ids.append(target_id)
                    _leasing_field_audit(cur, "commercial_target", target_id, work_item_id, "create", session["username"], {},
                        {"requirement_id": requirement_id, "metric": metric, "target_amount": amount, "currency": currency,
                         "target_source": target_source, "notes": notes, "service_name": service_name}, "Commercial target created")
                leasing_activity(cur, work_item_id, "commercial_target_recorded",
                    f"Target komersial {metric.upper()} dicatat untuk {len(created_ids)} cakupan",
                    session["username"], {"target_ids": created_ids, "metric": metric, "target_amount": amount,
                    "currency": currency, "service_name": service_name, "scope": scope, "requirement_ids": requirement_ids})
            conn.commit()
        return jsonify({"success": True, "target_ids": created_ids, "created_count": len(created_ids)}), 201
    except psycopg2.Error:
        app.logger.exception("Leasing commercial target save failed")
        return jsonify({"success": False, "message": "Gagal menyimpan commercial target."}), 400


# ==========================================================================
# Service-agnostic bulk Commercial Target workbook
# Each row represents a target scoped to Work Item or Site + Service + Metric.
# Empty edit cells mean unchanged; [[CLEAR]] can only clear Notes.
# ==========================================================================
def _leasing_target_service_key(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold()


def _leasing_target_workbook(cur, work_item_id):
    cur.execute("SELECT id, request_id, project_name, work_type FROM leasing.work_items WHERE id=%s", (work_item_id,))
    item = cur.fetchone()
    if not item:
        raise LookupError("Work Item tidak ditemukan.")
    cur.execute("""SELECT id, requirement_no, site_name, zone, address, requested_services, service_type
        FROM leasing.requirements WHERE work_item_id=%s ORDER BY requirement_no, id""", (work_item_id,))
    requirements = [dict(row) for row in cur.fetchall()]
    cur.execute("""SELECT * FROM leasing.commercial_targets WHERE work_item_id=%s
        ORDER BY created_at DESC, id DESC""", (work_item_id,))
    latest_targets = {}
    for row in cur.fetchall():
        record = dict(row)
        key = (int(record["requirement_id"]) if record.get("requirement_id") is not None else None,
               str(record.get("metric") or "").lower(), _leasing_target_service_key(record.get("service_name")))
        latest_targets.setdefault(key, record)

    service_names_by_key = {}
    normalized_requirements = {}
    for requirement in requirements:
        services = _leasing_normalize_service_names(requirement.get("requested_services"), requirement.get("service_type"))
        normalized_requirements[int(requirement["id"])] = services
        for service in services:
            service_names_by_key.setdefault(_leasing_target_service_key(service), service)
    all_services = sorted(service_names_by_key.values(), key=lambda value: value.casefold())
    scope_services = [""] + all_services

    wb = Workbook()
    ws = wb.active
    ws.title = "Service Targets"
    headers = ["Scope", "Requirement ID", "Requirement No", "Site / Requirement", "Service Name", "Metric",
               "Current Target", "Current Currency", "Current Source", "Current Notes",
               "Target Amount (edit)", "Currency (edit)", "Target Source (edit)", "Notes (edit)"]
    ws.append(headers)

    def append_target_row(scope, requirement=None, service_name="", metric="mrc"):
        requirement_id = int(requirement["id"]) if requirement else None
        key = (requirement_id, metric, _leasing_target_service_key(service_name))
        current = latest_targets.get(key, {})
        site_label = "Seluruh Work Item" if requirement is None else (
            f"#{requirement.get('requirement_no')} · " + str(requirement.get("site_name") or requirement.get("address") or requirement.get("zone") or "Requirement")
        )
        ws.append([
            scope, requirement_id, requirement.get("requirement_no") if requirement else None,
            site_label, service_name, metric.upper(), current.get("target_amount"),
            str(current.get("currency") or "").strip() or None,
            current.get("target_source"), current.get("notes"), None, None, None, None,
        ])

    for service_name in scope_services:
        for metric in ("mrc", "otc"):
            append_target_row("work_item", None, service_name, metric)
    for requirement in requirements:
        requirement_services = [""] + normalized_requirements[int(requirement["id"])]
        for service_name in requirement_services:
            for metric in ("mrc", "otc"):
                append_target_row("site", requirement, service_name, metric)

    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    widths = [14, 16, 16, 34, 28, 12, 20, 16, 20, 36, 22, 18, 22, 36]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + idx)].width = width
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="35266E")
        cell.alignment = Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[1].height = 34
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in {4, 9, 10, 14})
        if row[6].value is not None:
            row[6].number_format = '#,##0.00;[Red](#,##0.00);-'
    try:
        from openpyxl.worksheet.datavalidation import DataValidation
        scope_dv = DataValidation(type="list", formula1='"work_item,site"', allow_blank=False)
        metric_dv = DataValidation(type="list", formula1='"MRC,OTC"', allow_blank=False)
        source_dv = DataValidation(type="list", formula1='"requester,buyer_benchmark,other"', allow_blank=True)
        ws.add_data_validation(scope_dv); scope_dv.add(f"A2:A{max(2,ws.max_row)}")
        ws.add_data_validation(metric_dv); metric_dv.add(f"F2:F{max(2,ws.max_row)}")
        ws.add_data_validation(source_dv); source_dv.add(f"M2:M{max(2,ws.max_row)}")
    except Exception:
        app.logger.exception("Commercial target workbook validation setup failed")

    guide = wb.create_sheet("Petunjuk")
    guide.append(["Topik", "Panduan"])
    for row in [
        ("Tujuan", "Template ini berlaku untuk semua jenis jasa. Satu baris = satu Scope + Site/Work Item + Service Name + Metric."),
        ("Jenis jasa", "Nama jasa bebas dan tidak dibatasi Metro E atau Internet Dedicated. Nama harus sama dengan Requested Services (huruf besar/kecil tidak berpengaruh)."),
        ("Scope", "work_item = target umum untuk semua Work Item; site = target untuk satu Requirement ID tertentu."),
        ("Metric", "Pilih MRC atau OTC."),
        ("Edit cells", "Isi Target Amount (edit) untuk menetapkan target baru. Currency edit wajib jika target baru belum memiliki target sebelumnya; jika ada, currency lama boleh dipakai dengan membiarkan kolom ini kosong."),
        ("Cell kosong", "Kolom edit yang kosong berarti tidak diubah. Current Target/Currency/Source/Notes hanya informasi, bukan kolom untuk diedit."),
        ("Catatan", "Untuk mengganti catatan, isi Notes (edit). Ketik [[CLEAR]] hanya jika sengaja ingin mengosongkan catatan. Catatan kosong berarti pertahankan nilai lama."),
        ("Target source", "requester, buyer_benchmark, atau other. Sel kosong mempertahankan sumber lama atau default requester."),
        ("Validasi", "Requirement ID harus berasal dari Work Item yang sama. Nama jasa harus diminta pada site terkait. Metric duplikat untuk scope/site+jasa yang sama dalam satu upload ditolak."),
        ("Versi dan audit", "Setiap perubahan yang benar-benar berbeda membuat record target baru agar nilai sebelumnya tetap punya jejak. Upload identik diblokir agar tidak membuat versi ganda."),
        ("Batas", "Maksimal 20.000 baris data per import. Ubah file yang telah disimpan jika perlu mengulang import, atau download template baru untuk memperoleh nilai current terbaru."),
    ]: guide.append(list(row))
    guide.column_dimensions["A"].width = 26; guide.column_dimensions["B"].width = 115
    guide.freeze_panes = "A2"
    for cell in guide[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="35266E")
    for row in guide.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    for idx in range(2, guide.max_row + 1): guide.row_dimensions[idx].height = 34

    output = BytesIO(); wb.save(output); output.seek(0)
    return item, len(requirements), output


@app.route("/api/leasing/work-items/<int:work_item_id>/commercial-targets.xlsx", methods=["GET"])
@leasing_login_required
def leasing_commercial_targets_xlsx(work_item_id):
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                item, req_count, output = _leasing_target_workbook(cur, work_item_id)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(item.get("request_id") or work_item_id))
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=f"commercial_targets_{safe_id}_{req_count}_requirements.xlsx")
    except LookupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except Exception:
        app.logger.exception("Leasing commercial target template export failed")
        return jsonify({"success": False, "message": "Gagal membuat template commercial target. Periksa schema/migration dan log aplikasi."}), 500


@app.route("/api/leasing/work-items/<int:work_item_id>/commercial-targets/import", methods=["POST"])
@leasing_login_required
def leasing_commercial_targets_import(work_item_id):
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    file_obj = request.files.get("file")
    if not file_obj or not (file_obj.filename or "").lower().endswith(".xlsx"):
        return jsonify({"success": False, "message": "Pilih workbook .xlsx hasil Download bulk commercial target."}), 400
    content = file_obj.read()
    if not content:
        return jsonify({"success": False, "message": "File Excel kosong."}), 400
    if len(content) > 16 * 1024 * 1024:
        return jsonify({"success": False, "message": "File melebihi batas 16 MB."}), 413
    fingerprint = hashlib.sha256(content).hexdigest()
    try:
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
        if "Service Targets" not in wb.sheetnames:
            wb.close()
            return jsonify({"success": False, "message": "Sheet 'Service Targets' tidak ditemukan. Download template terbaru."}), 400
        ws = wb["Service Targets"]
        raw_headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        header_map = {_leasing_header_key(header): idx for idx, header in enumerate(raw_headers) if header is not None}
        required_headers = {"scope", "requirement_id", "service_name", "metric", "target_amount_edit", "currency_edit", "target_source_edit", "notes_edit"}
        missing_headers = sorted(required_headers - set(header_map))
        if missing_headers:
            wb.close()
            return jsonify({"success": False, "message": "Kolom wajib hilang: " + ", ".join(missing_headers)}), 400
        raw_ops, issues, seen = [], [], set()
        for excel_row_no, values in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if excel_row_no > 20002:
                issues.append("Maksimal 20.000 baris data per import."); break
            if not any(v not in (None, "") for v in values):
                continue
            def cell(name):
                idx = header_map[name]
                return values[idx] if idx < len(values) else None
            amount_raw, currency_raw = cell("target_amount_edit"), cell("currency_edit")
            source_raw, notes_raw = cell("target_source_edit"), cell("notes_edit")
            has_edit = any(v not in (None, "") and not (isinstance(v, str) and not v.strip())
                           for v in (amount_raw, currency_raw, source_raw, notes_raw))
            if not has_edit:
                continue
            scope = str(cell("scope") or "").strip().lower()
            metric = str(cell("metric") or "").strip().lower()
            service_name = re.sub(r"\s+", " ", str(cell("service_name") or "")).strip()
            rid_raw = cell("requirement_id")
            if scope not in {"work_item", "site"}:
                issues.append(f"Baris {excel_row_no}: Scope harus work_item atau site."); continue
            if metric not in {"mrc", "otc"}:
                issues.append(f"Baris {excel_row_no}: Metric harus MRC atau OTC."); continue
            if len(service_name) > 160:
                issues.append(f"Baris {excel_row_no}: Nama jasa maksimal 160 karakter."); continue
            req_id = None
            if scope == "site":
                try:
                    req_id = int(rid_raw)
                    if float(rid_raw) != req_id or req_id <= 0: raise ValueError
                except (TypeError, ValueError):
                    issues.append(f"Baris {excel_row_no}: Requirement ID wajib berupa bilangan bulat positif untuk scope site."); continue
            elif rid_raw not in (None, ""):
                issues.append(f"Baris {excel_row_no}: Requirement ID harus kosong untuk scope work_item."); continue
            key = (scope, req_id, _leasing_target_service_key(service_name), metric)
            if key in seen:
                issues.append(f"Baris {excel_row_no}: Kombinasi Scope/Requirement/Service/Metric duplikat pada file."); continue
            seen.add(key)
            amount = None
            if amount_raw not in (None, "") and not (isinstance(amount_raw, str) and not amount_raw.strip()):
                try:
                    amount = float(amount_raw)
                    if not math.isfinite(amount) or amount < 0: raise ValueError
                except (TypeError, ValueError):
                    issues.append(f"Baris {excel_row_no}: Target Amount harus angka non-negatif."); continue
            currency = str(currency_raw or "").strip().upper() or None
            if currency and not re.fullmatch(r"[A-Z]{3}", currency):
                issues.append(f"Baris {excel_row_no}: Currency harus kode 3 huruf."); continue
            target_source = str(source_raw or "").strip().lower() or None
            if target_source and target_source not in {"requester", "buyer_benchmark", "other"}:
                issues.append(f"Baris {excel_row_no}: Target Source tidak valid."); continue
            notes = None
            notes_action = "unchanged"
            if notes_raw not in (None, "") and not (isinstance(notes_raw, str) and not notes_raw.strip()):
                if isinstance(notes_raw, str) and notes_raw.strip().lower() == "[[clear]]":
                    notes_action = "clear"
                else:
                    notes = str(notes_raw).strip()
                    notes_action = "set"
                    if len(notes) > 4000:
                        issues.append(f"Baris {excel_row_no}: Notes maksimal 4.000 karakter."); continue
            raw_ops.append({"excel_row": excel_row_no, "scope": scope, "requirement_id": req_id,
                            "service_name": service_name, "service_key": _leasing_target_service_key(service_name),
                            "metric": metric, "amount": amount, "currency": currency,
                            "target_source": target_source, "notes": notes, "notes_action": notes_action})
        wb.close()
        if issues:
            return jsonify({"success": False, "message": "Workbook belum valid; tidak ada target yang disimpan.", "issues": issues[:100]}), 400
        if not raw_ops:
            return jsonify({"success": False, "message": "Tidak ada perubahan. Isi minimal satu kolom edit pada satu baris."}), 400

        prepared = []
        created_ids = []
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, request_id FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
                item = cur.fetchone()
                if not item:
                    return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                cur.execute("SELECT id, requirement_no, requested_services, service_type FROM leasing.requirements WHERE work_item_id=%s ORDER BY requirement_no", (work_item_id,))
                requirement_rows = [dict(row) for row in cur.fetchall()]
                req_by_id = {int(row["id"]): row for row in requirement_rows}
                all_services_by_key = {}
                services_by_req = {}
                for req in requirement_rows:
                    names = _leasing_normalize_service_names(req.get("requested_services"), req.get("service_type"))
                    services_by_req[int(req["id"])] = names
                    for name in names: all_services_by_key.setdefault(_leasing_target_service_key(name), name)
                cur.execute("""SELECT * FROM leasing.commercial_targets WHERE work_item_id=%s
                    ORDER BY created_at DESC,id DESC FOR UPDATE""", (work_item_id,))
                current_map = {}
                for target in cur.fetchall():
                    record = dict(target)
                    key = (int(record["requirement_id"]) if record.get("requirement_id") is not None else None,
                           str(record.get("metric") or "").lower(), _leasing_target_service_key(record.get("service_name")))
                    current_map.setdefault(key, record)
                for op in raw_ops:
                    req_id = op["requirement_id"] if op["scope"] == "site" else None
                    if req_id is not None and req_id not in req_by_id:
                        issues.append(f"Baris {op['excel_row']}: Requirement ID {req_id} bukan milik Work Item ini."); continue
                    if op["service_key"]:
                        allowed_services = services_by_req.get(req_id, []) if req_id is not None else list(all_services_by_key.values())
                        canonical = next((name for name in allowed_services if _leasing_target_service_key(name) == op["service_key"]), None)
                        if canonical is None:
                            issues.append(f"Baris {op['excel_row']}: Jasa '{op['service_name']}' tidak diminta pada cakupan ini."); continue
                        op["service_name"] = canonical
                        op["service_key"] = _leasing_target_service_key(canonical)
                    current_key = (req_id, op["metric"], op["service_key"])
                    current = current_map.get(current_key)
                    amount = op["amount"]
                    currency = op["currency"]
                    if amount is None:
                        if current is None:
                            issues.append(f"Baris {op['excel_row']}: target belum ada; isi Target Amount untuk membuatnya."); continue
                        amount = float(current["target_amount"])
                        current_currency = str(current.get("currency") or "").strip().upper()
                        if currency and currency != current_currency:
                            issues.append(f"Baris {op['excel_row']}: perubahan currency wajib disertai Target Amount baru."); continue
                        currency = current_currency
                    elif currency is None:
                        if current is None:
                            issues.append(f"Baris {op['excel_row']}: Currency wajib diisi untuk target baru."); continue
                        currency = str(current.get("currency") or "").strip().upper()
                    if not currency or not re.fullmatch(r"[A-Z]{3}", currency):
                        issues.append(f"Baris {op['excel_row']}: Currency wajib berupa kode 3 huruf."); continue
                    target_source = op["target_source"] or (current.get("target_source") if current else "requester")
                    if op["notes_action"] == "clear": notes = None
                    elif op["notes_action"] == "set": notes = op["notes"]
                    else: notes = current.get("notes") if current else None
                    # Do not append a duplicate version for an unchanged row.
                    if current and float(current["target_amount"]) == float(amount) and str(current.get("currency") or "").strip().upper() == currency and (current.get("target_source") or "requester") == target_source and (current.get("notes") or None) == (notes or None):
                        continue
                    prepared.append({"requirement_id": req_id, "metric": op["metric"], "service_name": op["service_name"] or None,
                                     "target_amount": amount, "currency": currency, "target_source": target_source,
                                     "notes": notes, "excel_row": op["excel_row"]})
                if issues:
                    return jsonify({"success": False, "message": "Validasi scope target gagal; tidak ada perubahan yang disimpan.", "issues": issues[:100]}), 400
                if not prepared:
                    return jsonify({"success": True, "created_count": 0, "message": "Semua nilai yang diisi sama dengan target saat ini; tidak ada versi baru dibuat."})
                cur.execute("""SELECT id FROM leasing.import_batches WHERE fingerprint=%s AND uploaded_by=%s AND allow_duplicate=FALSE LIMIT 1""", (fingerprint, session["username"]))
                if cur.fetchone():
                    return jsonify({"success": False, "message": "File ini sudah pernah diimpor oleh akunmu. Download template terbaru atau simpan perubahan workbook sebagai file baru."}), 409
                for row in prepared:
                    cur.execute("""INSERT INTO leasing.commercial_targets
                        (work_item_id, requirement_id, metric, target_amount, currency, target_source, notes, created_by, service_name)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (work_item_id, row["requirement_id"], row["metric"], row["target_amount"], row["currency"],
                         row["target_source"], row["notes"], session["username"], row["service_name"]))
                    target_id = int(cur.fetchone()["id"])
                    created_ids.append(target_id)
                    _leasing_field_audit(cur, "commercial_target", target_id, work_item_id, "create", session["username"], {},
                        {key: row.get(key) for key in ("requirement_id", "metric", "target_amount", "currency", "target_source", "notes", "service_name")},
                        f"Bulk Commercial Target import row {row.get('excel_row')}")
                cur.execute("""INSERT INTO leasing.import_batches
                    (fingerprint,uploaded_by,source_filename,grouping_mode,work_item_ids,created_count,requirement_count,allow_duplicate,metadata)
                    VALUES (%s,%s,%s,'commercial_targets',%s,%s,0,FALSE,%s::jsonb)""",
                    (fingerprint, session["username"], secure_filename(file_obj.filename or "commercial_targets.xlsx"),
                     [work_item_id], len(created_ids), json.dumps({"kind":"commercial_targets","target_ids":created_ids,"request_id":item["request_id"]})))
                leasing_activity(cur, work_item_id, "commercial_targets_bulk_imported",
                    f"{len(created_ids)} commercial target diimpor melalui Excel", session["username"],
                    {"target_ids": created_ids, "source_filename": secure_filename(file_obj.filename or "commercial_targets.xlsx")})
            conn.commit()
        return jsonify({"success": True, "created_count": len(created_ids), "target_ids": created_ids,
                        "message": f"{len(created_ids)} target berhasil diperbarui; nilai lama tetap dapat ditelusuri sebagai versi sebelumnya."}), 201
    except psycopg2.IntegrityError:
        app.logger.exception("Leasing commercial target import integrity conflict")
        return jsonify({"success": False, "message": "File target ini kemungkinan diimpor bersamaan dari sesi lain; tidak ada perubahan disimpan. Download template terbaru dan coba kembali."}), 409
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc) or "Workbook commercial target tidak valid."}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing commercial target import database error")
        return jsonify({"success": False, "message": "Gagal mengimpor commercial target. Tidak ada perubahan disimpan; periksa log aplikasi."}), 500
    except Exception:
        app.logger.exception("Leasing commercial target import failed unexpectedly")
        return jsonify({"success": False, "message": "Gagal memproses workbook commercial target. Tidak ada perubahan disimpan."}), 400


@app.route("/api/leasing/offer-lines/<int:offer_line_id>/negotiations", methods=["POST"])
@leasing_login_required
def leasing_create_negotiation_event(offer_line_id):
    payload = request.get_json(silent=True) or {}
    event_type = payload.get("event_type", "note")
    allowed_types = {"initial_offer", "counter_offer", "partner_revision", "agreed", "rejected", "note"}
    if event_type not in allowed_types:
        return jsonify({"success": False, "message": "Jenis event negosiasi tidak valid."}), 400
    def optional_nonnegative_number(value, field_name):
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{field_name} harus berupa angka.")
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{field_name} harus angka terbatas dan tidak boleh negatif.")
        return number
    try:
        mrc = optional_nonnegative_number(payload.get("mrc_amount"), "MRC")
        inet_mrc = optional_nonnegative_number(payload.get("mrc_inet_dedicated_25_amount"), "MRC Inet Dedicated 25 Mbps")
        metro_mrc = optional_nonnegative_number(payload.get("mrc_metro_25_amount"), "MRC Metro 25 Mbps")
        otc = optional_nonnegative_number(payload.get("otc_amount"), "OTC")
        has_amount = any(x is not None for x in (mrc, inet_mrc, metro_mrc, otc))
        currency = (str(payload.get("currency") or "IDR").strip().upper() if has_amount else None)
        if currency is not None and not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Currency harus berupa kode 3 huruf.")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT o.work_item_id, po.offer_status FROM leasing.partner_offer_lines pol
                    JOIN leasing.partner_offers po ON po.id=pol.offer_id
                    JOIN leasing.partner_outreaches o ON o.id=po.outreach_id WHERE pol.id=%s""", (offer_line_id,))
                line = cur.fetchone()
                if not line:
                    return jsonify({"success": False, "message": "Offer line tidak ditemukan."}), 404
                if line["offer_status"] != "current":
                    return jsonify({"success": False, "message": "Negosiasi harus dicatat pada versi penawaran aktif. Muat ulang detail Work Item."}), 409
                if not has_amount and not str(payload.get("notes") or "").strip() and event_type not in {"agreed", "rejected"}:
                    return jsonify({"success": False, "message": "Isi harga baru atau catatan untuk event negosiasi ini."}), 400
                cur.execute("""INSERT INTO leasing.negotiation_events
                    (offer_line_id, event_type, mrc_amount, mrc_inet_dedicated_25_amount,
                     mrc_metro_25_amount, otc_amount, currency, notes, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (offer_line_id, event_type, mrc, inet_mrc, metro_mrc, otc, currency, payload.get("notes"), session["username"]))
                event_id = cur.fetchone()["id"]
                leasing_activity(cur, line["work_item_id"], "negotiation_event_recorded", "Event negosiasi dicatat", session["username"],
                                 {"negotiation_event_id": event_id, "offer_line_id": offer_line_id, "event_type": event_type})
            conn.commit()
        return jsonify({"success": True, "event_id": event_id}), 201
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing negotiation event save failed")
        return jsonify({"success": False, "message": "Gagal mencatat event negosiasi."}), 400


@app.route("/api/leasing/service-offer-lines/<int:service_line_id>/negotiations", methods=["POST"])
@leasing_login_required
def leasing_create_service_negotiation_event(service_line_id):
    payload = request.get_json(silent=True) or {}
    event_type = str(payload.get("event_type") or "note").strip()
    allowed_types = {"initial_offer", "counter_offer", "partner_revision", "agreed", "rejected", "note"}
    if event_type not in allowed_types:
        return jsonify({"success": False, "message": "Jenis event negosiasi tidak valid."}), 400

    def optional_nonnegative_number(value, label):
        if value is None or value == "":
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"{label} harus berupa angka.")
        if not math.isfinite(number) or number < 0:
            raise ValueError(f"{label} harus angka nol atau lebih.")
        return number

    try:
        mrc = optional_nonnegative_number(payload.get("mrc_amount"), "MRC")
        otc = optional_nonnegative_number(payload.get("otc_amount"), "OTC")
        has_price = mrc is not None or otc is not None
        currency = str(payload.get("currency") or "").strip().upper() or None
        if has_price and (not currency or not re.fullmatch(r"[A-Z]{3}", currency)):
            raise ValueError("Currency harus berupa kode 3 huruf saat harga negosiasi diisi.")
        notes = str(payload.get("notes") or "").strip() or None
        if not has_price and not notes and event_type not in {"agreed", "rejected"}:
            raise ValueError("Isi harga baru atau catatan untuk event negosiasi ini.")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT o.work_item_id, po.offer_status, osl.requirement_id, osl.service_name,
                    p.partner_name, r.requirement_no
                    FROM leasing.partner_offer_service_lines osl
                    JOIN leasing.partner_offers po ON po.id=osl.offer_id
                    JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                    JOIN leasing.partners p ON p.id=o.partner_id
                    JOIN leasing.requirements r ON r.id=osl.requirement_id
                    WHERE osl.id=%s""", (service_line_id,))
                line = cur.fetchone()
                if not line:
                    return jsonify({"success": False, "message": "Service offer line tidak ditemukan."}), 404
                if line["offer_status"] != "current":
                    return jsonify({"success": False, "message": "Negosiasi harus dicatat pada versi penawaran aktif. Muat ulang detail Work Item."}), 409
                cur.execute("""INSERT INTO leasing.partner_service_negotiation_events
                    (service_line_id,event_type,mrc_amount,otc_amount,currency,notes,created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id,occurred_at""",
                    (service_line_id,event_type,mrc,otc,currency,notes,session["username"]))
                event = cur.fetchone()
                leasing_activity(cur, line["work_item_id"], "service_negotiation_event_recorded",
                    "Negosiasi jasa dicatat", session["username"],
                    {"service_negotiation_event_id":event["id"], "service_line_id":service_line_id,
                     "requirement_id":line["requirement_id"], "service_name":line["service_name"],
                     "partner_name":line["partner_name"], "event_type":event_type})
            conn.commit()
        return jsonify({"success":True,"event_id":event["id"],"occurred_at":event["occurred_at"]}),201
    except ValueError as exc:
        return jsonify({"success":False,"message":str(exc)}),400
    except psycopg2.Error:
        app.logger.exception("Leasing generic service negotiation event save failed")
        return jsonify({"success":False,"message":"Gagal mencatat negosiasi jasa."}),400


@app.route("/api/leasing/work-items/<int:work_item_id>/result-submissions", methods=["POST"])
@leasing_login_required
def leasing_create_result_submission(work_item_id):
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    payload = request.get_json(silent=True) or {}; lines = payload.get("lines") or []
    if not isinstance(lines, list) or not lines: return jsonify({"success": False, "message": "Minimal satu hasil requirement harus dicatat."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM leasing.work_items WHERE id=%s", (work_item_id,))
                if not cur.fetchone(): return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                cur.execute("SELECT COALESCE(MAX(submission_no),0)+1 AS n FROM leasing.result_submissions WHERE work_item_id=%s", (work_item_id,)); n=cur.fetchone()["n"]
                status=payload.get("submission_status", "draft")
                sent_at=payload.get("sent_at") or (datetime.now().isoformat() if status == "sent" else None)
                cur.execute("""INSERT INTO leasing.result_submissions
                    (work_item_id, submission_no, submission_status, recipient_name, recipient_email, channel, sent_at, notes, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""", (work_item_id,n,status,payload.get("recipient_name"),payload.get("recipient_email"),payload.get("channel","email"),sent_at,payload.get("notes"),session["username"]))
                submission_id=cur.fetchone()["id"]
                for line in lines:
                    req_id=int(line["requirement_id"]); offer_line_id=line.get("offer_line_id")
                    cur.execute("SELECT id FROM leasing.requirements WHERE id=%s AND work_item_id=%s", (req_id,work_item_id))
                    if not cur.fetchone(): raise ValueError("Requirement bukan milik Work Item ini.")
                    if offer_line_id:
                        cur.execute("""SELECT pol.id FROM leasing.partner_offer_lines pol JOIN leasing.partner_offers po ON po.id=pol.offer_id
                            JOIN leasing.partner_outreaches o ON o.id=po.outreach_id WHERE pol.id=%s AND o.work_item_id=%s""", (offer_line_id,work_item_id))
                        if not cur.fetchone(): raise ValueError("Offer line bukan milik Work Item ini.")
                    cur.execute("INSERT INTO leasing.result_submission_lines (submission_id, requirement_id, offer_line_id, result_note) VALUES (%s,%s,%s,%s)", (submission_id,req_id,offer_line_id,line.get("result_note")))
                leasing_activity(cur,work_item_id,"result_submission_created","Hasil dikirim/dicatat untuk sebagian atau seluruh requirement",session["username"],{"submission_id":submission_id,"submission_no":n,"line_count":len(lines)})
            conn.commit()
        return jsonify({"success": True, "submission_id": submission_id, "submission_no": n}), 201
    except (KeyError, TypeError, ValueError) as exc:
        return jsonify({"success": False, "message": str(exc) or "Format hasil tidak valid."}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing result submission failed")
        return jsonify({"success": False, "message": "Gagal mencatat hasil Leasing."}), 400


@app.route("/api/leasing/work-items/<int:work_item_id>/requirements", methods=["POST"])
@leasing_login_required
def leasing_create_requirement(work_item_id):
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    payload = request.get_json(silent=True) or {}
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, case_status, work_type, project_name FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
                work_item = cur.fetchone()
                if not work_item:
                    return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                if work_item["case_status"] != "open":
                    return jsonify({"success": False, "message": "Requirement baru hanya bisa ditambahkan ke Work Item yang masih open."}), 409
                values = _leasing_validate_requirement_payload({**payload, "project_name": work_item.get("project_name")}, "Requirement baru", work_item.get("work_type"))
                cur.execute("SELECT COALESCE(MAX(requirement_no),0)+1 AS next_no FROM leasing.requirements WHERE work_item_id=%s", (work_item_id,))
                next_no = cur.fetchone()["next_no"]
                if work_item.get("work_type") == "project":
                    cur.execute("""INSERT INTO leasing.requirements
                        (work_item_id, requirement_no, zone, site_name, address, postal_code, latitude, longitude,
                         project_mrc_inet_dedicated_25, project_mrc_metro_25, requested_otc, project_notes, area, requested_services, service_type)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id, requirement_no""",
                        (work_item_id, next_no, values.get("zone"), values["site_name"], values["address"], values.get("postal_code"),
                         values.get("latitude"), values.get("longitude"), values.get("project_mrc_inet_dedicated_25"),
                         values.get("project_mrc_metro_25"), values.get("requested_otc"), values.get("project_notes"), values.get("area"), values.get("requested_services") or [], values.get("service_type")))
                else:
                    cur.execute("""INSERT INTO leasing.requirements
                        (work_item_id, requirement_no, order_type, si, area, address, gedung_kawasan, latitude, longitude,
                         a_end, z_end, bandwidth, bandwidth_unit, service_type, special_features,
                         existing_mrc_amount, existing_mrc_currency, external_reference,
                         existing_mrc_inet_dedicated_25_amount, existing_mrc_metro_25_amount, requested_services)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING id, requirement_no""",
                        (work_item_id, next_no, values["order_type"], values["si"], values["area"], values["address"],
                         values["gedung_kawasan"], values["latitude"], values["longitude"], values["a_end"], values["z_end"], values["bandwidth"], values["bandwidth_unit"],
                         values["service_type"], values["special_features"], values["existing_mrc_amount"], values["existing_mrc_currency"], values.get("external_reference"),
                         values.get("existing_mrc_inet_dedicated_25_amount"), values.get("existing_mrc_metro_25_amount"), values.get("requested_services") or []))
                created = dict(cur.fetchone())
                _leasing_field_audit(cur,"requirement",created["id"],work_item_id,"create",session["username"],{},dict(values))
                leasing_activity(cur, work_item_id, "requirement_added", f"Requirement #{next_no} ditambahkan", session["username"], {"requirement_id": created["id"], "requirement_no": next_no})
            conn.commit()
        return jsonify({"success": True, **created, "message": "Requirement berhasil ditambahkan."}), 201
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing requirement create failed")
        return jsonify({"success": False, "message": "Gagal menambahkan requirement. Periksa log server."}), 400


@app.route("/api/leasing/requirements/<int:requirement_id>", methods=["PATCH"])
@leasing_login_required
def leasing_update_requirement(requirement_id):
    work_item_id = _leasing_resource_work_item_id({"requirement_id": requirement_id})
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    payload = request.get_json(silent=True) or {}
    allowed = {"status", "resolution_note", "order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end", "bandwidth", "bandwidth_unit", "service_type", "special_features", "existing_mrc_amount", "existing_mrc_currency", "zone", "site_name", "postal_code", "project_mrc_inet_dedicated_25", "project_mrc_metro_25", "requested_otc", "project_notes", "external_reference", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount", "requested_services"}
    changes = {k: payload[k] for k in allowed if k in payload}
    if not changes:
        return jsonify({"success": False, "message": "Tidak ada field yang diperbarui."}), 400
    if "status" in changes and changes["status"] not in LEASING_REQUIREMENT_STATUSES:
        return jsonify({"success": False, "message": "Status requirement tidak valid."}), 400
    detail_fields = {"order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end", "bandwidth", "bandwidth_unit", "service_type", "special_features", "existing_mrc_amount", "existing_mrc_currency", "zone", "site_name", "postal_code", "project_mrc_inet_dedicated_25", "project_mrc_metro_25", "requested_otc", "project_notes", "external_reference", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount", "requested_services"}
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT r.*, w.work_type, w.project_name FROM leasing.requirements r
                    JOIN leasing.work_items w ON w.id=r.work_item_id WHERE r.id=%s FOR UPDATE OF r""", (requirement_id,))
                existing = cur.fetchone()
                if not existing:
                    return jsonify({"success": False, "message": "Requirement tidak ditemukan."}), 404
                if detail_fields.intersection(changes):
                    merged = {key: existing.get(key) for key in detail_fields}
                    merged.update({k: v for k, v in changes.items() if k in detail_fields})
                    merged["project_name"] = existing.get("project_name")
                    require_project_services = True
                    if existing.get("work_type") == "project" and "requested_services" not in changes and not (existing.get("requested_services") or existing.get("service_type")):
                        # Let legacy service-less rows be repaired field-by-field; a user must
                        # provide a service before creating a new site or explicitly editing services.
                        require_project_services = False
                    # Do not turn a legacy NULL/empty array into an explicit clear merely because
                    # merged contains all detail fields. Missing request data may fall back to the
                    # legacy service_type; an explicit [] in changes remains a real clear request.
                    if "requested_services" not in changes and not existing.get("requested_services"):
                        merged.pop("requested_services", None)
                    validated = _leasing_validate_requirement_payload(
                        merged, f"Requirement #{requirement_id}", existing.get("work_type"),
                        require_project_services=require_project_services)
                    if "requested_services" in changes:
                        changes["requested_services"] = validated.get("requested_services") or []
                        changes["service_type"] = validated.get("service_type")
                    if existing.get("work_type") == "project":
                        changes.update({k: validated.get(k) for k in ("zone", "site_name", "address", "postal_code", "latitude", "longitude", "project_mrc_inet_dedicated_25", "project_mrc_metro_25", "requested_otc", "project_notes", "area", "external_reference", "requested_services", "service_type")})
                    else:
                        changes.update({k: validated.get(k) for k in ("order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end", "bandwidth", "bandwidth_unit", "service_type", "special_features", "existing_mrc_amount", "existing_mrc_currency", "external_reference", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount", "requested_services")})
                sets, vals = [], []
                for key, value in changes.items():
                    sets.append(f"{key}=%s")
                    vals.append(value)
                vals.append(requirement_id)
                sets.append("updated_at=NOW()")
                cur.execute(f"UPDATE leasing.requirements SET {', '.join(sets)} WHERE id=%s", vals)
                _leasing_field_audit(cur,"requirement",requirement_id,existing["work_item_id"],"update",session["username"],
                    {key:existing.get(key) for key in changes},{key:value for key,value in changes.items()})
                leasing_activity(cur, existing["work_item_id"], "requirement_updated", "Requirement diperbarui", session["username"], {"requirement_id": requirement_id, **changes})
            conn.commit()
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing requirement update failed")
        return jsonify({"success": False, "message": "Gagal memperbarui requirement."}), 400


def _leasing_header_key(value):
    """Normalize human-readable Excel headers for stable lookup."""
    value = unicodedata.normalize("NFKD", str(value or "").replace("\ufeff", ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


# Bulk requirement/site maintenance ------------------------------------------------
LEASING_REGISTER_FIELDS = {
    "external_reference": "External Reference", "status": "Status", "resolution_note": "Resolution Note",
    "zone": "Zone", "site_name": "Site", "address": "Address", "postal_code": "Postal Code",
    "latitude": "Latitude", "longitude": "Longitude",
    "project_notes": "Site Notes", "requested_services": "Requested Services (separate with ;)", "order_type": "Order Type", "si": "SI", "area": "Area",
    "gedung_kawasan": "Building / Complex", "a_end": "A-End", "z_end": "Z-End",
    "bandwidth": "Bandwidth", "bandwidth_unit": "Bandwidth Unit", "service_type": "Service Summary (legacy/optional)",
    "special_features": "Special Features", "existing_mrc_amount": "Existing MRC (Generic)",
    "existing_mrc_currency": "Existing MRC Currency",
}
LEASING_REGISTER_NUMERIC_FIELDS = {"latitude", "longitude", "bandwidth", "existing_mrc_amount"}
LEASING_REGISTER_READABLE_HEADERS = {
    _leasing_header_key("Requirement ID"): "requirement_id",
    _leasing_header_key("Requirement No (do not edit)"): "requirement_no",
    _leasing_header_key("Snapshot updated at (do not edit)"): "snapshot_updated_at",
    **{_leasing_header_key(label): key for key, label in LEASING_REGISTER_FIELDS.items()},
    # Friendly alternative headers are accepted for files users have already prepared.
    "mrc_existing_internet_dedicated": "existing_mrc_inet_dedicated_25_amount",
    "mrc_existing_metro_e": "existing_mrc_metro_25_amount",
    _leasing_header_key("Requested MRC Inet Dedicated 25 Mbps"): "project_mrc_inet_dedicated_25",
    _leasing_header_key("Requested MRC Metro 25 Mbps"): "project_mrc_metro_25",
    _leasing_header_key("Requested OTC"): "requested_otc",
}


def _leasing_register_workbook(cur, work_item_id):
    cur.execute("SELECT id, request_id, work_type, project_name FROM leasing.work_items WHERE id=%s", (work_item_id,))
    work_item = cur.fetchone()
    if not work_item:
        raise LookupError("Work Item tidak ditemukan.")
    cur.execute("SELECT * FROM leasing.requirements WHERE work_item_id=%s ORDER BY requirement_no", (work_item_id,))
    requirements = [dict(row) for row in cur.fetchall()]
    wb = Workbook()
    ws = wb.active
    ws.title = "Requirement Edit"
    headers = ["Requirement ID", "Requirement No (do not edit)", "Work Type (read-only)", "Snapshot updated at (do not edit)"] + list(LEASING_REGISTER_FIELDS.values())
    ws.append(headers)
    field_by_label = {label: field for field, label in LEASING_REGISTER_FIELDS.items()}
    for row in requirements:
        snapshot = row.get("updated_at")
        snapshot = snapshot.isoformat() if hasattr(snapshot, "isoformat") else (str(snapshot) if snapshot else "")
        vals = [row.get("id"), row.get("requirement_no"), work_item.get("work_type"), snapshot]
        vals.extend(("; ".join(row.get(field_by_label[label]) or []) if field_by_label[label] == "requested_services" and isinstance(row.get(field_by_label[label]), (list, tuple)) else row.get(field_by_label[label])) for label in LEASING_REGISTER_FIELDS.values())
        ws.append([_leasing_excel_safe(v) for v in vals])
    ws.freeze_panes = "E2"
    ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 36
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="35266E")
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for col in ws.columns:
        letter = col[0].column_letter
        max_len = min(34, max(12, max(len(str(c.value or "")) for c in col[:200])))
        ws.column_dimensions[letter].width = max_len
    info = wb.create_sheet("Instructions")
    guide_rows = [
        ["Bulk edit requirement/site", "Petunjuk"],
        ["Work Item", f"{work_item.get('request_id')} — {work_item.get('project_name') or ''}"],
        ["Scope", "Workbook ini hanya mengubah requirement yang ID-nya sudah ada di Work Item ini. Tidak menambah/menghapus requirement."],
        ["Requirement ID / No / Work Type / Snapshot", "Kolom identitas dan Snapshot updated at wajib dipertahankan. Snapshot dipakai mendeteksi edit bersamaan; jangan diedit atau dihapus."],
        ["Perubahan", "Edit kolom yang diperlukan, lalu upload kembali ke Work Item yang sama."],
        ["Cell kosong", "Dibiarkan apa adanya (tidak menghapus nilai lama)."],
        ["Hapus nilai optional", "Ketik [[CLEAR]] pada sel yang ingin dikosongkan. Kolom wajib seperti Site, Alamat, A-End, Jasa atau Fitur Khusus tidak boleh dikosongkan."],
        ["Status", "Gunakan open, in_progress, resolved, atau stopped."],
        ["Harga", "Gunakan angka tanpa simbol currency. Nilai harus nol atau lebih."],
        ["Project", "MRC Inet/Metro/OTC referensi ada di field Requested MRC dan Requested OTC."],
        ["Non-Project multi-service", "Gunakan kolom Existing MRC Internet Dedicated dan Existing MRC Metro E untuk membedakan harga referensi tiap jasa."],
        ["Import", "Seluruh perubahan divalidasi terlebih dahulu; jika ada kesalahan, tidak ada baris yang disimpan."],
    ]
    for row in guide_rows: info.append(row)
    info.column_dimensions["A"].width = 38
    info.column_dimensions["B"].width = 105
    info.freeze_panes = "A2"
    for cell in info[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="35266E")
    for row in info.iter_rows(min_row=2):
        row[1].alignment = Alignment(wrap_text=True, vertical="top")
    info.row_dimensions[1].height = 26
    for idx in range(2, len(guide_rows) + 1):
        info.row_dimensions[idx].height = 34
    output = BytesIO(); wb.save(output); output.seek(0)
    return work_item, len(requirements), output


@app.route("/api/leasing/work-items/<int:work_item_id>/requirements.xlsx", methods=["GET"])
@leasing_login_required
def leasing_requirements_edit_xlsx(work_item_id):
    # This workbook contains the complete site register. A delegated follow-up PIC may see
    # only sites in their assigned outreach through detail/coverage endpoints, not this export.
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                item, count, output = _leasing_register_workbook(cur, work_item_id)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", str(item.get("request_id") or work_item_id))
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                         as_attachment=True, download_name=f"requirement_edit_{safe_id}_{count}_rows.xlsx")
    except LookupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except Exception:
        app.logger.exception("Leasing requirement edit export failed")
        return jsonify({"success": False, "message": "Gagal membuat workbook edit requirement. Periksa migrasi dan log aplikasi."}), 500


@app.route("/api/leasing/work-items/<int:work_item_id>/requirements/import", methods=["POST"])
@leasing_login_required
def leasing_requirements_edit_import(work_item_id):
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    file_obj = request.files.get("file")
    if not file_obj or not (file_obj.filename or "").lower().endswith(".xlsx"):
        return jsonify({"success": False, "message": "Pilih workbook .xlsx hasil Download editable register."}), 400
    try:
        content = file_obj.read()
        if not content:
            raise ValueError("File Excel kosong.")
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
        if "Requirement Edit" not in wb.sheetnames:
            raise ValueError("Sheet 'Requirement Edit' tidak ditemukan; download template baru dari Work Item ini.")
        ws = wb["Requirement Edit"]
        raw_headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        header_map = {}
        for idx, header in enumerate(raw_headers):
            if header is not None:
                key = LEASING_REGISTER_READABLE_HEADERS.get(_leasing_header_key(header))
                if key:
                    header_map[key] = idx
        if "requirement_id" not in header_map:
            raise ValueError("Kolom Requirement ID wajib ada dan tidak boleh dihapus.")
        if "snapshot_updated_at" not in header_map:
            raise ValueError("Workbook ini tidak memiliki Snapshot updated at. Download ulang workbook terbaru agar edit bersamaan dapat dideteksi.")
        rows, issues, seen_ids = [], [], set()
        clear_marker = "[[clear]]"
        for excel_row_no, values in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if excel_row_no > 10002:
                raise ValueError("Maksimal 10.000 baris dalam satu workbook.")
            if not any(v not in (None, "") for v in values):
                continue
            raw_id = values[header_map["requirement_id"]] if header_map["requirement_id"] < len(values) else None
            if raw_id in (None, ""):
                issues.append(f"Baris {excel_row_no}: Requirement ID wajib diisi untuk baris yang digunakan.")
                continue
            try:
                req_id = int(raw_id)
                if float(raw_id) != req_id or req_id <= 0:
                    raise ValueError
            except (TypeError, ValueError):
                issues.append(f"Baris {excel_row_no}: Requirement ID harus bilangan bulat positif.")
                continue
            if req_id in seen_ids:
                issues.append(f"Baris {excel_row_no}: Requirement ID {req_id} duplikat.")
                continue
            seen_ids.add(req_id)
            changes = {}
            for key, idx in header_map.items():
                if key in {"requirement_id", "requirement_no", "snapshot_updated_at"} or idx >= len(values):
                    continue
                raw = values[idx]
                if raw is None or (isinstance(raw, str) and not raw.strip()):
                    continue  # Blank means unchanged, never clear silently.
                if isinstance(raw, str) and raw.strip().lower() == clear_marker:
                    if key in {"status"}:
                        issues.append(f"Baris {excel_row_no}: Status tidak boleh dikosongkan.")
                    else:
                        changes[key] = None
                    continue
                if key == "status":
                    status = str(raw).strip().lower()
                    if status not in LEASING_REQUIREMENT_STATUSES:
                        issues.append(f"Baris {excel_row_no}: Status harus open, in_progress, resolved, atau stopped.")
                        continue
                    changes[key] = status
                elif key in LEASING_REGISTER_NUMERIC_FIELDS:
                    try:
                        number = float(raw)
                        if not math.isfinite(number) or number < 0 and key not in {"latitude", "longitude"}:
                            raise ValueError
                        if key == "latitude" and not -90 <= number <= 90: raise ValueError
                        if key == "longitude" and not -180 <= number <= 180: raise ValueError
                        changes[key] = number
                    except (TypeError, ValueError):
                        issues.append(f"Baris {excel_row_no}: {LEASING_REGISTER_FIELDS.get(key, key)} harus angka yang valid dan tidak negatif (kecuali koordinat).")
                elif key in LEASING_REGISTER_FIELDS:
                    changes[key] = _leasing_normalize_service_names(raw) if key == "requested_services" else (str(raw).strip() or None)
            if changes:
                snapshot_index=header_map["snapshot_updated_at"]
                snapshot_value=values[snapshot_index] if snapshot_index < len(values) else None
                rows.append({"excel_row": excel_row_no, "requirement_id": req_id, "snapshot_updated_at": str(snapshot_value or "").strip(), "changes": changes})
        wb.close()
        if issues:
            return jsonify({"success": False, "message": "Workbook belum valid; tidak ada perubahan yang disimpan.", "issues": issues[:100]}), 400
        if not rows:
            raise ValueError("Tidak ada perubahan. Edit minimal satu kolom pada satu baris.")
        applied = []
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id, work_type, project_name FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
                item = cur.fetchone()
                if not item:
                    return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                req_ids = [row["requirement_id"] for row in rows]
                cur.execute("SELECT * FROM leasing.requirements WHERE work_item_id=%s AND id=ANY(%s) FOR UPDATE", (work_item_id, req_ids))
                existing_by_id = {int(r["id"]): dict(r) for r in cur.fetchall()}
                missing = sorted(set(req_ids) - set(existing_by_id))
                if missing:
                    raise ValueError("Requirement ID tidak dikenal pada Work Item ini: " + ", ".join(map(str, missing)))
                conflicts=[]
                for row in rows:
                    existing=existing_by_id[row["requirement_id"]]
                    snap=row.get("snapshot_updated_at")
                    current=existing.get("updated_at")
                    try:
                        snap_ts=pd.to_datetime(snap,utc=True,errors="raise") if snap else None
                        current_ts=pd.to_datetime(current,utc=True,errors="raise") if current is not None else None
                    except Exception:
                        snap_ts=current_ts=None
                    if snap_ts is None or current_ts is None or snap_ts != current_ts:
                        conflicts.append({"excel_row":row["excel_row"],"requirement_id":row["requirement_id"],"requirement_no":existing.get("requirement_no"),"workbook_updated_at":snap or None,"current_updated_at":current})
                if conflicts:
                    return jsonify({"success":False,"code":"STALE_WORKBOOK_CONFLICT","message":f"{len(conflicts)} baris berubah sejak workbook diunduh. Tidak ada perubahan disimpan. Download ulang, bandingkan, lalu terapkan ulang edit yang masih diperlukan.","conflicts":conflicts[:100]}),409
                prepared = []
                detail_fields = set(LEASING_REGISTER_FIELDS) - {"status", "resolution_note"}
                for row in rows:
                    req_id = row["requirement_id"]
                    existing = existing_by_id[req_id]
                    changes = row["changes"]
                    merged = {key: existing.get(key) for key in detail_fields}
                    merged.update({key: value for key, value in changes.items() if key in detail_fields})
                    merged["project_name"] = item.get("project_name")
                    validated = _leasing_validate_requirement_payload(merged, f"Baris Excel {row['excel_row']} / Requirement {existing['requirement_no']}", item.get("work_type"))
                    prepared.append((req_id, existing, changes, validated))
                for req_id, existing, changes, validated in prepared:
                    all_updates = {}
                    if item.get("work_type") == "project":
                        editable = ("external_reference", "zone", "site_name", "address", "postal_code", "latitude", "longitude",
                                    "project_mrc_inet_dedicated_25", "project_mrc_metro_25", "requested_otc", "project_notes", "area", "requested_services")
                    else:
                        editable = ("external_reference", "order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude",
                                    "a_end", "z_end", "bandwidth", "bandwidth_unit", "service_type", "special_features",
                                    "existing_mrc_amount", "existing_mrc_currency", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount", "requested_services")
                    for key in editable:
                        if key in changes:
                            all_updates[key] = validated.get(key) if key in detail_fields else changes[key]
                    for key in ("status", "resolution_note"):
                        if key in changes:
                            all_updates[key] = changes[key]
                    if all_updates:
                        assignments = [f"{key}=%s" for key in all_updates]
                        cur.execute(f"UPDATE leasing.requirements SET {', '.join(assignments)}, updated_at=NOW() WHERE id=%s",
                                    list(all_updates.values()) + [req_id])
                        _leasing_field_audit(cur,"requirement",req_id,work_item_id,"bulk_workbook_update",session["username"],
                            {key:existing.get(key) for key in all_updates},{key:value for key,value in all_updates.items()},
                            f"Workbook {secure_filename(file_obj.filename or 'requirements.xlsx')}")
                        applied.append(req_id)
                leasing_activity(cur, work_item_id, "requirements_bulk_updated", f"Bulk edit {len(applied)} requirement/site dari Excel",
                                 session["username"], {"requirement_ids": applied, "source_file": secure_filename(file_obj.filename or "requirements.xlsx")})
            conn.commit()
        return jsonify({"success": True, "updated_count": len(applied), "requirement_ids": applied,
                        "message": f"{len(applied)} requirement/site berhasil diperbarui dalam satu transaksi."}), 200
    except LookupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing bulk requirement edit failed")
        return jsonify({"success": False, "message": "Bulk edit gagal; tidak ada perubahan yang disimpan. Periksa log aplikasi."}), 400
    except Exception:
        app.logger.exception("Leasing bulk requirement edit failed unexpectedly")
        return jsonify({"success": False, "message": "Gagal memproses workbook. Tidak ada perubahan yang disimpan."}), 400


@app.route("/api/leasing/work-items/<int:work_item_id>/requirements/bulk-status", methods=["PATCH"])
@leasing_login_required
def leasing_bulk_requirement_status(work_item_id):
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("requirement_ids")
    if not isinstance(raw_ids, list) or not raw_ids or len(raw_ids) > 3000:
        return jsonify({"success": False, "message": "Pilih antara 1 sampai 3.000 requirement."}), 400
    try:
        ids = list(dict.fromkeys(int(v) for v in raw_ids))
        if len(ids) != len(raw_ids) or any(v <= 0 for v in ids): raise ValueError
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Daftar requirement tidak valid atau duplikat."}), 400
    changes = {}
    if "status" in payload:
        status = str(payload.get("status") or "").strip().lower()
        if status not in LEASING_REQUIREMENT_STATUSES:
            return jsonify({"success": False, "message": "Status tidak valid."}), 400
        changes["status"] = status
    if "resolution_note" in payload:
        note = payload.get("resolution_note")
        changes["resolution_note"] = str(note).strip() if note is not None and str(note).strip() else None
    if not changes:
        return jsonify({"success": False, "message": "Tentukan status atau catatan resolusi yang akan diperbarui."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
                if not cur.fetchone(): return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                cur.execute("SELECT id FROM leasing.requirements WHERE work_item_id=%s AND id=ANY(%s) FOR UPDATE", (work_item_id, ids))
                found = {int(r["id"]) for r in cur.fetchall()}
                missing = sorted(set(ids)-found)
                if missing: raise ValueError("Ada requirement yang bukan milik Work Item ini: " + ", ".join(map(str, missing)))
                assignments = [f"{key}=%s" for key in changes]
                cur.execute("SELECT id,status,resolution_note FROM leasing.requirements WHERE work_item_id=%s AND id=ANY(%s) FOR UPDATE",(work_item_id,ids))
                old_status_rows=[dict(x) for x in cur.fetchall()]
                cur.execute(f"UPDATE leasing.requirements SET {', '.join(assignments)}, updated_at=NOW() WHERE work_item_id=%s AND id=ANY(%s)",
                            list(changes.values()) + [work_item_id, ids])
                for oldrow in old_status_rows:
                    _leasing_field_audit(cur,"requirement",oldrow["id"],work_item_id,"bulk_status_update",session["username"],
                        {key:oldrow.get(key) for key in changes},{key:value for key,value in changes.items()})
                leasing_activity(cur, work_item_id, "requirements_bulk_status_updated", f"Bulk update status/catatan untuk {len(ids)} requirement",
                                 session["username"], {"requirement_ids": ids, **changes})
            conn.commit()
        return jsonify({"success": True, "updated_count": len(ids), "message": f"{len(ids)} requirement berhasil diperbarui."})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing bulk requirement status update failed")
        return jsonify({"success": False, "message": "Bulk update gagal dan transaksi dibatalkan."}), 400


# ---------------------------------------------------------------------------
@app.route("/api/leasing/export.xlsx", methods=["GET"])
@leasing_login_required
def leasing_export_xlsx():
    """Export one row per requirement, with work-item and partner context, suitable for large-site reporting."""
    try:
        work_item_id = request.args.get("work_item_id", type=int)
        partner_id = request.args.get("partner_id", type=int)
        from_date = request.args.get("from_date")
        to_date = request.args.get("to_date")
        for date_value, label in ((from_date, "from_date"), (to_date, "to_date")):
            if date_value:
                try: datetime.strptime(date_value, "%Y-%m-%d")
                except ValueError: return jsonify({"success": False, "message": f"{label} harus berformat YYYY-MM-DD."}), 400
        if from_date and to_date and from_date > to_date:
            return jsonify({"success": False, "message": "from_date tidak boleh setelah to_date."}), 400
        scope_sql, scope_params = _leasing_scope_sql(alias="w")
        if _is_leasing_admin():
            row_scope_sql, row_scope_params = "TRUE", []
        else:
            row_scope_sql, row_scope_params = "(w.buyer_owner_id=%s OR o.follow_up_owner_id=%s)", [session.get("username"), session.get("username")]
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = f"""SELECT w.id AS work_item_db_id, w.request_id, w.work_type, w.project_name, c.customer_name, w.requester_name,
                    w.request_due_date, w.current_stage, w.case_status, w.buyer_owner_id, w.created_at,
                    r.id AS requirement_id, r.requirement_no, r.zone, r.site_name, r.postal_code, r.project_mrc_inet_dedicated_25, r.project_mrc_metro_25, r.requested_otc, r.project_notes,
                    r.order_type, r.si, r.area, r.address, r.gedung_kawasan,
                    r.latitude, r.longitude, r.a_end, r.z_end, r.bandwidth, r.bandwidth_unit,
                    r.service_type, r.requested_services, r.special_features, r.status AS requirement_status,
                    r.existing_mrc_amount, r.existing_mrc_currency, r.external_reference,
                    r.existing_mrc_inet_dedicated_25_amount, r.existing_mrc_metro_25_amount,
                    p.partner_name, o.response_status AS partner_response_status,
                    o.next_follow_up_at, po.offer_status, pol.feasibility_status, pol.mrc_amount AS offered_mrc,
                    pol.otc_amount AS offered_otc, pol.mrc_inet_dedicated_25_amount AS offered_mrc_inet_dedicated_25,
                    pol.mrc_metro_25_amount AS offered_mrc_metro_25, pol.currency AS offer_currency
                    FROM leasing.work_items w
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    LEFT JOIN leasing.requirements r ON r.work_item_id=w.id
                    LEFT JOIN leasing.partner_outreaches o ON o.work_item_id=w.id
                    LEFT JOIN leasing.partners p ON p.id=o.partner_id
                    LEFT JOIN leasing.partner_offers po ON po.outreach_id=o.id
                    LEFT JOIN leasing.partner_offer_lines pol ON pol.offer_id=po.id AND pol.requirement_id=r.id
                    WHERE (%s IS NULL OR w.id=%s) AND (%s IS NULL OR p.id=%s)
                      AND (%s IS NULL OR COALESCE(po.received_at, o.sent_at, w.created_at)::date >= %s::date)
                      AND (%s IS NULL OR COALESCE(po.received_at, o.sent_at, w.created_at)::date <= %s::date)
                      AND ({scope_sql}) AND ({row_scope_sql})
                    ORDER BY w.created_at DESC, w.id, r.requirement_no, p.partner_name, po.version_no DESC"""
                cur.execute(sql, (work_item_id, work_item_id, partner_id, partner_id,
                                  from_date, from_date, to_date, to_date, *scope_params, *row_scope_params))
                rows = [dict(row) for row in cur.fetchall()]
                # A generic service matrix is exported separately so the main legacy sheet remains backward compatible.
                generic_sql = f"""WITH base AS (
                    SELECT w.id AS work_item_db_id,w.request_id,w.work_type,w.project_name,c.customer_name,
                        w.request_due_date,w.buyer_owner_id,r.id AS requirement_id,r.requirement_no,r.site_name,r.zone,
                        r.address,r.external_reference,r.requested_services,r.service_type,
                        p.id AS partner_id,p.partner_name,o.id AS outreach_id,o.outreach_round,o.sent_at,
                        o.response_status AS outreach_status,o.next_follow_up_at,oro.response_status AS site_response_status,
                        oro.response_note,
                        CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                             ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END AS service_names
                    FROM leasing.work_items w JOIN leasing.requirements r ON r.work_item_id=w.id
                    JOIN leasing.outreach_requirements oro ON oro.requirement_id=r.id
                    JOIN leasing.partner_outreaches o ON o.id=oro.outreach_id AND o.work_item_id=w.id
                    JOIN leasing.partners p ON p.id=o.partner_id LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    WHERE (%s IS NULL OR w.id=%s) AND (%s IS NULL OR p.id=%s)
                      AND (%s IS NULL OR COALESCE(o.sent_at,w.created_at)::date >= %s::date)
                      AND (%s IS NULL OR COALESCE(o.sent_at,w.created_at)::date <= %s::date)
                      AND ({scope_sql}) AND ({row_scope_sql}) AND COALESCE(o.response_status,'') <> 'cancelled'
                ), requested AS (
                    SELECT b.work_item_db_id,b.request_id,b.work_type,b.project_name,b.customer_name,b.request_due_date,
                        b.buyer_owner_id,b.requirement_id,b.requirement_no,b.site_name,b.zone,b.address,b.external_reference,
                        b.partner_id,b.partner_name,b.outreach_round,b.sent_at,b.outreach_status,b.next_follow_up_at,
                        b.requested_services,svc.service_name,TRUE AS is_requested_service,
                        CASE WHEN sl.feasibility_status IS NOT NULL AND sl.feasibility_status <> 'pending' THEN sl.feasibility_status
                             WHEN pl.feasibility_status='cannot_provide' OR b.site_response_status='cannot_provide' THEN 'cannot_provide'
                             WHEN pl.feasibility_status='can_provide' AND CARDINALITY(b.service_names)<=1 THEN 'can_provide'
                             WHEN b.site_response_status='can_provide' AND CARDINALITY(b.service_names)<=1 THEN 'can_provide'
                             WHEN pl.feasibility_status='can_provide' OR b.site_response_status='can_provide' THEN 'needs_clarification'
                             WHEN pl.feasibility_status='needs_clarification' OR b.site_response_status='needs_clarification' THEN 'needs_clarification'
                             WHEN b.sent_at IS NULL THEN 'draft' WHEN sl.feasibility_status='pending' THEN 'pending'
                             ELSE COALESCE(b.site_response_status,'awaiting_response') END AS coverage_status,
                        sl.mrc_amount,sl.otc_amount,sl.currency,COALESCE(sl.notes,b.response_note) AS notes,COALESCE(sl.version_no,pl.version_no) AS offer_version
                    FROM base b CROSS JOIN LATERAL unnest(b.service_names) AS svc(service_name)
                    LEFT JOIN LATERAL (SELECT po.version_no,x.feasibility_status,x.mrc_amount,x.otc_amount,x.currency,x.notes
                        FROM leasing.partner_offers po JOIN leasing.partner_offer_service_lines x ON x.offer_id=po.id
                        WHERE po.outreach_id=b.outreach_id AND po.offer_status='current' AND x.requirement_id=b.requirement_id
                          AND LOWER(BTRIM(x.service_name))=LOWER(BTRIM(svc.service_name)) ORDER BY po.version_no DESC LIMIT 1) sl ON TRUE
                    LEFT JOIN LATERAL (SELECT po.version_no,x.feasibility_status FROM leasing.partner_offers po
                        JOIN leasing.partner_offer_lines x ON x.offer_id=po.id WHERE po.outreach_id=b.outreach_id
                          AND po.offer_status='current' AND x.requirement_id=b.requirement_id ORDER BY po.version_no DESC LIMIT 1) pl ON TRUE
                ), extras AS (
                    SELECT b.work_item_db_id,b.request_id,b.work_type,b.project_name,b.customer_name,b.request_due_date,
                        b.buyer_owner_id,b.requirement_id,b.requirement_no,b.site_name,b.zone,b.address,b.external_reference,
                        b.partner_id,b.partner_name,b.outreach_round,b.sent_at,b.outreach_status,b.next_follow_up_at,
                        b.requested_services,x.service_name,FALSE AS is_requested_service,x.feasibility_status AS coverage_status,
                        x.mrc_amount,x.otc_amount,x.currency,x.notes,po.version_no AS offer_version
                    FROM base b JOIN leasing.partner_offers po ON po.outreach_id=b.outreach_id AND po.offer_status='current'
                    JOIN leasing.partner_offer_service_lines x ON x.offer_id=po.id AND x.requirement_id=b.requirement_id
                    WHERE NOT EXISTS (SELECT 1 FROM unnest(b.service_names) s(n) WHERE LOWER(BTRIM(s.n))=LOWER(BTRIM(x.service_name)))
                ) SELECT * FROM requested UNION ALL SELECT * FROM extras
                  ORDER BY request_id,partner_name,outreach_round,requirement_no,service_name"""
                generic_params = (work_item_id, work_item_id, partner_id, partner_id, from_date, from_date,
                                  to_date, to_date, *scope_params, *row_scope_params)
                cur.execute(generic_sql, generic_params)
                generic_service_rows = [dict(row) for row in cur.fetchall()]
        wb = Workbook()
        ws = wb.active
        ws.title = "Site Register"
        def safe_excel_value(value):
            return _leasing_excel_safe(value)
        site_headers = ["Work Item DB ID", "Request ID", "Work Type", "Project Name", "Customer", "Requester", "Due Date", "Stage", "Case Status", "Buyer Username",
            "Requirement ID", "Requirement No", "Zone", "Site", "Postal Code", "Address", "Latitude", "Longitude", "Order Type", "SI", "Area", "Gedung/Kawasan",
            "A-End", "Z-End", "Bandwidth", "Bandwidth Unit", "Requested Services", "Service Summary (legacy)", "Special Features", "Requirement Status", "External Reference",
            "Existing MRC (Generic)", "Existing MRC Currency", "Site Notes"]
        ws.append(site_headers)
        # Main sheet is one row per requirement/site, not one row per partner/offer version.
        site_seen = set()
        for row in rows:
            key = (row.get("work_item_db_id"), row.get("requirement_id") or row.get("requirement_no"))
            if key in site_seen:
                continue
            site_seen.add(key)
            requested = row.get("requested_services")
            if isinstance(requested, (list, tuple)):
                requested = "; ".join(str(x) for x in requested if x)
            vals = [row.get("work_item_db_id"), row.get("request_id"), row.get("work_type"), row.get("project_name"), row.get("customer_name"), row.get("requester_name"),
                row.get("request_due_date"), row.get("current_stage"), row.get("case_status"), row.get("buyer_owner_id"), row.get("requirement_id"), row.get("requirement_no"),
                row.get("zone"), row.get("site_name"), row.get("postal_code"), row.get("address"), row.get("latitude"), row.get("longitude"), row.get("order_type"), row.get("si"),
                row.get("area"), row.get("gedung_kawasan"), row.get("a_end"), row.get("z_end"), row.get("bandwidth"), row.get("bandwidth_unit"), requested,
                row.get("service_type"), row.get("special_features"), row.get("requirement_status"), row.get("external_reference"), row.get("existing_mrc_amount"),
                row.get("existing_mrc_currency"), row.get("project_notes")]
            ws.append([safe_excel_value(v.isoformat() if hasattr(v, "isoformat") else v) for v in vals])
        ws.freeze_panes = "K2"
        ws.auto_filter.ref = ws.dimensions
        ws.row_dimensions[1].height = 34
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="35266E")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for col in ws.columns:
            letter = col[0].column_letter
            max_len = min(36, max(12, max(len(str(c.value or "")) for c in col[:200])))
            ws.column_dimensions[letter].width = max_len
        ws.sheet_view.showGridLines = False

        # Retain legacy offer columns only in a clearly-labelled compatibility sheet.
        legacy_ws = wb.create_sheet("Legacy Commercial")
        legacy_headers = ["Work Item DB ID", "Request ID", "Work Type", "Project Name", "Customer", "Requester", "Due Date", "Stage", "Case Status", "Buyer Username",
            "Requirement No", "Zone", "Site", "Postal Code", "Legacy Requested MRC A", "Legacy Requested MRC B", "Legacy Requested OTC", "Site Notes", "Order Type", "SI", "Area", "Address", "Building/Complex", "Latitude", "Longitude", "A End", "Z End",
            "Bandwidth", "Unit", "Service Summary (legacy)", "Requested Services", "Special Features", "Requirement Status", "External Reference", "Existing MRC (Generic)", "Currency MRC (Generic)", "Legacy Existing MRC A", "Legacy Existing MRC B",
            "Partner", "Partner Response", "Next Follow-up", "Offer Status", "Legacy Site Feasibility", "Legacy Site MRC", "Legacy Offer MRC A", "Legacy Offer MRC B", "Legacy Site OTC", "Legacy Currency"]
        legacy_ws.append(legacy_headers)
        for row in rows:
            requested = row.get("requested_services")
            if isinstance(requested, (list, tuple)):
                requested = "; ".join(str(x) for x in requested if x)
            vals = [row.get(k) for k in ["work_item_db_id", "request_id", "work_type", "project_name", "customer_name", "requester_name", "request_due_date", "current_stage", "case_status", "buyer_owner_id",
                "requirement_no", "zone", "site_name", "postal_code", "project_mrc_inet_dedicated_25", "project_mrc_metro_25", "requested_otc", "project_notes", "order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end", "bandwidth", "bandwidth_unit",
                "service_type"]] + [requested] + [row.get(k) for k in ["special_features", "requirement_status", "external_reference", "existing_mrc_amount", "existing_mrc_currency", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount", "partner_name", "partner_response_status", "next_follow_up_at", "offer_status", "feasibility_status", "offered_mrc", "offered_mrc_inet_dedicated_25", "offered_mrc_metro_25", "offered_otc", "offer_currency"]]
            legacy_ws.append([safe_excel_value(v.isoformat() if hasattr(v, "isoformat") else v) for v in vals])
        legacy_ws.freeze_panes = "A2"
        legacy_ws.auto_filter.ref = legacy_ws.dimensions
        legacy_ws.row_dimensions[1].height = 34
        for cell in legacy_ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="716B83")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for col in legacy_ws.columns:
            letter = col[0].column_letter
            max_len = min(36, max(12, max(len(str(c.value or "")) for c in col[:200])))
            legacy_ws.column_dimensions[letter].width = max_len
        legacy_ws.sheet_view.showGridLines = False
        svc_ws = wb.create_sheet("Service Coverage")
        if generic_service_rows:
            svc_cols = list(generic_service_rows[0].keys())
            svc_ws.append(svc_cols)
            for record in generic_service_rows:
                svc_ws.append([_leasing_excel_safe(record.get(col)) for col in svc_cols])
        else:
            svc_ws.append(["No records"])
            svc_ws.append(["Tidak ada outreach/coverage untuk filter yang dipilih."])
        svc_ws.freeze_panes = "A2"
        svc_ws.auto_filter.ref = svc_ws.dimensions
        svc_ws.sheet_view.showGridLines = False
        svc_ws.row_dimensions[1].height = 30
        for cell in svc_ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="35266E")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for col in svc_ws.columns:
            letter = col[0].column_letter
            max_len = min(34, max(12, max(len(str(c.value or "")) for c in col[:200])))
            svc_ws.column_dimensions[letter].width = max_len
        output = BytesIO(); wb.save(output); output.seek(0)
        suffix = f"_work_item_{work_item_id}" if work_item_id else (f"_partner_{partner_id}" if partner_id else "")
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True,
                         download_name=f"leasing_report{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    except Exception:
        app.logger.exception("Leasing Excel export failed")
        return jsonify({"success": False, "message": "Export Excel gagal. Periksa log aplikasi."}), 500


@app.route("/api/leasing/monthly-report.xlsx", methods=["GET"])
@leasing_login_required
def leasing_monthly_report_xlsx():
    """Monthly buyer/vendor report. Vendor request counts use distinct Work Items per partner."""
    report_tz = ZoneInfo("Asia/Jakarta")
    month_key = (request.args.get("month") or datetime.now(report_tz).strftime("%Y-%m")).strip()
    if not re.fullmatch(r"\d{4}-\d{2}", month_key):
        return jsonify({"success": False, "message": "Parameter month wajib berformat YYYY-MM."}), 400
    try:
        parsed_month = datetime.strptime(month_key, "%Y-%m")
        start = datetime(parsed_month.year, parsed_month.month, 1, tzinfo=report_tz)
    except ValueError:
        return jsonify({"success": False, "message": "Bulan tidak valid."}), 400
    end = datetime(start.year + (1 if start.month == 12 else 0), 1 if start.month == 12 else start.month + 1, 1, tzinfo=report_tz)
    buyer = (request.args.get("buyer") or "").strip() or None
    # A Buyer may only download their own monthly activity; Leasing/platform admins may select any buyer.
    if session.get("role") == "buyer":
        buyer = session.get("username")
    partner_raw = (request.args.get("partner_id") or "").strip()
    partner_id = None
    if partner_raw:
        try: partner_id = int(partner_raw)
        except ValueError: return jsonify({"success": False, "message": "partner_id tidak valid."}), 400
        if partner_id < 1: return jsonify({"success": False, "message": "partner_id tidak valid."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT
                    COUNT(DISTINCT w.id) FILTER (WHERE w.received_at >= %s AND w.received_at < %s) AS items_received,
                    COUNT(DISTINCT w.id) FILTER (WHERE EXISTS (SELECT 1 FROM leasing.activity_events ae WHERE ae.work_item_id=w.id AND ae.occurred_at >= %s AND ae.occurred_at < %s)) AS items_with_activity,
                    COUNT(DISTINCT o.id) FILTER (WHERE o.sent_at >= %s AND o.sent_at < %s) AS outreach_sent,
                    COUNT(DISTINCT w.id) FILTER (WHERE w.work_type='project' AND (
                        (w.received_at >= %s AND w.received_at < %s)
                        OR EXISTS (SELECT 1 FROM leasing.activity_events ae WHERE ae.work_item_id=w.id AND ae.occurred_at >= %s AND ae.occurred_at < %s)
                        OR EXISTS (SELECT 1 FROM leasing.partner_outreaches ox WHERE ox.work_item_id=w.id AND ox.sent_at >= %s AND ox.sent_at < %s)
                    )) AS project_work_items
                    FROM leasing.work_items w LEFT JOIN leasing.partner_outreaches o ON o.work_item_id=w.id
                    WHERE (%s IS NULL OR w.buyer_owner_id=%s)
                      AND (%s IS NULL OR EXISTS (SELECT 1 FROM leasing.partner_outreaches op WHERE op.work_item_id=w.id AND op.partner_id=%s AND op.sent_at >= %s AND op.sent_at < %s))""",
                    (start,end,start,end,start,end,start,end,start,end,start,end,buyer,buyer,partner_id,partner_id,start,end))
                summary = dict(cur.fetchone() or {})
                # Attribute outreach volume to the account that recorded/sent it, not the Work Item's current owner.
                cur.execute("""SELECT COUNT(DISTINCT o.id) AS outreach_sent
                    FROM leasing.partner_outreaches o
                    JOIN leasing.work_items w ON w.id=o.work_item_id
                    WHERE o.sent_at >= %s AND o.sent_at < %s
                      AND (%s IS NULL OR o.created_by=%s)
                      AND (%s IS NULL OR o.partner_id=%s)""",
                    (start,end,buyer,buyer,partner_id,partner_id))
                summary["outreach_sent"] = (cur.fetchone() or {}).get("outreach_sent", 0)
                cur.execute("""SELECT w.id AS work_item_db_id, w.request_id, w.work_type, w.project_name, c.customer_name,
                    w.requester_name, w.buyer_owner_id, w.current_stage, w.case_status, w.received_at,
                    w.request_due_date, w.updated_at, COUNT(DISTINCT r.id) AS site_count,
                    COUNT(DISTINCT o.id) FILTER (WHERE o.sent_at >= %s AND o.sent_at < %s) AS outreach_sent_in_month,
                    COUNT(DISTINCT ae.id) FILTER (WHERE ae.occurred_at >= %s AND ae.occurred_at < %s) AS activity_events_in_month
                    FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    LEFT JOIN leasing.requirements r ON r.work_item_id=w.id
                    LEFT JOIN leasing.partner_outreaches o ON o.work_item_id=w.id
                    LEFT JOIN leasing.activity_events ae ON ae.work_item_id=w.id
                    WHERE ((w.received_at >= %s AND w.received_at < %s)
                      OR EXISTS (SELECT 1 FROM leasing.activity_events ax WHERE ax.work_item_id=w.id AND ax.occurred_at >= %s AND ax.occurred_at < %s)
                      OR EXISTS (SELECT 1 FROM leasing.partner_outreaches ox WHERE ox.work_item_id=w.id AND ox.sent_at >= %s AND ox.sent_at < %s))
                      AND (%s IS NULL OR w.buyer_owner_id=%s
                        OR EXISTS (SELECT 1 FROM leasing.activity_events act WHERE act.work_item_id=w.id AND act.actor_id=%s AND act.occurred_at >= %s AND act.occurred_at < %s)
                        OR EXISTS (SELECT 1 FROM leasing.partner_outreaches own_out WHERE own_out.work_item_id=w.id AND own_out.created_by=%s AND own_out.sent_at >= %s AND own_out.sent_at < %s))
                      AND (%s IS NULL OR EXISTS (SELECT 1 FROM leasing.partner_outreaches op WHERE op.work_item_id=w.id AND op.partner_id=%s AND op.sent_at >= %s AND op.sent_at < %s))
                    GROUP BY w.id,c.customer_name ORDER BY w.received_at,w.request_id""",
                    (start,end,start,end,start,end,start,end,start,end,buyer,buyer,buyer,start,end,buyer,start,end,partner_id,partner_id,start,end))
                work_rows = [dict(r) for r in cur.fetchall()]
                summary["work_items_in_period"] = len(work_rows)
                cur.execute("""SELECT w.id AS work_item_db_id, w.request_id, w.work_type, w.project_name,
                    c.customer_name, w.buyer_owner_id, w.request_due_date, w.current_stage, w.case_status,
                    r.id AS requirement_id, r.requirement_no, r.status AS requirement_status,
                    r.zone, r.site_name, r.address, r.postal_code, r.latitude, r.longitude,
                    r.project_mrc_inet_dedicated_25 AS requested_mrc_inet_dedicated_25,
                    r.project_mrc_metro_25 AS requested_mrc_metro_25, r.requested_otc,
                    r.order_type, r.si, r.area, r.gedung_kawasan, r.a_end, r.z_end,
                    r.bandwidth, r.bandwidth_unit, r.service_type, r.requested_services, r.special_features, r.project_notes
                    FROM leasing.work_items w
                    JOIN leasing.requirements r ON r.work_item_id=w.id
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    WHERE ((w.received_at >= %s AND w.received_at < %s)
                      OR EXISTS (SELECT 1 FROM leasing.activity_events ax WHERE ax.work_item_id=w.id AND ax.occurred_at >= %s AND ax.occurred_at < %s)
                      OR EXISTS (SELECT 1 FROM leasing.partner_outreaches ox WHERE ox.work_item_id=w.id AND ox.sent_at >= %s AND ox.sent_at < %s))
                      AND (%s IS NULL OR w.buyer_owner_id=%s OR EXISTS (
                        SELECT 1 FROM leasing.partner_outreaches own_out
                        JOIN leasing.outreach_requirements own_oro ON own_oro.outreach_id=own_out.id
                        WHERE own_out.work_item_id=w.id AND own_oro.requirement_id=r.id
                          AND (own_out.created_by=%s OR own_out.follow_up_owner_id=%s)
                          AND (%s IS NULL OR own_out.partner_id=%s)))
                      AND (%s IS NULL OR EXISTS (SELECT 1 FROM leasing.partner_outreaches op WHERE op.work_item_id=w.id AND op.partner_id=%s AND op.sent_at >= %s AND op.sent_at < %s))
                    ORDER BY w.received_at, w.request_id, r.requirement_no""",
                    (start,end,start,end,start,end,buyer,buyer,buyer,buyer,partner_id,partner_id,partner_id,partner_id,start,end))
                site_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("""SELECT COALESCE(NULLIF(ae.actor_id,''),'__system__') AS buyer,
                    COUNT(*) AS activity_count, COUNT(DISTINCT ae.work_item_id) AS work_items_touched
                    FROM leasing.activity_events ae JOIN leasing.work_items w ON w.id=ae.work_item_id
                    WHERE ae.occurred_at >= %s AND ae.occurred_at < %s
                      AND (%s IS NULL OR ae.actor_id=%s)
                      AND (%s IS NULL OR EXISTS (SELECT 1 FROM leasing.partner_outreaches op WHERE op.work_item_id=w.id AND op.partner_id=%s AND op.sent_at >= %s AND op.sent_at < %s))
                    GROUP BY COALESCE(NULLIF(ae.actor_id,''),'__system__') ORDER BY activity_count DESC,buyer""",
                    (start,end,buyer,buyer,partner_id,partner_id,start,end))
                buyer_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("""SELECT p.partner_name, COUNT(DISTINCT w.id) AS distinct_requests_asked,
                    COUNT(DISTINCT r.id) AS sites_sent, COUNT(DISTINCT o.id) AS outreach_records,
                    COUNT(DISTINCT w.id) FILTER (WHERE o.response_status IN ('responded','partial_response','no_bid')) AS requests_with_partner_response
                    FROM leasing.partner_outreaches o JOIN leasing.partners p ON p.id=o.partner_id
                    JOIN leasing.work_items w ON w.id=o.work_item_id
                    LEFT JOIN leasing.outreach_requirements oro ON oro.outreach_id=o.id
                    LEFT JOIN leasing.requirements r ON r.id=oro.requirement_id
                    WHERE o.sent_at >= %s AND o.sent_at < %s AND (%s IS NULL OR o.created_by=%s)
                      AND (%s IS NULL OR o.partner_id=%s)
                    GROUP BY p.id,p.partner_name ORDER BY distinct_requests_asked DESC,p.partner_name""",
                    (start,end,buyer,buyer,partner_id,partner_id))
                vendor_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("""SELECT COALESCE(NULLIF(o.created_by,''),'__system__') AS buyer,
                    p.partner_name, COUNT(DISTINCT w.id) AS distinct_requests_asked,
                    COUNT(DISTINCT r.id) AS sites_sent, COUNT(DISTINCT o.id) AS outreach_records
                    FROM leasing.partner_outreaches o JOIN leasing.partners p ON p.id=o.partner_id
                    JOIN leasing.work_items w ON w.id=o.work_item_id
                    LEFT JOIN leasing.outreach_requirements oro ON oro.outreach_id=o.id
                    LEFT JOIN leasing.requirements r ON r.id=oro.requirement_id
                    WHERE o.sent_at >= %s AND o.sent_at < %s
                      AND (%s IS NULL OR o.created_by=%s) AND (%s IS NULL OR o.partner_id=%s)
                    GROUP BY COALESCE(NULLIF(o.created_by,''),'__system__'),p.id,p.partner_name
                    ORDER BY buyer,p.partner_name""",
                    (start,end,buyer,buyer,partner_id,partner_id))
                buyer_vendor_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("""SELECT o.sent_at, w.request_id, w.work_type, c.customer_name, w.buyer_owner_id, o.created_by AS outreach_created_by,
                    p.partner_name, o.outreach_round, o.response_status, COUNT(DISTINCT oro.requirement_id) AS sites_sent,
                    o.next_follow_up_at, o.follow_up_owner_id, o.notes
                    FROM leasing.partner_outreaches o JOIN leasing.work_items w ON w.id=o.work_item_id
                    JOIN leasing.partners p ON p.id=o.partner_id LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    LEFT JOIN leasing.outreach_requirements oro ON oro.outreach_id=o.id
                    WHERE o.sent_at >= %s AND o.sent_at < %s AND (%s IS NULL OR o.created_by=%s)
                      AND (%s IS NULL OR o.partner_id=%s)
                    GROUP BY o.id,w.id,c.customer_name,p.partner_name ORDER BY o.sent_at,p.partner_name,w.request_id""",
                    (start,end,buyer,buyer,partner_id,partner_id))
                outreach_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("""WITH outreach_sites AS (
                    SELECT o.id AS outreach_id,w.request_id,w.work_type,w.project_name,c.customer_name,p.partner_name,
                        o.outreach_round,o.sent_at,o.response_status AS outreach_status,o.next_follow_up_at,o.created_by,
                        r.id AS requirement_id,r.requirement_no,r.site_name,r.zone,r.address,r.requested_services,r.service_type,
                        oro.response_status AS site_response_status,oro.response_note,
                        CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                            ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END AS service_names
                    FROM leasing.partner_outreaches o JOIN leasing.work_items w ON w.id=o.work_item_id
                    JOIN leasing.partners p ON p.id=o.partner_id LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    JOIN leasing.outreach_requirements oro ON oro.outreach_id=o.id
                    JOIN leasing.requirements r ON r.id=oro.requirement_id
                    WHERE o.sent_at >= %s AND o.sent_at < %s AND (%s IS NULL OR o.created_by=%s)
                      AND (%s IS NULL OR o.partner_id=%s)
                ), requested AS (
                    SELECT os.request_id,os.work_type,os.project_name,os.customer_name,os.partner_name,os.outreach_round,
                        os.sent_at,os.outreach_status,os.next_follow_up_at,os.created_by,os.requirement_id,os.requirement_no,
                        os.site_name,os.zone,os.address,os.requested_services,svc.service_name,TRUE AS is_requested_service,
                        CASE WHEN sl.feasibility_status IS NOT NULL AND sl.feasibility_status <> 'pending' THEN sl.feasibility_status
                            WHEN pl.feasibility_status='cannot_provide' OR os.site_response_status='cannot_provide' THEN 'cannot_provide'
                            WHEN pl.feasibility_status='can_provide' AND CARDINALITY(os.service_names)<=1 THEN 'can_provide'
                            WHEN os.site_response_status='can_provide' AND CARDINALITY(os.service_names)<=1 THEN 'can_provide'
                            WHEN pl.feasibility_status='can_provide' OR os.site_response_status='can_provide' THEN 'needs_clarification'
                            WHEN pl.feasibility_status='needs_clarification' OR os.site_response_status='needs_clarification' THEN 'needs_clarification'
                            WHEN os.sent_at IS NULL THEN 'draft' WHEN sl.feasibility_status='pending' THEN 'pending'
                            ELSE COALESCE(os.site_response_status,'awaiting_response') END AS coverage_status,
                        sl.mrc_amount,sl.otc_amount,sl.currency,COALESCE(sl.notes,os.response_note) AS notes,COALESCE(sl.version_no,pl.version_no) AS offer_version
                    FROM outreach_sites os CROSS JOIN LATERAL unnest(os.service_names) AS svc(service_name)
                    LEFT JOIN LATERAL (SELECT po.version_no,x.feasibility_status,x.mrc_amount,x.otc_amount,x.currency,x.notes
                        FROM leasing.partner_offers po JOIN leasing.partner_offer_service_lines x ON x.offer_id=po.id
                        WHERE po.outreach_id=os.outreach_id AND po.offer_status='current' AND x.requirement_id=os.requirement_id
                          AND LOWER(BTRIM(x.service_name))=LOWER(BTRIM(svc.service_name)) ORDER BY po.version_no DESC LIMIT 1) sl ON TRUE
                    LEFT JOIN LATERAL (SELECT po.version_no,x.feasibility_status FROM leasing.partner_offers po
                        JOIN leasing.partner_offer_lines x ON x.offer_id=po.id
                        WHERE po.outreach_id=os.outreach_id AND po.offer_status='current' AND x.requirement_id=os.requirement_id
                        ORDER BY po.version_no DESC LIMIT 1) pl ON TRUE
                ), extras AS (
                    SELECT os.request_id,os.work_type,os.project_name,os.customer_name,os.partner_name,os.outreach_round,
                        os.sent_at,os.outreach_status,os.next_follow_up_at,os.created_by,os.requirement_id,os.requirement_no,
                        os.site_name,os.zone,os.address,os.requested_services,x.service_name,FALSE AS is_requested_service,
                        x.feasibility_status AS coverage_status,x.mrc_amount,x.otc_amount,x.currency,x.notes,po.version_no AS offer_version
                    FROM outreach_sites os JOIN leasing.partner_offers po ON po.outreach_id=os.outreach_id AND po.offer_status='current'
                    JOIN leasing.partner_offer_service_lines x ON x.offer_id=po.id AND x.requirement_id=os.requirement_id
                    WHERE NOT EXISTS (SELECT 1 FROM unnest(os.service_names) AS s(n) WHERE LOWER(BTRIM(s.n))=LOWER(BTRIM(x.service_name)))
                )
                SELECT * FROM requested UNION ALL SELECT * FROM extras
                ORDER BY partner_name,request_id,outreach_round,requirement_no,service_name""",
                    (start,end,buyer,buyer,partner_id,partner_id))
                vendor_service_rows = [dict(r) for r in cur.fetchall()]
                cur.execute("""SELECT ae.occurred_at, ae.actor_id, w.request_id, w.work_type,
                    w.buyer_owner_id, c.customer_name, ae.event_type, ae.event_summary, ae.metadata
                    FROM leasing.activity_events ae JOIN leasing.work_items w ON w.id=ae.work_item_id
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    WHERE ae.occurred_at >= %s AND ae.occurred_at < %s
                      AND (%s IS NULL OR ae.actor_id=%s)
                      AND (%s IS NULL OR EXISTS (SELECT 1 FROM leasing.partner_outreaches op WHERE op.work_item_id=w.id AND op.partner_id=%s AND op.sent_at >= %s AND op.sent_at < %s))
                    ORDER BY ae.occurred_at,w.request_id""",
                    (start,end,buyer,buyer,partner_id,partner_id,start,end))
                activity_rows = [dict(r) for r in cur.fetchall()]
        wb = Workbook()
        ws = wb.active; ws.title = "Monthly Summary"
        ws.append(["Leasing Monthly Report", month_key]); ws.append(["Buyer filter", buyer or "All buyers"]); ws.append(["Vendor filter", partner_id or "All vendors"])
        ws.append(["Metric", "Value", "Definition"])
        definitions = [
            ("Work Items received", summary.get("items_received",0), "Work Items yang diterima pada bulan terpilih, dikelompokkan menurut owner saat ini (bukan histori assignment)."),
            ("Work Items in period", summary.get("work_items_in_period",0), "Jumlah Work Item unik pada sheet Work Items: owner saat ini, atau ada aktivitas/outreach yang dibuat buyer terpilih selama bulan tersebut."),
            ("Work Items touched (current owner)", summary.get("items_with_activity",0), "Work Items milik owner saat ini yang memiliki activity event pada bulan terpilih; actor aktual dirinci di sheet Buyer Activity."),
            ("Outreach records sent", summary.get("outreach_sent",0), "Baris outreach yang dibuat/dikirim oleh Buyer terpilih pada bulan tersebut; satu baris per komunikasi/round."),
            ("Project Work Items in period", summary.get("project_work_items",0), "Project milik owner saat ini yang diterima, disentuh, atau dikirimi outreach pada bulan terpilih."),
            ("Vendor requests asked", sum(int(x.get("distinct_requests_asked") or 0) for x in vendor_rows), "Jumlah request unik per vendor; satu request ke beberapa vendor dihitung sekali per vendor.")]
        for row in definitions: ws.append(list(row))
        _leasing_style_report_sheet(ws); ws.column_dimensions["A"].width=30; ws.column_dimensions["B"].width=22; ws.column_dimensions["C"].width=92
        def add_sheet(title, records):
            sheet=wb.create_sheet(title)
            if records:
                columns=list(records[0].keys()); sheet.append(columns)
                for record in records: sheet.append([_leasing_excel_safe(record.get(col)) for col in columns])
            else: sheet.append(["No records"]); sheet.append(["Tidak ada data untuk filter yang dipilih."])
            _leasing_style_report_sheet(sheet); sheet.sheet_view.showGridLines=False; sheet.freeze_panes="A2"; sheet.auto_filter.ref=sheet.dimensions
        add_sheet("Work Items",work_rows); add_sheet("Requirements - Sites",site_rows)
        add_sheet("Buyer Activity",buyer_rows); add_sheet("Vendor Monthly Requests",vendor_rows)
        add_sheet("Vendor Service Coverage",vendor_service_rows)
        add_sheet("Buyer x Vendor",buyer_vendor_rows); add_sheet("Outreach Detail",outreach_rows)
        add_sheet("Activity Log",activity_rows)
        output=BytesIO(); wb.save(output); output.seek(0)
        safe_buyer=secure_filename(buyer or "all_buyers") or "all_buyers"
        return send_file(output,mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",as_attachment=True,
                         download_name=f"leasing_monthly_{month_key}_{safe_buyer}.xlsx")
    except psycopg2.Error:
        app.logger.exception("Leasing monthly report query failed")
        return jsonify({"success": False, "message": "Laporan bulanan gagal dibuat. Pastikan migration Project/Non-Project sudah diterapkan di leasing_db."}), 500
    except Exception:
        app.logger.exception("Leasing monthly report generation failed")
        return jsonify({"success": False, "message": "Laporan bulanan gagal dibuat. Periksa log aplikasi."}), 500


# ---------------------------------------------------------------------------
# Scalable partner response workflow: Excel template round-trip + Work Item report
# ---------------------------------------------------------------------------
def _leasing_style_report_sheet(ws):
    ws.freeze_panes = "A2"
    if ws.max_row >= 1 and ws.max_column >= 1:
        ws.auto_filter.ref = ws.dimensions
    ws.row_dimensions[1].height = 32
    header_fill = PatternFill("solid", fgColor="24345B")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF", size=10)
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center", horizontal="left", wrap_text=True)
    for col in ws.columns:
        letter = col[0].column_letter
        max_len = min(42, max(12, max((len(str(c.value or "")) for c in list(col)[:250]), default=12)))
        ws.column_dimensions[letter].width = max_len
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            if cell.row % 2 == 0:
                cell.fill = PatternFill("solid", fgColor="F6F8FC")


def _leasing_excel_safe(value):
    if value is None:
        return None
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    if hasattr(value, "isoformat"):
        try: return value.isoformat(sep=" ")
        except TypeError: return value.isoformat()
    if isinstance(value, str) and value.lstrip(" \t\r\n").startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _leasing_record_offer_version(cur, outreach_id, incoming_lines, username, source,
                                  offer_notes=None, received_at=None, valid_until=None,
                                  source_label=None, incoming_service_lines=None):
    """Create an immutable offer version with independent, arbitrary service coverage.

    Site-level data in partner_offer_lines remains for compatibility. Arbitrary service names
    are stored in partner_offer_service_lines per site + offer version + service. Blank prices
    preserve existing values; coverage is not conflated with price completeness.
    """
    incoming_service_lines = list(incoming_service_lines or [])
    cur.execute("SELECT id, work_item_id FROM leasing.partner_outreaches WHERE id=%s FOR UPDATE", (outreach_id,))
    outreach = cur.fetchone()
    if not outreach:
        raise LookupError("Outreach tidak ditemukan.")
    cur.execute("SELECT requirement_id FROM leasing.outreach_requirements WHERE outreach_id=%s", (outreach_id,))
    allowed_ids = {int(row["requirement_id"]) for row in cur.fetchall()}
    if not allowed_ids:
        raise ValueError("Outreach ini belum memiliki requirement yang dikirim.")

    cur.execute("""SELECT id, requested_services, service_type FROM leasing.requirements
        WHERE work_item_id=%s AND id=ANY(%s)""", (outreach["work_item_id"], list(allowed_ids)))
    req_meta = {int(row["id"]): dict(row) for row in cur.fetchall()}
    requested_by_id = {}
    for req_id, req in req_meta.items():
        names = _leasing_normalize_service_names(req.get("requested_services"), req.get("service_type"))
        requested_by_id[req_id] = names

    incoming = {}
    legacy_price_fields = ("mrc_inet_dedicated_25_amount", "mrc_metro_25_amount")
    all_legacy_prices = ("mrc_amount", "otc_amount", *legacy_price_fields)
    for raw_line in incoming_lines or []:
        line = dict(raw_line)
        req_id = int(line["requirement_id"])
        if req_id in incoming:
            raise ValueError(f"Requirement ID {req_id} muncul lebih dari sekali pada sheet Offer Input.")
        if req_id not in allowed_ids:
            raise ValueError(f"Requirement ID {req_id} bukan bagian dari outreach ini.")
        if line.get("feasibility_status") not in (None, "") and line.get("feasibility_status") not in {"pending", "can_provide", "cannot_provide", "needs_clarification"}:
            raise ValueError(f"Requirement ID {req_id}: status coverage tidak valid.")
        for field in all_legacy_prices:
            value = line.get(field)
            if value not in (None, ""):
                try: value=float(value)
                except (TypeError, ValueError): raise ValueError(f"Requirement ID {req_id}: {field} harus angka valid.")
                if not math.isfinite(value) or value < 0: raise ValueError(f"Requirement ID {req_id}: harga tidak boleh negatif.")
                line[field]=value
            else: line[field]=None
        if line.get("feasibility_status") == "pending" and any(line.get(k) is not None for k in all_legacy_prices):
            raise ValueError(f"Requirement ID {req_id}: pilih Can provide sebelum memasukkan harga.")
        line["requirement_id"] = req_id
        incoming[req_id] = line

    normalized_services, seen_services = [], set()
    for line_no, raw_line in enumerate(incoming_service_lines, start=1):
        line = dict(raw_line)
        try: req_id = int(line.get("requirement_id"))
        except (TypeError, ValueError): raise ValueError(f"Baris service {line_no}: Requirement ID harus bilangan bulat.")
        if req_id not in allowed_ids:
            raise ValueError(f"Baris service {line_no}: Requirement ID {req_id} bukan bagian dari outreach ini.")
        service_name = re.sub(r"\s+", " ", str(line.get("service_name") or "").strip())
        if not service_name:
            raise ValueError(f"Baris service {line_no}: Service Name wajib diisi.")
        if len(service_name) > 160:
            raise ValueError(f"Baris service {line_no}: Service Name maksimal 160 karakter.")
        service_key = (req_id, service_name.casefold())
        if service_key in seen_services:
            raise ValueError(f"Baris service {line_no}: jasa '{service_name}' duplikat untuk Requirement ID {req_id}.")
        seen_services.add(service_key)
        status = str(line.get("feasibility_status") or "").strip().lower() or None
        if status and status not in {"pending", "can_provide", "cannot_provide", "needs_clarification"}:
            raise ValueError(f"Baris service {line_no}: status coverage tidak valid: {status}.")
        amount_fields = ("mrc_amount", "otc_amount")
        for field in amount_fields:
            value=line.get(field)
            if value in (None, ""):
                line[field]=None
                continue
            try: value=float(value)
            except (TypeError, ValueError): raise ValueError(f"Baris service {line_no}: {field} harus angka valid.")
            if not math.isfinite(value) or value < 0: raise ValueError(f"Baris service {line_no}: harga tidak boleh negatif.")
            line[field]=value
        clear = line.get("clear_existing_prices") in (True, 1, "1", "yes", "YES", "true", "TRUE", "y", "Y")
        has_price=any(line.get(k) is not None for k in amount_fields)
        if status == "pending" and has_price:
            raise ValueError(f"Baris service {line_no}: pilih can_provide sebelum memasukkan harga.")
        if status == "cannot_provide" and has_price:
            raise ValueError(f"Baris service {line_no}: harga tidak boleh diisi bila jasa tidak dapat disediakan.")
        currency=str(line.get("currency") or "").strip().upper() or None
        if has_price and (not currency or not re.fullmatch(r"[A-Z]{3}", currency)):
            raise ValueError(f"Baris service {line_no}: Currency wajib kode 3 huruf saat harga diisi.")
        notes=str(line.get("notes") or "").strip() or None
        if not (status or has_price or notes or clear):
            continue
        if not status and has_price: status="can_provide"
        normalized_services.append({"requirement_id":req_id,"service_name":service_name,
            "service_key":service_key,"feasibility_status":status,"mrc_amount":line.get("mrc_amount"),
            "otc_amount":line.get("otc_amount"),"currency":currency,"notes":notes,"clear_existing_prices":clear})

    if not incoming and not normalized_services:
        raise ValueError("Tidak ada baris respons site atau jasa yang dapat disimpan.")

    cur.execute("""SELECT id, version_no, notes, valid_until FROM leasing.partner_offers
        WHERE outreach_id=%s AND offer_status='current' ORDER BY version_no DESC LIMIT 1 FOR UPDATE""", (outreach_id,))
    previous_offer = cur.fetchone()
    merged = {}
    cur.execute("""SELECT pol.requirement_id, pol.feasibility_status, pol.mrc_amount, pol.otc_amount,
        pol.mrc_inet_dedicated_25_amount, pol.mrc_metro_25_amount, pol.currency, pol.notes, po.version_no
        FROM leasing.partner_offer_lines pol JOIN leasing.partner_offers po ON po.id=pol.offer_id
        WHERE po.outreach_id=%s AND po.offer_status='current'
        ORDER BY po.version_no DESC, pol.requirement_id""", (outreach_id,))
    for old_line in cur.fetchall():
        req_id=int(old_line["requirement_id"])
        if req_id not in merged:
            merged[req_id]={k:old_line[k] for k in ("requirement_id","feasibility_status","mrc_amount","otc_amount",*legacy_price_fields,"currency","notes")}

    legacy_before_by_req = {req_id: dict(line) for req_id, line in merged.items()}
    all_price_fields=all_legacy_prices
    for req_id,new_line in incoming.items():
        old_line=merged.get(req_id)
        clear=bool(new_line.get("clear_existing_prices"))
        new_has_price=any(new_line.get(k) is not None for k in all_price_fields)
        old_has_price=bool(old_line and any(old_line.get(k) is not None for k in all_price_fields))
        new_currency=str(new_line.get("currency") or "").strip().upper() or None
        old_currency=old_line.get("currency") if old_line else None
        if old_line and not new_line.get("feasibility_status"):
            new_line["feasibility_status"]=old_line.get("feasibility_status") or "pending"
        elif not old_line and not new_line.get("feasibility_status"):
            new_line["feasibility_status"]="needs_clarification"
        if old_line and new_line.get("notes") in (None, ""):
            new_line["notes"]=old_line.get("notes")
        if new_line.get("feasibility_status")=="cannot_provide":
            for field in all_price_fields:new_line[field]=None
            new_line["currency"]=None; new_line["clear_existing_prices"]=True
            continue
        if old_line and not clear:
            if old_has_price and new_currency and old_currency and new_currency != old_currency:
                raise ValueError(f"Requirement ID {req_id}: currency baru ({new_currency}) berbeda dari currency lama ({old_currency}). Reset harga secara eksplisit dan isi kembali nilai yang ingin dipertahankan.")
            for field in all_price_fields:
                if new_line.get(field) is None:new_line[field]=old_line.get(field)
            new_line["currency"]=new_currency or old_currency
            if new_line.get("notes") in (None, ""):new_line["notes"]=old_line.get("notes")
            if new_line.get("feasibility_status")=="pending" and not new_has_price and not clear:
                new_line["feasibility_status"]=old_line.get("feasibility_status") or "pending"
        elif clear and not new_has_price:
            new_line["currency"]=None
        new_line["clear_existing_prices"]=clear
    merged.update(incoming)

    # Load current arbitrary-service lines, then merge only fields explicitly changed.
    service_merged = {}
    cur.execute("""SELECT osl.requirement_id, osl.service_name, osl.feasibility_status, osl.mrc_amount,
        osl.otc_amount, osl.currency, osl.notes
        FROM leasing.partner_offer_service_lines osl
        JOIN leasing.partner_offers po ON po.id=osl.offer_id
        WHERE po.outreach_id=%s AND po.offer_status='current'
        ORDER BY po.version_no DESC, osl.requirement_id, osl.service_name""", (outreach_id,))
    for old in cur.fetchall():
        key=(int(old["requirement_id"]), str(old["service_name"]).casefold())
        if key not in service_merged:
            service_merged[key]={"requirement_id":int(old["requirement_id"]),"service_name":old["service_name"],
                "feasibility_status":old["feasibility_status"],"mrc_amount":old["mrc_amount"],"otc_amount":old["otc_amount"],
                "currency":old["currency"],"notes":old["notes"]}
    service_before_by_key = {key: dict(line) for key, line in service_merged.items()}
    for new_line in normalized_services:
        key=new_line["service_key"]
        old=service_merged.get(key)
        new=dict(new_line)
        clear=bool(new.get("clear_existing_prices"))
        has_price=any(new.get(k) is not None for k in ("mrc_amount","otc_amount"))
        if old and not new.get("feasibility_status"):
            new["feasibility_status"]=old.get("feasibility_status") or "pending"
        elif not old and not new.get("feasibility_status"):
            new["feasibility_status"]="needs_clarification"
        if old and not new.get("notes"):new["notes"]=old.get("notes")
        if new.get("feasibility_status")=="cannot_provide":
            new["mrc_amount"]=None;new["otc_amount"]=None;new["currency"]=None
        elif old and not clear:
            old_has_price=old.get("mrc_amount") is not None or old.get("otc_amount") is not None
            if old_has_price and new.get("currency") and old.get("currency") and new["currency"] != old["currency"]:
                raise ValueError(f"Requirement ID {key[0]}, jasa '{new['service_name']}': currency berubah. Pilih Clear Existing Prices? = YES lalu isi harga yang ingin dipertahankan.")
            if new.get("mrc_amount") is None:new["mrc_amount"]=old.get("mrc_amount")
            if new.get("otc_amount") is None:new["otc_amount"]=old.get("otc_amount")
            if not new.get("currency"):new["currency"]=old.get("currency")
        elif clear and not has_price:
            new["currency"]=None
        new.pop("service_key",None);new.pop("clear_existing_prices",None)
        service_merged[key]=new

    # A site-level cannot_provide means none of the requested services can be provided.
    # Reject only if the SAME update explicitly says a service can_provide; a previous
    # active snapshot is not a contradiction and must be withdrawable by the buyer.
    for req_id,line in incoming.items():
        if line.get("feasibility_status") != "cannot_provide":continue
        contradictory=[v["service_name"] for v in normalized_services
                       if int(v["requirement_id"])==req_id and v.get("feasibility_status")=="can_provide"]
        if contradictory:
            raise ValueError(f"Requirement ID {req_id}: status site Cannot provide bertentangan dengan status jasa Can provide pada update ini: {', '.join(contradictory)}.")
        service_names=requested_by_id.get(req_id) or []
        for name in service_names:
            service_merged[(req_id,name.casefold())]={"requirement_id":req_id,"service_name":name,
                "feasibility_status":"cannot_provide","mrc_amount":None,"otc_amount":None,"currency":None,"notes":line.get("notes")}

    # When a service-only sheet is used, keep the site snapshot complete without overwriting
    # previously entered site-level commercial values.
    if normalized_services:
        for req_id in allowed_ids:
            merged.setdefault(req_id,{"requirement_id":req_id,"feasibility_status":"pending","mrc_amount":None,
                "otc_amount":None,"mrc_inet_dedicated_25_amount":None,"mrc_metro_25_amount":None,"currency":None,"notes":None})

    retained_line_count=sum(1 for req_id in merged if req_id not in incoming)
    cur.execute("SELECT COALESCE(MAX(version_no),0)+1 AS v FROM leasing.partner_offers WHERE outreach_id=%s",(outreach_id,))
    version=int(cur.fetchone()["v"])
    cur.execute("UPDATE leasing.partner_offers SET offer_status='superseded' WHERE outreach_id=%s AND offer_status='current'",(outreach_id,))
    effective_notes=str(offer_notes).strip() if offer_notes is not None and str(offer_notes).strip() else (previous_offer["notes"] if previous_offer else None)
    effective_valid_until=valid_until if valid_until not in (None, "") else (previous_offer["valid_until"] if previous_offer else None)
    cur.execute("""INSERT INTO leasing.partner_offers (outreach_id, version_no, received_at, valid_until, notes, created_by)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",(outreach_id,version,received_at or datetime.now(),effective_valid_until,effective_notes,username))
    offer_id=cur.fetchone()["id"]
    for req_id in sorted(merged):
        line=merged[req_id]
        cur.execute("""INSERT INTO leasing.partner_offer_lines
            (offer_id, requirement_id, feasibility_status, mrc_amount, otc_amount,
             mrc_inet_dedicated_25_amount, mrc_metro_25_amount, currency, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (offer_id,req_id,line.get("feasibility_status") or "pending",line.get("mrc_amount"),line.get("otc_amount"),
             line.get("mrc_inet_dedicated_25_amount"),line.get("mrc_metro_25_amount"),line.get("currency"),line.get("notes")))
    for key in sorted(service_merged):
        line=service_merged[key]
        cur.execute("""INSERT INTO leasing.partner_offer_service_lines
            (offer_id, requirement_id, service_name, feasibility_status, mrc_amount, otc_amount, currency, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
            (offer_id,line["requirement_id"],line["service_name"],line.get("feasibility_status") or "pending",
             line.get("mrc_amount"),line.get("otc_amount"),line.get("currency"),line.get("notes")))

    # Persist field-level commercial audit only for changed site/service rows. The immutable
    # offer version is the after-snapshot; previous values are retained in the audit event.
    legacy_audit_fields = ("feasibility_status", "mrc_amount", "otc_amount",
                           "mrc_inet_dedicated_25_amount", "mrc_metro_25_amount", "currency", "notes")
    for req_id, line in merged.items():
        before_line = legacy_before_by_req.get(req_id)
        before_values = {k: (before_line or {}).get(k) for k in legacy_audit_fields}
        after_values = {k: line.get(k) for k in legacy_audit_fields}
        if before_line is None or before_values != after_values:
            _leasing_field_audit(cur, "partner_offer_requirement", req_id, outreach["work_item_id"],
                "create" if before_line is None else "update", username,
                before_values if before_line else {},
                {**after_values, "offer_id": offer_id, "version_no": version},
                "Partner offer version recorded")
    service_audit_fields = ("service_name", "feasibility_status", "mrc_amount", "otc_amount", "currency", "notes")
    for key, line in service_merged.items():
        before_line = service_before_by_key.get(key)
        before_values = {k: (before_line or {}).get(k) for k in service_audit_fields}
        after_values = {k: line.get(k) for k in service_audit_fields}
        if before_line is None or before_values != after_values:
            _leasing_field_audit(cur, "partner_offer_service", int(key[0]), outreach["work_item_id"],
                "create" if before_line is None else "update", username,
                before_values if before_line else {},
                {**after_values, "offer_id": offer_id, "version_no": version},
                "Partner service offer version recorded")

    # Calculate site-level coverage status from generic service names, not fixed service enums.
    coverage_by_req={}
    fully_answered_by_req={}
    for req_id in allowed_ids:
        base=merged.get(req_id,{})
        requested=requested_by_id.get(req_id) or []
        if base.get("feasibility_status")=="cannot_provide":
            state="cannot_provide"
        elif not requested:
            state=base.get("feasibility_status") or "pending"
        else:
            states=[]
            for service in requested:
                item=service_merged.get((req_id,service.casefold()))
                service_state=item.get("feasibility_status") if item else None
                if not service_state or service_state=="pending":
                    # Compatibility for single-service legacy records: site-level coverage applies.
                    if len(requested)==1 and base.get("feasibility_status") in {"can_provide","cannot_provide"}:
                        service_state=base.get("feasibility_status")
                    elif base.get("feasibility_status")=="can_provide":
                        service_state="needs_clarification"
                    else: service_state="pending"
                states.append(service_state)
            if states and all(x=="can_provide" for x in states):state="can_provide"
            elif states and all(x=="cannot_provide" for x in states):state="cannot_provide"
            elif all(x in {"can_provide","cannot_provide"} for x in states):state="needs_clarification"
            elif any(x in {"can_provide","cannot_provide","needs_clarification"} for x in states):state="needs_clarification"
            else:state="pending"
        coverage_by_req[req_id]=state
        if base.get("feasibility_status")=="cannot_provide":
            fully_answered_by_req[req_id]=True
        elif requested:
            resolved_states=[]
            for service in requested:
                item=service_merged.get((req_id,service.casefold()))
                service_state=item.get("feasibility_status") if item else None
                if (not service_state or service_state=="pending") and len(requested)==1 and base.get("feasibility_status") in {"can_provide","cannot_provide"}:
                    service_state=base.get("feasibility_status")
                resolved_states.append(service_state in {"can_provide","cannot_provide"})
            fully_answered_by_req[req_id]=bool(resolved_states) and all(resolved_states)
        else:
            fully_answered_by_req[req_id]=state in {"can_provide","cannot_provide"}
        response_note=base.get("notes")
        if not response_note:
            service_notes=[v.get("notes") for k,v in service_merged.items() if k[0]==req_id and v.get("notes")]
            response_note="; ".join(dict.fromkeys(service_notes)) if service_notes else None
        cur.execute("""UPDATE leasing.outreach_requirements SET response_status=%s, response_note=%s
            WHERE outreach_id=%s AND requirement_id=%s""",
            ({"pending":"awaiting_response","can_provide":"can_provide","cannot_provide":"cannot_provide","needs_clarification":"needs_clarification"}.get(state,"awaiting_response"),response_note,outreach_id,req_id))

    complete_count=sum(1 for req_id in allowed_ids if fully_answered_by_req.get(req_id,False))
    responded_count=sum(1 for state in coverage_by_req.values() if state in {"can_provide","cannot_provide","needs_clarification"})
    total_count=len(allowed_ids)
    if complete_count==total_count and total_count:response_status="responded"
    elif responded_count:response_status="partial_response"
    else:response_status="awaiting_response"
    now=datetime.now()
    cur.execute("""UPDATE leasing.partner_outreaches SET response_status=%s,
        responded_at=CASE WHEN %s THEN %s ELSE responded_at END,
        next_follow_up_at=CASE WHEN %s THEN NULL ELSE next_follow_up_at END WHERE id=%s""",
        (response_status,responded_count>0,now,response_status=="responded",outreach_id))
    leasing_activity(cur,outreach["work_item_id"],"partner_offer_recorded","Penawaran partner diperbarui",username,
        {"offer_id":offer_id,"version_no":version,"source":source,"imported_line_count":len(incoming),
         "imported_service_line_count":len(normalized_services),"current_line_count":len(merged),
         "current_service_line_count":len(service_merged),"retained_line_count":retained_line_count,
         "response_status":response_status,"source_label":source_label})
    return {"offer_id":offer_id,"version_no":version,"line_count":len(incoming),
        "service_line_count":len(normalized_services),"current_line_count":len(merged),
        "current_service_line_count":len(service_merged),"retained_line_count":retained_line_count,
        "response_status":response_status}


@app.route("/api/leasing/outreaches/<int:outreach_id>/offer-template.xlsx", methods=["GET"])
@leasing_login_required
def leasing_offer_template_xlsx(outreach_id):
    """Download a partner-specific spreadsheet containing only sites in this outreach."""
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT o.id, o.work_item_id, o.outreach_round, p.partner_name, w.request_id,
                    c.customer_name FROM leasing.partner_outreaches o
                    JOIN leasing.partners p ON p.id=o.partner_id
                    JOIN leasing.work_items w ON w.id=o.work_item_id
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id WHERE o.id=%s""", (outreach_id,))
                outreach = cur.fetchone()
                if not outreach:
                    return jsonify({"success": False, "message": "Outreach tidak ditemukan."}), 404
                cur.execute("""SELECT r.id AS requirement_id, r.requirement_no, r.work_item_id, r.area, r.address,
                    r.gedung_kawasan, r.latitude, r.longitude, r.si, r.a_end, r.z_end,
                    r.bandwidth, r.bandwidth_unit, r.service_type, r.zone, r.site_name, r.postal_code,
                    r.project_mrc_inet_dedicated_25, r.project_mrc_metro_25, r.requested_otc,
                    r.requested_services, w.work_type
                    FROM leasing.outreach_requirements oro
                    JOIN leasing.requirements r ON r.id=oro.requirement_id
                    JOIN leasing.work_items w ON w.id=r.work_item_id
                    WHERE oro.outreach_id=%s ORDER BY r.requirement_no""", (outreach_id,))
                requirements = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT pol.requirement_id, pol.currency
                    FROM leasing.partner_offers po
                    JOIN leasing.partner_offer_lines pol ON pol.offer_id=po.id
                    WHERE po.outreach_id=%s AND po.offer_status='current'
                    ORDER BY po.version_no DESC, pol.requirement_id""", (outreach_id,))
                current_currency_by_requirement = {}
                for currency_row in cur.fetchall():
                    current_currency_by_requirement.setdefault(int(currency_row["requirement_id"]), currency_row.get("currency"))
                cur.execute("""SELECT osl.requirement_id, osl.service_name, osl.feasibility_status, osl.mrc_amount,
                    osl.otc_amount, osl.currency, osl.notes FROM leasing.partner_offer_service_lines osl
                    JOIN leasing.partner_offers po ON po.id=osl.offer_id
                    WHERE po.outreach_id=%s AND po.offer_status='current'
                    ORDER BY po.version_no DESC, osl.requirement_id, osl.service_name""", (outreach_id,))
                current_service_rows = [dict(x) for x in cur.fetchall()]
                current_service_by_key = {}
                for item in current_service_rows:
                    current_service_by_key.setdefault((int(item["requirement_id"]), str(item["service_name"]).casefold()), item)
        if not requirements:
            return jsonify({"success": False, "message": "Outreach ini belum memiliki requirement terkait. Catat ulang outreach dengan memilih lokasi yang dikirim."}), 409
        wb = Workbook()
        ws = wb.active
        ws.title = "Offer Input"
        is_project = any(row.get("work_type") == "project" for row in requirements)
        # Keep the legacy site-level sheet generic for compatibility. For service-specific answers,
        # buyers should use the Service Responses sheet below (one row per site × arbitrary service).
        if is_project:
            headers = ["Requirement ID", "Requirement No", "Zone", "Site", "Address", "Postal Code", "Requested Services",
                       "Feasibility Status", "MRC", "OTC", "Currency", "Clear Existing Prices?", "Notes"]
        else:
            headers = ["Requirement ID", "Requirement No", "Area", "Address", "Building / Complex", "Latitude", "Longitude", "SI", "A-End", "Z-End", "Bandwidth", "Bandwidth Unit", "Requested Services",
                       "Feasibility Status", "MRC", "OTC", "Currency", "Clear Existing Prices?", "Notes"]
        ws.append(headers)
        for row in requirements:
            service_names = _leasing_normalize_service_names(row.get("requested_services"), row.get("service_type"))
            if is_project:
                details = [row.get("requirement_id"), row.get("requirement_no"), row.get("zone"), row.get("site_name"), row.get("address"), row.get("postal_code"), "; ".join(service_names)]
                # Currency is intentionally blank here: separate service lines can use different currencies.
                ws.append([_leasing_excel_safe(v) for v in details] + [None, None, None, None, None, None])
            else:
                details = [row.get(k) for k in ["requirement_id", "requirement_no", "area", "address", "gedung_kawasan", "latitude", "longitude", "si", "a_end", "z_end", "bandwidth", "bandwidth_unit"]] + ["; ".join(service_names)]
                ws.append([_leasing_excel_safe(v) for v in details] + [None, None, None, None, None, None])
        _leasing_style_report_sheet(ws)
        # Commercial response columns are editable; site/request identity remains unchanged.
        response_start = 7 if is_project else 13
        for cell in ws[1][response_start:]:
            cell.fill = PatternFill("solid", fgColor="16765B")
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"
        ws.column_dimensions["D"].width = 34
        ws.column_dimensions["E"].width = 24
        ws.column_dimensions["F"].width = 13
        ws.column_dimensions["G"].width = 13
        ws.column_dimensions["A"].width = 16
        ws.column_dimensions["D"].width = 34
        ws.column_dimensions["E"].width = 34
        ws.column_dimensions["M" if is_project else "S"].width = 42
        ws.column_dimensions["L" if is_project else "R"].width = 20
        if requirements:
            last_row = len(requirements) + 1
            dv = DataValidation(type="list", formula1='"pending,can_provide,cannot_provide,needs_clarification"', allow_blank=True)
            status_col = "H" if is_project else "N"
            dv.add(f"{status_col}2:{status_col}{last_row}")
            ws.add_data_validation(dv)
            clear_prices_validation = DataValidation(type="list", formula1='"NO,YES"', allow_blank=True)
            clear_prices_validation.error = "Pilih NO atau YES. YES akan menghapus harga lama yang tidak diisi ulang pada baris tersebut."
            clear_prices_validation.errorTitle = "Pilihan reset harga tidak valid"
            clear_prices_validation.showErrorMessage = True
            clear_prices_validation.add(f"L2:L{last_row}" if is_project else f"R2:R{last_row}")
            ws.add_data_validation(clear_prices_validation)
            price_validation = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
            price_validation.error = "Harga harus berupa angka nol atau lebih."
            price_validation.errorTitle = "Harga tidak valid"
            price_validation.showErrorMessage = True
            price_start_col = "I" if is_project else "O"
            price_end_col = "J" if is_project else "P"
            price_validation.add(f"{price_start_col}2:{price_end_col}{last_row}")
            ws.add_data_validation(price_validation)
            for row_idx in range(2, last_row + 1):
                for col_letter in (("I", "J") if is_project else ("O", "P")):
                    ws[f"{col_letter}{row_idx}"].number_format = '#,##0.00'
        service_ws = wb.create_sheet("Service Responses")
        service_headers = ["Requirement ID", "Requirement No", "Site / Requirement", "Service Name",
            "Feasibility Status", "MRC", "OTC", "Currency", "Clear Existing Prices?", "Notes"]
        service_ws.append(service_headers)
        for req in requirements:
            service_names = _leasing_normalize_service_names(req.get("requested_services"), req.get("service_type"))
            for service_name in service_names:
                old = current_service_by_key.get((int(req["requirement_id"]), service_name.casefold()), {})
                service_ws.append([req.get("requirement_id"), req.get("requirement_no"),
                    req.get("site_name") or req.get("address") or req.get("area") or req.get("si") or "",
                    service_name, old.get("feasibility_status"), old.get("mrc_amount"), old.get("otc_amount"),
                    old.get("currency"), None, old.get("notes")])
        _leasing_style_report_sheet(service_ws)
        service_ws.freeze_panes = "A2"
        service_ws.auto_filter.ref = service_ws.dimensions
        for col, width in {"A":16,"B":14,"C":36,"D":28,"E":24,"F":17,"G":17,"H":13,"I":22,"J":42}.items():
            service_ws.column_dimensions[col].width = width
        if service_ws.max_row >= 2:
            service_status_validation = DataValidation(type="list", formula1='"pending,can_provide,cannot_provide,needs_clarification"', allow_blank=True)
            service_status_validation.add(f"E2:E{service_ws.max_row}")
            service_ws.add_data_validation(service_status_validation)
            service_clear_validation = DataValidation(type="list", formula1='"NO,YES"', allow_blank=True)
            service_clear_validation.add(f"I2:I{service_ws.max_row}")
            service_ws.add_data_validation(service_clear_validation)
            service_price_validation = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
            service_price_validation.add(f"F2:G{service_ws.max_row}")
            service_ws.add_data_validation(service_price_validation)
            for row_idx in range(2, service_ws.max_row + 1):
                service_ws[f"F{row_idx}"].number_format = '#,##0.00'
                service_ws[f"G{row_idx}"].number_format = '#,##0.00'

        guide = wb.create_sheet("Instructions")
        guide.append(["Partner offer template", "Instructions"])
        guide.append(["Work Item", outreach["request_id"]])
        guide.append(["Customer", outreach["customer_name"]])
        guide.append(["Partner", outreach["partner_name"]])
        guide.append(["Outreach round", outreach["outreach_round"]])
        guide.append(["How to use", "Edit only Feasibility Status and commercial response columns; keep Requirement ID and site detail unchanged. Leave sites without a new response blank. Import creates a new version and carries forward unchanged sites. Blank price cells mean NO CHANGE to that price, so you can update one price without erasing other existing prices. Use Clear Existing Prices? = YES to clear the old prices for that site; any prices entered on that same row become the new complete price set. Choosing cannot_provide clears all previous prices automatically. Currency is prefilled from the active offer when available; do not change currency for only a partial price update. To change currency, choose YES and enter all prices that should remain."])
        guide.append(["Feasibility Status", "Use: pending, can_provide, cannot_provide, needs_clarification"])
        guide.append(["Currency", "Use a three-letter currency code such as IDR, USD, or SGD when adding or changing a price. Existing offer currency is prefilled where available."])
        guide.append(["Clear Existing Prices?", "Optional: NO/blank preserves prices in blank cells; YES clears prior prices in that row before applying any newly entered prices."])
        guide.append(["Service Responses", "Gunakan sheet ini untuk status cover dan harga per jasa dengan nama bebas. Satu baris = satu jasa pada satu site. Status Can provide/Cannot provide tidak memerlukan harga agar coverage tercatat; harga MRC/OTC tetap opsional dan ditampilkan terpisah. Nama jasa harus sesuai dengan jasa yang diminta di Work Item. Jasa tambahan yang ditawarkan partner dapat ditambahkan sebagai baris baru, tetapi tetap akan terlihat sebagai jasa tambahan."])
        guide.column_dimensions["A"].width = 22
        guide.column_dimensions["B"].width = 105
        for cell in guide[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24345B")
        guide.freeze_panes = "A2"
        guide.row_dimensions[6].height = 108
        guide["B6"].alignment = Alignment(wrap_text=True, vertical="top")
        output = BytesIO(); wb.save(output); output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True,
                         download_name=f"offer_template_outreach_{outreach_id}.xlsx")
    except psycopg2.Error:
        app.logger.exception("Leasing offer template generation failed")
        return jsonify({"success": False, "message": "Gagal membuat template penawaran."}), 500


@app.route("/api/leasing/outreaches/<int:outreach_id>/offers/import", methods=["POST"])
@leasing_login_required
def leasing_import_offer_xlsx(outreach_id):
    """Validate a filled offer workbook completely before creating one new offer version."""
    file_obj = request.files.get("file")
    if not file_obj or not (file_obj.filename or "").lower().endswith(".xlsx"):
        return jsonify({"success": False, "message": "Pilih file Excel .xlsx dari template penawaran."}), 400
    try:
        content = file_obj.read()
        if not content:
            raise ValueError("File penawaran kosong.")
        wb = load_workbook(BytesIO(content), read_only=True, data_only=True)
        if "Offer Input" not in wb.sheetnames:
            raise ValueError("Sheet 'Offer Input' tidak ditemukan. Gunakan template penawaran dari Work Item ini.")
        ws = wb["Offer Input"]
        raw_headers = [cell.value for cell in next(ws.iter_rows(min_row=1, max_row=1))]
        headers = {_leasing_header_key(value): idx for idx, value in enumerate(raw_headers) if value is not None}
        required_headers = {"requirement_id", "feasibility_status", "mrc", "otc", "currency", "notes"}
        missing = required_headers - set(headers)
        if missing:
            raise ValueError("Kolom wajib tidak ditemukan: " + ", ".join(sorted(missing)))
        def cell(row, name):
            index = headers.get(name)
            return row[index] if index is not None and index < len(row) else None
        parsed_lines, row_issues, seen = [], [], set()
        allowed_feasibility = {"pending", "can_provide", "cannot_provide", "needs_clarification"}
        yes_values = {"yes", "y", "true", "1", "clear"}
        no_values = {"no", "n", "false", "0"}
        for excel_row_no, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            if excel_row_no > 10002:
                raise ValueError("Maksimal 10.000 baris pada template penawaran.")
            if not any(v not in (None, "") for v in row):
                continue
            raw_id = cell(row, "requirement_id")
            if raw_id in (None, ""):
                row_issues.append(f"Baris {excel_row_no}: Requirement ID wajib diisi untuk baris yang digunakan.")
                continue
            try:
                req_id = int(raw_id)
                if float(raw_id) != req_id:
                    raise ValueError
            except (TypeError, ValueError):
                row_issues.append(f"Baris {excel_row_no}: Requirement ID harus bilangan bulat.")
                continue
            if req_id in seen:
                row_issues.append(f"Baris {excel_row_no}: Requirement ID {req_id} duplikat.")
                continue
            seen.add(req_id)
            raw_feasibility = str(cell(row, "feasibility_status") or "").strip().lower()
            if raw_feasibility and raw_feasibility not in allowed_feasibility:
                row_issues.append(f"Baris {excel_row_no}: Feasibility Status tidak valid: {raw_feasibility}.")
                continue
            try:
                mrc = _leasing_parse_number(cell(row, "mrc"), "MRC", excel_row_no)
                otc = _leasing_parse_number(cell(row, "otc"), "OTC", excel_row_no)
                inet_mrc = _leasing_parse_number(cell(row, "mrc_inet_dedicated_25_mbps"), "MRC Inet Dedicated 25 Mbps", excel_row_no)
                metro_mrc = _leasing_parse_number(cell(row, "mrc_metro_25_mbps"), "MRC Metro 25 Mbps", excel_row_no)
            except ValueError as exc:
                row_issues.append(str(exc))
                continue
            notes = str(cell(row, "notes") or "").strip() or None
            raw_clear_prices = str(cell(row, "clear_existing_prices") or "").strip().lower()
            if raw_clear_prices and raw_clear_prices not in yes_values | no_values:
                row_issues.append(f"Baris {excel_row_no}: Clear Existing Prices? harus YES atau NO.")
                continue
            clear_existing_prices = raw_clear_prices in yes_values
            # Blank price fields mean no change to those fields on an existing quote.
            # An explicit YES is the only spreadsheet command that clears previous values.
            any_price = any(x is not None for x in (mrc, inet_mrc, metro_mrc, otc))
            has_response_value = bool(raw_feasibility) or any_price or bool(notes) or clear_existing_prices
            if not has_response_value:
                continue
            if raw_feasibility == "pending" and not any_price and not notes and not clear_existing_prices:
                continue
            if not raw_feasibility and any_price:
                raw_feasibility = "can_provide"
            elif not raw_feasibility:
                # Blank status on an existing line means no status change, not reset.
                # The version merge preserves its prior status; new note-only rows become clarification.
                raw_feasibility = None
            if raw_feasibility == "pending" and any_price:
                row_issues.append(f"Baris {excel_row_no}: pilih can_provide sebelum memasukkan MRC/OTC.")
                continue
            if raw_feasibility == "cannot_provide" and any_price:
                row_issues.append(f"Baris {excel_row_no}: harga tidak boleh diisi jika status cannot_provide.")
                continue
            currency = str(cell(row, "currency") or "").strip().upper()
            if any_price:
                if not re.fullmatch(r"[A-Z]{3}", currency):
                    row_issues.append(f"Baris {excel_row_no}: Currency wajib kode 3 huruf jika MRC/OTC diisi.")
                    continue
            else:
                currency = None
            parsed_lines.append({"requirement_id": req_id, "feasibility_status": raw_feasibility,
                                 "mrc_amount": mrc, "mrc_inet_dedicated_25_amount": inet_mrc,
                                 "mrc_metro_25_amount": metro_mrc, "otc_amount": otc, "currency": currency,
                                 "notes": notes, "clear_existing_prices": clear_existing_prices})

        parsed_service_lines, service_seen = [], set()
        if "Service Responses" in wb.sheetnames:
            sws=wb["Service Responses"]
            sraw=[cell.value for cell in next(sws.iter_rows(min_row=1,max_row=1))]
            sheaders={_leasing_header_key(value):idx for idx,value in enumerate(sraw) if value is not None}
            required_service_headers={"requirement_id","service_name","feasibility_status","mrc","otc","currency","clear_existing_prices","notes"}
            missing_service=required_service_headers-set(sheaders)
            if missing_service:
                row_issues.append("Sheet Service Responses kehilangan kolom: "+", ".join(sorted(missing_service)))
            def scell(values,name):
                idx=sheaders.get(name)
                return values[idx] if idx is not None and idx<len(values) else None
            if not missing_service:
                for row_no,values in enumerate(sws.iter_rows(min_row=2,values_only=True),start=2):
                    if row_no>10002:
                        row_issues.append("Maksimal 10.000 baris pada Service Responses."); break
                    if not any(v not in (None,"") for v in values): continue
                    raw_id=scell(values,"requirement_id")
                    service_name=str(scell(values,"service_name") or "").strip()
                    if raw_id in (None,"") and not service_name: continue
                    if raw_id in (None,"") or not service_name:
                        row_issues.append(f"Service Responses baris {row_no}: Requirement ID dan Service Name wajib diisi bersama."); continue
                    try:
                        req_id=int(raw_id)
                        if float(raw_id)!=req_id or req_id<=0: raise ValueError
                    except (TypeError,ValueError):
                        row_issues.append(f"Service Responses baris {row_no}: Requirement ID harus bilangan bulat positif."); continue
                    key=(req_id,re.sub(r"\s+"," ",service_name).casefold())
                    if key in service_seen:
                        row_issues.append(f"Service Responses baris {row_no}: jasa '{service_name}' ganda untuk Requirement ID {req_id}."); continue
                    service_seen.add(key)
                    status=str(scell(values,"feasibility_status") or "").strip().lower() or None
                    if status and status not in allowed_feasibility:
                        row_issues.append(f"Service Responses baris {row_no}: Feasibility Status tidak valid: {status}."); continue
                    try:
                        smrc=_leasing_parse_number(scell(values,"mrc"),"MRC",row_no)
                        sotc=_leasing_parse_number(scell(values,"otc"),"OTC",row_no)
                    except ValueError as exc:
                        row_issues.append(str(exc)); continue
                    clear_raw=str(scell(values,"clear_existing_prices") or "").strip().lower()
                    if clear_raw and clear_raw not in yes_values | no_values:
                        row_issues.append(f"Service Responses baris {row_no}: Clear Existing Prices? harus YES atau NO."); continue
                    clear=clear_raw in yes_values
                    has_price=smrc is not None or sotc is not None
                    currency=str(scell(values,"currency") or "").strip().upper() or None
                    if has_price and (not currency or not re.fullmatch(r"[A-Z]{3}",currency)):
                        row_issues.append(f"Service Responses baris {row_no}: Currency wajib kode 3 huruf saat harga diisi."); continue
                    if status=="pending" and has_price:
                        row_issues.append(f"Service Responses baris {row_no}: pilih can_provide sebelum memasukkan harga."); continue
                    if status=="cannot_provide" and has_price:
                        row_issues.append(f"Service Responses baris {row_no}: harga tidak boleh diisi jika cannot_provide."); continue
                    notes=str(scell(values,"notes") or "").strip() or None
                    if not (status or has_price or notes or clear): continue
                    if not status and has_price:status="can_provide"
                    parsed_service_lines.append({"requirement_id":req_id,"service_name":service_name,
                        "feasibility_status":status,"mrc_amount":smrc,"otc_amount":sotc,"currency":currency,
                        "clear_existing_prices":clear,"notes":notes})
        wb.close()
        if row_issues:
            return jsonify({"success": False, "message": "Template penawaran belum valid; data belum disimpan.", "issues": row_issues[:100]}), 400
        if not parsed_lines and not parsed_service_lines:
            raise ValueError("Tidak ada perubahan site atau jasa yang bisa diimpor.")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                result = _leasing_record_offer_version(
                    cur, outreach_id, parsed_lines, session["username"], "xlsx_import",
                    received_at=datetime.now(), source_label=secure_filename(file_obj.filename or "offer.xlsx"),
                    incoming_service_lines=parsed_service_lines)
            conn.commit()
        return jsonify({"success": True, **result,
                        "message": f"Respons site: {result['line_count']}; respons jasa: {result.get('service_line_count',0)}. Versi {result['version_no']} tersimpan; snapshot aktif memuat {result['current_line_count']} site dan {result.get('current_service_line_count',0)} baris coverage jasa."}), 201
    except LookupError as exc:
        return jsonify({"success": False, "message": str(exc)}), 404
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        app.logger.exception("Leasing bulk offer import failed")
        return jsonify({"success": False, "message": "Import penawaran gagal. File belum disimpan; periksa format template dan log server."}), 400


@app.route("/api/leasing/work-items/<int:work_item_id>/report.xlsx", methods=["GET"])
@leasing_login_required
def leasing_work_item_report_xlsx(work_item_id):
    """Auditable multi-sheet report for one Work Item; owner/admin-only because it contains all partner pricing."""
    if not _leasing_user_is_work_item_owner_or_admin(work_item_id):
        return _leasing_owner_mutation_denied()
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT w.id, w.request_id, w.work_type, w.project_name, w.requester_name, w.requester_division, w.request_due_date,
                    w.current_stage, w.case_status, w.buyer_owner_id, w.created_at, w.updated_at, w.notes,
                    c.customer_name,
                    (SELECT COUNT(*) FROM leasing.requirements r WHERE r.work_item_id=w.id) AS requirement_count,
                    (SELECT COUNT(*) FROM leasing.requirements r WHERE r.work_item_id=w.id AND r.status IN ('resolved','stopped')) AS resolved_count,
                    (SELECT COUNT(*) FROM leasing.partner_outreaches o WHERE o.work_item_id=w.id) AS outreach_count,
                    (SELECT COUNT(DISTINCT o.partner_id) FROM leasing.partner_outreaches o WHERE o.work_item_id=w.id) AS partner_count,
                    (SELECT COUNT(*) FROM leasing.partner_offer_lines pol JOIN leasing.partner_offers po ON po.id=pol.offer_id JOIN leasing.partner_outreaches o ON o.id=po.outreach_id WHERE o.work_item_id=w.id) AS offer_line_count,
                    (SELECT COUNT(*) FROM leasing.activity_events a WHERE a.work_item_id=w.id) AS activity_count
                    FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id WHERE w.id=%s""", (work_item_id,))
                item = cur.fetchone()
                if not item: return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                queries = {
                    "Requirements": ("""SELECT id AS requirement_id, requirement_no, status, zone, site_name, postal_code,
                        requested_services, external_reference, project_notes AS site_notes,
                        order_type, si, area, address, gedung_kawasan, latitude, longitude,
                        a_end, z_end, bandwidth, bandwidth_unit, service_type AS service_summary_legacy,
                        special_features, existing_mrc_amount, existing_mrc_currency, resolution_note, created_at
                        FROM leasing.requirements WHERE work_item_id=%s ORDER BY requirement_no""", (work_item_id,)),
                    "Service Coverage": ("""WITH outreach_sites AS (
                        SELECT o.id AS outreach_id,w.id AS work_item_id,w.request_id,w.work_type,w.project_name,c.customer_name,
                            p.partner_name,o.outreach_round,o.sent_at,o.response_status AS outreach_status,o.next_follow_up_at,
                            o.follow_up_owner_id,o.created_by,r.id AS requirement_id,r.requirement_no,r.site_name,r.zone,r.address,
                            r.requested_services,r.service_type,oro.response_status AS site_response_status,oro.response_note,
                            CARDINALITY(CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                                ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END) AS service_count,
                            CASE WHEN COALESCE(array_length(r.requested_services,1),0)>0 THEN r.requested_services
                                ELSE ARRAY[COALESCE(NULLIF(BTRIM(r.service_type),''),'Service belum ditentukan')]::TEXT[] END AS service_names
                        FROM leasing.outreach_requirements oro JOIN leasing.partner_outreaches o ON o.id=oro.outreach_id
                        JOIN leasing.work_items w ON w.id=o.work_item_id JOIN leasing.partners p ON p.id=o.partner_id
                        JOIN leasing.requirements r ON r.id=oro.requirement_id LEFT JOIN leasing.customers c ON c.id=w.customer_id
                        WHERE o.work_item_id=%s
                    ), requested AS (
                        SELECT os.request_id,os.work_type,os.project_name,os.customer_name,os.partner_name,os.outreach_round,
                            os.sent_at,os.outreach_status,os.next_follow_up_at,os.follow_up_owner_id,os.created_by,
                            os.requirement_id,os.requirement_no,os.site_name,os.zone,os.address,os.requested_services,
                            svc.service_name,TRUE AS is_requested_service,
                            CASE WHEN osl.feasibility_status IS NOT NULL AND osl.feasibility_status <> 'pending' THEN osl.feasibility_status
                                WHEN pol.feasibility_status='cannot_provide' OR os.site_response_status='cannot_provide' THEN 'cannot_provide'
                                WHEN pol.feasibility_status='can_provide' AND os.service_count<=1 THEN 'can_provide'
                                WHEN os.site_response_status='can_provide' AND os.service_count<=1 THEN 'can_provide'
                                WHEN pol.feasibility_status='can_provide' OR os.site_response_status='can_provide' THEN 'needs_clarification'
                                WHEN os.sent_at IS NULL THEN 'draft'
                                WHEN pol.feasibility_status='needs_clarification' OR os.site_response_status='needs_clarification' THEN 'needs_clarification'
                                WHEN os.sent_at IS NULL THEN 'draft' WHEN osl.feasibility_status='pending' THEN 'pending'
                                ELSE COALESCE(os.site_response_status,'awaiting_response') END AS coverage_status,
                            osl.mrc_amount,osl.otc_amount,osl.currency,COALESCE(osl.notes,os.response_note) AS notes,COALESCE(osl.version_no,pol.version_no) AS offer_version
                        FROM outreach_sites os CROSS JOIN LATERAL unnest(os.service_names) AS svc(service_name)
                        LEFT JOIN LATERAL (SELECT po.version_no,sl.feasibility_status,sl.mrc_amount,sl.otc_amount,sl.currency,sl.notes
                            FROM leasing.partner_offers po JOIN leasing.partner_offer_service_lines sl ON sl.offer_id=po.id
                            WHERE po.outreach_id=os.outreach_id AND po.offer_status='current' AND sl.requirement_id=os.requirement_id
                              AND LOWER(BTRIM(sl.service_name))=LOWER(BTRIM(svc.service_name))
                            ORDER BY po.version_no DESC LIMIT 1) osl ON TRUE
                        LEFT JOIN LATERAL (SELECT po.version_no,pl.feasibility_status FROM leasing.partner_offers po
                            JOIN leasing.partner_offer_lines pl ON pl.offer_id=po.id
                            WHERE po.outreach_id=os.outreach_id AND po.offer_status='current' AND pl.requirement_id=os.requirement_id
                            ORDER BY po.version_no DESC LIMIT 1) pol ON TRUE
                    ), extras AS (
                        SELECT os.request_id,os.work_type,os.project_name,os.customer_name,os.partner_name,os.outreach_round,
                            os.sent_at,os.outreach_status,os.next_follow_up_at,os.follow_up_owner_id,os.created_by,
                            os.requirement_id,os.requirement_no,os.site_name,os.zone,os.address,os.requested_services,
                            sl.service_name,FALSE AS is_requested_service,sl.feasibility_status AS coverage_status,
                            sl.mrc_amount,sl.otc_amount,sl.currency,sl.notes,po.version_no AS offer_version
                        FROM outreach_sites os JOIN leasing.partner_offers po ON po.outreach_id=os.outreach_id AND po.offer_status='current'
                        JOIN leasing.partner_offer_service_lines sl ON sl.offer_id=po.id AND sl.requirement_id=os.requirement_id
                        WHERE NOT EXISTS (SELECT 1 FROM unnest(os.service_names) AS s(n)
                            WHERE LOWER(BTRIM(s.n))=LOWER(BTRIM(sl.service_name)))
                    )
                    SELECT * FROM requested UNION ALL SELECT * FROM extras
                    ORDER BY request_id,partner_name,outreach_round,requirement_no,service_name""", (work_item_id,)),
                    "Partner Activity": ("""SELECT o.id AS outreach_id, p.partner_name, o.outreach_round, o.sent_at,
                        o.response_status, o.responded_at, o.next_follow_up_at, o.follow_up_owner_id, o.created_by, o.notes,
                        (SELECT COUNT(*) FROM leasing.outreach_requirements oro WHERE oro.outreach_id=o.id) AS locations_sent,
                        (SELECT COUNT(DISTINCT oro.requirement_id) FROM leasing.outreach_requirements oro
                         WHERE oro.outreach_id=o.id AND oro.response_status IN ('can_provide','cannot_provide','needs_clarification')) AS locations_responded,
                        (SELECT COUNT(DISTINCT quoted.requirement_id) FROM (
                            SELECT osl.requirement_id FROM leasing.partner_offer_service_lines osl
                            JOIN leasing.partner_offers po ON po.id=osl.offer_id
                            WHERE po.outreach_id=o.id AND po.offer_status='current'
                              AND (osl.mrc_amount IS NOT NULL OR osl.otc_amount IS NOT NULL)
                            UNION
                            SELECT pol.requirement_id FROM leasing.partner_offer_lines pol
                            JOIN leasing.partner_offers po ON po.id=pol.offer_id
                            WHERE po.outreach_id=o.id AND po.offer_status='current'
                              AND (pol.mrc_amount IS NOT NULL OR pol.mrc_inet_dedicated_25_amount IS NOT NULL OR pol.mrc_metro_25_amount IS NOT NULL OR pol.otc_amount IS NOT NULL)
                        ) quoted) AS locations_quoted,
                        (SELECT MAX(po.version_no) FROM leasing.partner_offers po WHERE po.outreach_id=o.id) AS latest_offer_version,
                        (SELECT MAX(po.received_at) FROM leasing.partner_offers po WHERE po.outreach_id=o.id) AS latest_offer_received,
                        o.created_at
                        FROM leasing.partner_outreaches o JOIN leasing.partners p ON p.id=o.partner_id
                        WHERE o.work_item_id=%s ORDER BY o.created_at""", (work_item_id,)),
                    "Partner Coverage": ("""SELECT p.partner_name, o.outreach_round, o.sent_at, o.response_status AS outreach_status,
                        CASE current_line.feasibility_status WHEN 'can_provide' THEN 'can_provide'
                             WHEN 'cannot_provide' THEN 'cannot_provide' WHEN 'needs_clarification' THEN 'needs_clarification'
                             ELSE oro.response_status END AS requirement_response_status,
                        COALESCE(current_line.notes, oro.response_note) AS response_note,
                        r.id AS requirement_id, r.requirement_no, r.order_type, r.si, r.area,
                        r.address, r.gedung_kawasan, r.zone, r.site_name, r.postal_code, r.a_end, r.z_end, r.bandwidth, r.bandwidth_unit
                        FROM leasing.outreach_requirements oro JOIN leasing.partner_outreaches o ON o.id=oro.outreach_id
                        JOIN leasing.partners p ON p.id=o.partner_id JOIN leasing.requirements r ON r.id=oro.requirement_id
                        LEFT JOIN LATERAL (SELECT pol.feasibility_status, pol.notes
                            FROM leasing.partner_offers po JOIN leasing.partner_offer_lines pol ON pol.offer_id=po.id
                            WHERE po.outreach_id=o.id AND po.offer_status='current' AND pol.requirement_id=oro.requirement_id
                            ORDER BY po.version_no DESC LIMIT 1) current_line ON TRUE
                        WHERE o.work_item_id=%s ORDER BY p.partner_name, o.outreach_round, r.requirement_no""", (work_item_id,)),
                    "Commercial Comparison": ("""SELECT
                        osl.id AS service_line_id, osl.requirement_id, r.requirement_no, r.zone, r.site_name, r.address,
                        r.external_reference, osl.service_name, EXISTS (SELECT 1 FROM unnest(COALESCE(r.requested_services, ARRAY[]::TEXT[])) AS requested(req_name)
                            WHERE LOWER(BTRIM(requested.req_name))=LOWER(BTRIM(osl.service_name))) AS is_requested_service,
                        p.partner_name, o.outreach_round, o.sent_at, o.response_status AS outreach_status,
                        po.version_no, po.offer_status, po.received_at, po.valid_until,
                        osl.feasibility_status AS coverage_status, osl.mrc_amount AS offer_mrc, osl.otc_amount AS offer_otc,
                        osl.currency AS offer_currency, osl.notes AS service_notes, po.notes AS offer_notes,
                        mrc_target.target_amount AS target_mrc, mrc_target.currency AS target_mrc_currency,
                        otc_target.target_amount AS target_otc, otc_target.currency AS target_otc_currency,
                        neg.event_type AS latest_negotiation_event, neg.mrc_amount AS latest_negotiated_mrc,
                        neg.otc_amount AS latest_negotiated_otc, neg.currency AS latest_negotiated_currency,
                        neg.occurred_at AS latest_negotiation_at, neg.notes AS latest_negotiation_notes
                        FROM leasing.partner_offer_service_lines osl
                        JOIN leasing.partner_offers po ON po.id=osl.offer_id
                        JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                        JOIN leasing.partners p ON p.id=o.partner_id
                        JOIN leasing.requirements r ON r.id=osl.requirement_id
                        LEFT JOIN LATERAL (
                            SELECT ct.target_amount,ct.currency FROM leasing.commercial_targets ct
                            WHERE ct.work_item_id=o.work_item_id AND ct.metric='mrc'
                              AND (ct.requirement_id=osl.requirement_id OR ct.requirement_id IS NULL)
                              AND (ct.service_name IS NULL OR LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(osl.service_name)))
                            ORDER BY CASE
                                WHEN ct.requirement_id=osl.requirement_id AND ct.service_name IS NOT NULL AND LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(osl.service_name)) THEN 0
                                WHEN ct.requirement_id=osl.requirement_id AND ct.service_name IS NULL THEN 1
                                WHEN ct.requirement_id IS NULL AND ct.service_name IS NOT NULL AND LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(osl.service_name)) THEN 2
                                ELSE 3 END, ct.created_at DESC LIMIT 1
                        ) mrc_target ON TRUE
                        LEFT JOIN LATERAL (
                            SELECT ct.target_amount,ct.currency FROM leasing.commercial_targets ct
                            WHERE ct.work_item_id=o.work_item_id AND ct.metric='otc'
                              AND (ct.requirement_id=osl.requirement_id OR ct.requirement_id IS NULL)
                              AND (ct.service_name IS NULL OR LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(osl.service_name)))
                            ORDER BY CASE
                                WHEN ct.requirement_id=osl.requirement_id AND ct.service_name IS NOT NULL AND LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(osl.service_name)) THEN 0
                                WHEN ct.requirement_id=osl.requirement_id AND ct.service_name IS NULL THEN 1
                                WHEN ct.requirement_id IS NULL AND ct.service_name IS NOT NULL AND LOWER(BTRIM(ct.service_name))=LOWER(BTRIM(osl.service_name)) THEN 2
                                ELSE 3 END, ct.created_at DESC LIMIT 1
                        ) otc_target ON TRUE
                        LEFT JOIN LATERAL (
                            SELECT n.* FROM leasing.partner_service_negotiation_events n
                            WHERE n.service_line_id=osl.id ORDER BY n.occurred_at DESC,n.id DESC LIMIT 1
                        ) neg ON TRUE
                        WHERE o.work_item_id=%s
                        ORDER BY r.requirement_no,p.partner_name,osl.service_name,po.version_no DESC""", (work_item_id,)),
                    "Legacy Commercial": ("""SELECT pol.id AS offer_line_id, pol.requirement_id, p.partner_name, o.outreach_round,
                        po.version_no, po.offer_status, po.received_at, r.requirement_no, r.site_name, r.address,
                        pol.feasibility_status, pol.mrc_amount, pol.mrc_inet_dedicated_25_amount,
                        pol.mrc_metro_25_amount, pol.otc_amount, pol.currency, pol.notes AS line_notes,
                        po.notes AS offer_notes, r.project_mrc_inet_dedicated_25, r.project_mrc_metro_25, r.requested_otc
                        FROM leasing.partner_offer_lines pol JOIN leasing.partner_offers po ON po.id=pol.offer_id
                        JOIN leasing.partner_outreaches o ON o.id=po.outreach_id JOIN leasing.partners p ON p.id=o.partner_id
                        JOIN leasing.requirements r ON r.id=pol.requirement_id
                        WHERE o.work_item_id=%s ORDER BY r.requirement_no,p.partner_name,po.version_no DESC""", (work_item_id,)),
                    "Activity Log": ("""SELECT occurred_at, event_type, event_summary, actor_id, metadata
                        FROM leasing.activity_events WHERE work_item_id=%s ORDER BY occurred_at""", (work_item_id,)),
                    "Results Sent": ("""SELECT rs.submission_no, rs.submission_status, rs.channel, rs.recipient_name, rs.recipient_email,
                        rs.sent_at, rs.created_at, rs.created_by, rs.notes, rsl.requirement_id, r.requirement_no,
                        r.zone, r.site_name, r.postal_code, r.area, r.address, r.gedung_kawasan, p.partner_name,
                        pol.mrc_amount, pol.mrc_inet_dedicated_25_amount, pol.mrc_metro_25_amount, pol.otc_amount, pol.currency,
                        rsl.result_note
                        FROM leasing.result_submissions rs LEFT JOIN leasing.result_submission_lines rsl ON rsl.submission_id=rs.id
                        LEFT JOIN leasing.requirements r ON r.id=rsl.requirement_id
                        LEFT JOIN leasing.partner_offer_lines pol ON pol.id=rsl.offer_line_id
                        LEFT JOIN leasing.partner_offers po ON po.id=pol.offer_id
                        LEFT JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                        LEFT JOIN leasing.partners p ON p.id=o.partner_id
                        WHERE rs.work_item_id=%s ORDER BY rs.submission_no, r.requirement_no""", (work_item_id,)),
                    "Commercial Targets": ("""SELECT ct.metric, ct.service_name, ct.target_amount, ct.currency, ct.target_source, ct.notes,
                        ct.requirement_id, r.requirement_no, r.site_name, r.zone, r.area, r.address, ct.created_at, ct.created_by
                        FROM leasing.commercial_targets ct LEFT JOIN leasing.requirements r ON r.id=ct.requirement_id
                        WHERE ct.work_item_id=%s ORDER BY ct.requirement_id NULLS FIRST, ct.metric, ct.created_at""", (work_item_id,)),
                    "Documents": ("""SELECT d.id AS document_id, d.document_type, d.original_filename, d.mime_type,
                        d.size_bytes, d.requirement_id, r.requirement_no, d.outreach_id, d.offer_id,
                        d.uploaded_by, d.uploaded_at
                        FROM leasing.documents d LEFT JOIN leasing.requirements r ON r.id=d.requirement_id
                        WHERE d.work_item_id=%s ORDER BY d.uploaded_at""", (work_item_id,)),
                }
                result_sets = {}
                for title, (sql, params) in queries.items():
                    cur.execute(sql, params)
                    result_sets[title] = [dict(row) for row in cur.fetchall()]
        wb = Workbook()
        overview = wb.active; overview.title = "Overview"
        overview.append(["Field", "Value"])
        summary_fields = [
            ("Work Item ID", item.get("id")), ("Request ID", item.get("request_id")), ("Customer", item.get("customer_name")),
            ("Requester", item.get("requester_name")), ("Requester Division", item.get("requester_division")),
            ("Due Date", item.get("request_due_date")), ("Buyer / PIC", item.get("buyer_owner_id")),
            ("Stage", item.get("current_stage")), ("Case Status", item.get("case_status")),
            ("Created At", item.get("created_at")), ("Updated At", item.get("updated_at")),
            ("Requirement Count", item.get("requirement_count")), ("Resolved / Stopped", item.get("resolved_count")),
            ("Partner Outreach Count", item.get("outreach_count")), ("Distinct Partners Contacted", item.get("partner_count")),
            ("Commercial Offer Line Records (all versions)", item.get("offer_line_count")), ("Activity Events", item.get("activity_count")),
            ("Request Notes", item.get("notes")),
        ]
        for key, val in summary_fields: overview.append([key, _leasing_excel_safe(val)])
        overview.column_dimensions["A"].width = 30; overview.column_dimensions["B"].width = 75
        overview.freeze_panes = "A2"
        for cell in overview[1]:
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = PatternFill("solid", fgColor="24345B")
        for row in overview.iter_rows(min_row=2):
            row[1].alignment = Alignment(wrap_text=True, vertical="top")
        for title, records in result_sets.items():
            ws = wb.create_sheet(title)
            if records:
                columns = list(records[0].keys())
                ws.append(columns)
                for rec in records:
                    ws.append([_leasing_excel_safe(rec.get(col)) for col in columns])
            else:
                ws.append(["No records"])
                ws.append(["Tidak ada data untuk bagian ini."])
            _leasing_style_report_sheet(ws)
            if title in {"Activity Log", "Requirements", "Partner Coverage", "Commercial Comparison", "Results Sent"}:
                ws.sheet_view.showGridLines = False
        output = BytesIO(); wb.save(output); output.seek(0)
        request_id = secure_filename(str(item.get("request_id") or f"work_item_{work_item_id}")) or f"work_item_{work_item_id}"
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True,
                         download_name=f"leasing_activity_{request_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    except psycopg2.Error:
        app.logger.exception("Leasing Work Item report query failed")
        return jsonify({"success": False, "message": "Laporan Work Item gagal dibuat. Pastikan schema Leasing dan seluruh tabel terkait sudah termigrasi."}), 500
    except Exception:
        app.logger.exception("Leasing Work Item report generation failed")
        return jsonify({"success": False, "message": "Laporan Work Item gagal dibuat. Periksa log aplikasi."}), 500


# Leasing bulk intake: Excel upload or raw TSV/CSV paste.
# Each non-empty source row becomes a requirement. Rows with the same non-empty
# Request ID group into one Work Item; rows with blank Request ID each create a
# separate Work Item. Customer name is never used as a grouping key.
# ---------------------------------------------------------------------------
LEASING_IMPORT_ALIASES = {
    "work_type": {"work_type", "work type", "tipe pekerjaan", "jenis pekerjaan", "tipe work item", "jenis work item"},
    "request_id": {"request_id", "request id", "work_item_id", "work item id", "work_item", "work item", "ticket_id", "ticket id", "id request", "id_request"},
    "project_name": {"project name", "nama project", "nama proyek", "project", "proyek"},
    "customer_name": {"customer", "customer_name", "customer name", "pelanggan", "customer/pelanggan", "customer_pelanggan"},
    "requester_name": {"requester", "requester_name", "requester name", "nama requester", "pemohon"},
    "request_due_date": {"request_due_date", "request due date", "due date", "due_date", "due date submit", "due date requester", "target submit"},
    "notes": {"notes", "catatan", "catatan request", "feedback sales"},
    "order_type": {"order_type", "order type", "jenis order", "jenis_order"},
    "si": {"si", "nomor si", "no si", "si number", "service id"},
    "area": {"area", "wilayah", "regional area"},
    "address": {"address", "alamat", "alamat site", "site address"},
    "zone": {"zona", "zone"},
    "site_name": {"site", "site name", "nama site", "site_id", "site id"},
    "postal_code": {"kode pos", "postal code", "postal_code", "postcode", "zip code"},
    "project_mrc_inet_dedicated_25": {"mrc inet dedicated 25 mbps", "mrc internet dedicated 25 mbps", "mrc inet dedicated", "mrc dedicated 25"},
    "project_mrc_metro_25": {"mrc metro 25 mbps", "mrc metro", "mrc metro-e 25"},
    "requested_otc": {"otc", "requested otc", "otc request"},
    "project_notes": {"keterangan", "site notes", "project notes", "catatan site"},
    "latitude": {"latitude", "lat", "lintang"},
    "longitude": {"longitude", "long", "lng", "bujur"},
    "gedung_kawasan": {"gedung_kawasan", "gedung kawasan", "gedung/kawasan", "gedung", "kawasan", "building"},
    "a_end": {"a_end", "a end", "a-end", "aend"},
    "z_end": {"z_end", "z end", "z-end", "zend"},
    "bandwidth": {"bandwidth", "bw", "bandwidth value"},
    "bandwidth_unit": {"bandwidth_unit", "bandwidth unit", "satuan bandwidth", "satuan (default mbps)", "satuan", "unit"},
    "service_type": {"service_type", "service type", "jenis layanan", "jasa", "service", "product"},
    "requested_services": {"requested services", "services requested", "jasa yang diminta", "daftar jasa", "requested_services", "services"},
    "special_features": {"special_features", "special features", "fitur khusus", "special requirement", "fitur"},
    "existing_mrc_amount": {"existing_mrc_amount", "existing mrc", "mrc eksisting", "mrc existing", "mrc berjalan"},
    "existing_mrc_currency": {"existing_mrc_currency", "existing mrc currency", "currency mrc eksisting", "mata uang mrc eksisting"},
    "external_reference": {"external reference", "external_reference", "source request id", "original request id", "reference id", "referensi eksternal"},
    "existing_mrc_inet_dedicated_25_amount": {"mrc existing internet dedicated", "mrc existing inet dedicated", "existing mrc internet dedicated", "existing mrc inet dedicated", "mrc inet dedicated existing", "mrc inet existing"},
    "existing_mrc_metro_25_amount": {"mrc existing metro e", "mrc existing metro-e", "existing mrc metro e", "existing mrc metro-e", "mrc metro e existing", "mrc metro existing"},
}
LEASING_IMPORT_SUPPORTED_HEADERS = set().union(*LEASING_IMPORT_ALIASES.values())


def _leasing_alias_key(alias):
    return _leasing_header_key(alias)


LEASING_IMPORT_ALIAS_LOOKUP = {
    _leasing_alias_key(alias): canonical
    for canonical, aliases in LEASING_IMPORT_ALIASES.items()
    for alias in aliases
}


def _leasing_cell_value(value):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, (datetime,)):
        return value.isoformat()
    text_value = str(value).strip()
    return text_value if text_value else None


def _leasing_parse_date(value, field_name, row_no):
    value = _leasing_cell_value(value)
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        raise ValueError(f"Baris {row_no}: {field_name} tidak dikenali sebagai tanggal: {value}")
    return parsed.strftime("%Y-%m-%d")


def _leasing_parse_number(value, field_name, row_no):
    value = _leasing_cell_value(value)
    if value is None:
        return None
    raw = str(value).strip().replace("Rp", "").replace("IDR", "").replace(" ", "")
    if "," in raw and "." in raw:
        # If the final comma occurs after the final dot, treat comma as decimal separator.
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        pieces = raw.split(",")
        # Repeated 3-digit groups are thousands separators (e.g. 1,000,000).
        if len(pieces) > 2 and all(piece.isdigit() for piece in pieces) and all(len(piece) == 3 for piece in pieces[1:]):
            raw = "".join(pieces)
        elif len(pieces) == 2 and pieces[1].isdigit() and len(pieces[1]) == 3 and pieces[0].lstrip("+-").isdigit():
            raw = "".join(pieces)
        else:
            raw = raw.replace(",", ".")
    elif raw.count(".") > 1:
        pieces = raw.split(".")
        if all(piece.isdigit() for piece in pieces) and all(len(piece) == 3 for piece in pieces[1:]):
            raw = "".join(pieces)
    elif "." in raw:
        pieces = raw.split(".")
        if len(pieces) == 2 and pieces[1].isdigit() and len(pieces[1]) == 3 and pieces[0].lstrip("+-").isdigit():
            raw = "".join(pieces)
    try:
        number = float(raw)
    except (TypeError, ValueError):
        raise ValueError(f"Baris {row_no}: {field_name} harus berupa angka: {value}")
    if not math.isfinite(number):
        raise ValueError(f"Baris {row_no}: {field_name} harus berupa angka yang valid.")
    if number < 0:
        raise ValueError(f"Baris {row_no}: {field_name} tidak boleh negatif.")
    return number


def _leasing_read_import_source():
    raw_rows = []
    source_content_fingerprint = None
    if request.files.get("file"):
        file_obj = request.files["file"]
        filename = secure_filename(file_obj.filename or "")
        suffix = os.path.splitext(filename)[1].lower()
        content = file_obj.read()
        if not filename or not content:
            raise ValueError("File import kosong atau tidak memiliki nama.")
        source_content_fingerprint = hashlib.sha256(content).hexdigest()
        if suffix == ".xlsx":
            frame = pd.read_excel(io.BytesIO(content), dtype=object)
        elif suffix in {".csv", ".tsv", ".txt"}:
            delimiter = "\t" if suffix == ".tsv" else None
            frame = pd.read_csv(io.BytesIO(content), dtype=object, sep=delimiter or None, engine="python")
        else:
            raise ValueError("Format file belum didukung. Gunakan .xlsx, .csv, atau .tsv.")
        frame.columns = [str(c).strip() for c in frame.columns]
        raw_rows = frame.where(pd.notna(frame), None).to_dict(orient="records")
        source_name = filename
        source_headers = [str(c) for c in frame.columns]
    else:
        payload = request.get_json(silent=True) or {}
        raw_text = str(payload.get("text") or "").strip()
        source_content_fingerprint = hashlib.sha256(raw_text.encode("utf-8")).hexdigest() if raw_text else None
        if not raw_text:
            raise ValueError("Pilih file Excel/CSV atau paste data dengan header kolom terlebih dahulu.")
        first_line = raw_text.splitlines()[0]
        delimiter = "\t" if first_line.count("\t") >= max(first_line.count(","), first_line.count(";")) and "\t" in first_line else (";" if first_line.count(";") > first_line.count(",") else ",")
        reader = csv.DictReader(io.StringIO(raw_text), delimiter=delimiter)
        source_headers = [str(h or "").strip() for h in (reader.fieldnames or [])]
        if not source_headers:
            raise ValueError("Header kolom tidak ditemukan. Pastikan baris pertama adalah header dari Excel.")
        raw_rows = [{str(k or "").strip(): v for k, v in row.items() if k is not None} for row in reader]
        source_name = "Clipboard paste"
    if len(raw_rows) > 3000:
        raise ValueError("Maksimal 3.000 baris per import. Pecah file menjadi beberapa batch.")
    raw_rows = [row for row in raw_rows if any(_leasing_cell_value(v) is not None for v in row.values())]
    return raw_rows, source_headers, source_name, source_content_fingerprint


def _leasing_is_psb(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return normalized in {"psb", "pasang baru", "pasang baru psb"}


def _leasing_normalize_service_names(value, fallback=None):
    """Normalize arbitrary service names; explicit [] means clear, None/blank may use legacy fallback."""
    # An explicit empty array is a deliberate value from the API/UI, not a missing field.
    # This distinction prevents a user from clearing the field only to have stale legacy
    # service_type silently reappear. Blank cells/None still support old Excel/DB rows.
    explicit_empty_array = isinstance(value, (list, tuple, set)) and len(value) == 0
    explicit_empty_string = isinstance(value, str) and not value.strip()
    use_fallback = value is None
    raw = fallback if use_fallback else ([] if explicit_empty_array or explicit_empty_string else value)
    if raw is None or raw == "" or (isinstance(raw, (list, tuple, set)) and len(raw) == 0):
        return []
    if isinstance(raw, (list, tuple, set)):
        tokens = []
        for item in raw:
            # Arrays are accepted by the UI/API too; allow one item to contain multiple names.
            tokens.extend(re.split(r"[;|\r\n]+", str(item or "")))
        tokens = [str(item or "").strip() for item in tokens]
    else:
        # Semicolon, pipe, or line breaks separate services. Commas are kept inside a name.
        tokens = re.split(r"[;|\r\n]+", str(raw))
        tokens = [str(item or "").strip() for item in tokens]
    result, seen = [], set()
    for token in tokens:
        token = re.sub(r"\s+", " ", token).strip()
        if not token:
            continue
        if len(token) > 160:
            raise ValueError("Nama jasa maksimal 160 karakter.")
        key = token.casefold()
        if key not in seen:
            result.append(token)
            seen.add(key)
    if len(result) > 50:
        raise ValueError("Maksimal 50 jenis jasa per requirement/site.")
    return result


def _leasing_validate_requirement_payload(payload, label="Requirement", work_type="non_project", require_project_services=True):
    data = {key: _leasing_cell_value(payload.get(key)) for key in (
        "order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end",
        "bandwidth", "bandwidth_unit", "service_type", "special_features", "existing_mrc_amount", "existing_mrc_currency",
        "zone", "site_name", "postal_code", "project_name", "project_mrc_inet_dedicated_25", "project_mrc_metro_25", "requested_otc", "project_notes",
        "external_reference", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount"
    )}
    work_type = str(work_type or payload.get("work_type") or "non_project").strip().lower().replace(" ", "_")
    if work_type not in {"project", "non_project"}:
        raise ValueError(f"{label}: Work Type harus Project atau Non-Project.")
    service_fallback = data.get("service_type")
    # JSON clients may send an array. Preserve its type until the generic service normalizer runs.
    # Explicit []/blank is a requested clear; missing/None can fall back to legacy service_type.
    requested_services_explicit = "requested_services" in payload and payload.get("requested_services") is not None
    data["requested_services"] = _leasing_normalize_service_names(payload.get("requested_services"), service_fallback)
    if work_type == "non_project":
        if requested_services_explicit:
            data["service_type"] = "; ".join(data["requested_services"]) or None
        elif not data.get("service_type") and data["requested_services"]:
            data["service_type"] = "; ".join(data["requested_services"])
    if work_type == "project":
        if not data["requested_services"] and not requested_services_explicit:
            # One-time compatibility for older Project templates with legacy price fields.
            inferred = []
            if data.get("project_mrc_inet_dedicated_25") not in (None, ""):
                inferred.append("Internet Dedicated")
            if data.get("project_mrc_metro_25") not in (None, ""):
                inferred.append("Metro E")
            data["requested_services"] = _leasing_normalize_service_names(inferred)
        if require_project_services and not data["requested_services"]:
            raise ValueError(f"{label}: isi minimal satu nama jasa pada Requested Services. Nama jasa bebas; pisahkan beberapa jasa dengan titik koma.")
        if data["requested_services"]:
            data["service_type"] = "; ".join(data["requested_services"])
        elif requested_services_explicit:
            data["service_type"] = None
        data["site_name"] = data.get("site_name")
        data["area"] = data.get("zone") or data.get("area")
        if not data.get("project_name"): raise ValueError(f"{label}: Project Name wajib diisi untuk Project.")
        if not data.get("site_name"): raise ValueError(f"{label}: Site wajib diisi untuk Project.")
        if not data.get("address"): raise ValueError(f"{label}: Alamat wajib diisi untuk Project.")
        for key, title in (("project_mrc_inet_dedicated_25", "MRC Inet Dedicated 25 Mbps"), ("project_mrc_metro_25", "MRC Metro 25 Mbps"), ("requested_otc", "OTC")):
            if data.get(key) not in (None, ""):
                try: amount = float(str(data[key]).replace(".", "").replace(",", ".") if "," in str(data[key]) else data[key])
                except (TypeError, ValueError): raise ValueError(f"{label}: {title} harus berupa angka nol atau lebih.")
                if not math.isfinite(amount) or amount < 0: raise ValueError(f"{label}: {title} harus berupa angka nol atau lebih.")
                data[key] = amount
            else: data[key] = None
        data["latitude"] = _leasing_validate_coordinate(data.get("latitude"), "Latitude", label, -90, 90)
        data["longitude"] = _leasing_validate_coordinate(data.get("longitude"), "Longitude", label, -180, 180)
        data["bandwidth"] = None
        data["bandwidth_unit"] = "Mbps"
        if any(data.get(k) not in (None, "") for k in (
            "existing_mrc_amount", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount"
        )):
            raise ValueError(f"{label}: untuk Project, gunakan kolom target MRC Inet Dedicated / MRC Metro / OTC, bukan MRC Eksisting Non-Project.")
        data["existing_mrc_amount"] = None
        data["existing_mrc_currency"] = None
        data["work_type"] = work_type
        return data

    required = (("order_type", "Jenis Order"), ("area", "Area"), ("address", "Alamat"), ("a_end", "A End"), ("service_type", "Jasa"), ("special_features", "Fitur Khusus"))
    for key, title in required:
        if not data.get(key): raise ValueError(f"{label}: {title} wajib diisi.")
    if not _leasing_is_psb(data["order_type"]) and not data.get("si"):
        raise ValueError(f"{label}: SI wajib diisi untuk Jenis Order selain Pasang Baru (PSB).")
    order_aliases = {
        "psb": "PSB", "pasang baru": "PSB", "pasang baru psb": "PSB",
        "relokasi": "Relokasi", "upgrade": "Upgrade", "downgrade": "Downgrade",
        "change mitra": "Change Mitra", "change service": "Change Service"
    }
    normalized_order = re.sub(r"\s+", " ", str(data["order_type"]).strip().lower())
    if normalized_order not in order_aliases:
        raise ValueError(f"{label}: Jenis Order harus PSB, Relokasi, Upgrade, Downgrade, Change Mitra, atau Change Service.")
    data["order_type"] = order_aliases[normalized_order]
    for coord_key, coord_label, low, high in (("latitude", "Latitude", -90, 90), ("longitude", "Longitude", -180, 180)):
        raw = data.get(coord_key)
        if raw not in (None, ""):
            try: coord = float(str(raw).replace(",", "."))
            except (TypeError, ValueError): raise ValueError(f"{label}: {coord_label} harus berupa angka desimal.")
            if not math.isfinite(coord) or not low <= coord <= high:
                raise ValueError(f"{label}: {coord_label} di luar rentang yang valid ({low} sampai {high}).")
            data[coord_key] = coord
        else:
            data[coord_key] = None
    try:
        bandwidth = float(str(data.get("bandwidth") or "").replace(",", "."))
    except (TypeError, ValueError):
        raise ValueError(f"{label}: Bandwidth wajib berupa angka lebih besar dari nol.")
    if not math.isfinite(bandwidth) or bandwidth <= 0:
        raise ValueError(f"{label}: Bandwidth wajib berupa angka lebih besar dari nol.")
    data["bandwidth"] = bandwidth
    unit_map = {"mbps": "Mbps", "gbps": "Gbps", "kbps": "Kbps", "other": "Other"}
    unit = str(data.get("bandwidth_unit") or "Mbps").strip().lower()
    if unit not in unit_map: raise ValueError(f"{label}: Satuan harus Mbps, Gbps, Kbps, atau Other.")
    data["bandwidth_unit"] = unit_map[unit]
    for key, label in (
        ("existing_mrc_amount", "MRC Eksisting"),
        ("existing_mrc_inet_dedicated_25_amount", "MRC Existing Internet Dedicated"),
        ("existing_mrc_metro_25_amount", "MRC Existing Metro E"),
    ):
        raw_value = data.get(key)
        if raw_value not in (None, ""):
            try: amount = float(str(raw_value).replace(",", "."))
            except (TypeError, ValueError): raise ValueError(f"{label} harus berupa angka nol atau lebih.")
            if not math.isfinite(amount) or amount < 0: raise ValueError(f"{label} harus berupa angka nol atau lebih.")
            data[key] = amount
        else:
            data[key] = None
    if any(data.get(k) is not None for k in ("existing_mrc_amount", "existing_mrc_inet_dedicated_25_amount", "existing_mrc_metro_25_amount")):
        currency = str(data.get("existing_mrc_currency") or "IDR").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise ValueError("Currency MRC harus berupa kode 3 huruf.")
        data["existing_mrc_currency"] = currency
    else:
        data["existing_mrc_currency"] = None
    data["external_reference"] = str(data.get("external_reference") or "").strip() or None
    data["work_type"] = work_type
    return data


def _leasing_validate_coordinate(raw, title, label, low, high):
    if raw in (None, ""): return None
    try: coord = float(str(raw).replace(",", "."))
    except (TypeError, ValueError): raise ValueError(f"{label}: {title} harus berupa angka desimal.")
    if not math.isfinite(coord) or not low <= coord <= high:
        raise ValueError(f"{label}: {title} di luar rentang yang valid ({low} sampai {high}).")
    return coord


def _leasing_normalize_import_rows(raw_rows, source_headers):
    mapped_headers, unmapped_headers = {}, []
    for header in source_headers:
        canonical = LEASING_IMPORT_ALIAS_LOOKUP.get(_leasing_header_key(header))
        if canonical: mapped_headers.setdefault(canonical, header)
        elif any(_leasing_cell_value(row.get(header)) is not None for row in raw_rows): unmapped_headers.append(header)
    normalized, issues = [], []
    for row_idx, source in enumerate(raw_rows, start=2):
        obj = {canonical: _leasing_cell_value(source.get(header)) for canonical, header in mapped_headers.items()}
        obj["_row_no"] = row_idx
        try:
            raw_type = str(obj.get("work_type") or "non_project").strip().lower().replace("_", " ").replace("-", " ")
            if raw_type in {"project", "proyek"}: obj["work_type"] = "project"
            elif raw_type in {"non project", "nonproject", "non proyek", "nonproyek", ""}: obj["work_type"] = "non_project"
            else: raise ValueError(f"Baris {row_idx}: Work Type harus Project atau Non-Project.")
            obj["request_due_date"] = _leasing_parse_date(obj.get("request_due_date"), "Due date", row_idx)
            obj["bandwidth"] = _leasing_parse_number(obj.get("bandwidth"), "Bandwidth", row_idx)
            obj["existing_mrc_amount"] = _leasing_parse_number(obj.get("existing_mrc_amount"), "MRC eksisting", row_idx)
            obj["existing_mrc_inet_dedicated_25_amount"] = _leasing_parse_number(obj.get("existing_mrc_inet_dedicated_25_amount"), "MRC Existing Internet Dedicated", row_idx)
            obj["existing_mrc_metro_25_amount"] = _leasing_parse_number(obj.get("existing_mrc_metro_25_amount"), "MRC Existing Metro E", row_idx)
            for key, label in (("project_mrc_inet_dedicated_25", "MRC Inet Dedicated 25 Mbps"), ("project_mrc_metro_25", "MRC Metro 25 Mbps"), ("requested_otc", "OTC")):
                obj[key] = _leasing_parse_number(obj.get(key), label, row_idx)
            if obj.get("request_id"): obj["request_id"] = str(obj["request_id"]).strip()
            obj.update(_leasing_validate_requirement_payload(obj, f"Baris {row_idx}", obj["work_type"]))
            normalized.append(obj)
        except ValueError as exc:
            issues.append(str(exc))
    return normalized, mapped_headers, unmapped_headers, issues


def _leasing_import_groups(rows, grouping_mode="request_id_grouping", combined_request_id=None):
    """Group intake rows either by Request ID or explicitly into one Work Item."""
    if not rows: return [], ["Tidak ada baris data requirement untuk diimport."]
    issues, groups, by_request_id = [], [], {}
    if grouping_mode == "single_work_item":
        combined_request_id = str(combined_request_id or "").strip()
        if not combined_request_id:
            return [], ["Request ID Work Item wajib diisi saat seluruh file digabung menjadi satu Work Item."]
        if len(combined_request_id) > 120:
            return [], ["Request ID Work Item maksimal 120 karakter."]
        group = {"request_id": combined_request_id, "rows": list(rows), "customer_name": None,
                 "requester_name": None, "work_type": rows[0].get("work_type", "non_project"),
                 "project_name": rows[0].get("project_name")}
        for row in rows:
            # Preserve a row-level source Request ID instead of silently losing it when the file is merged.
            row["external_reference"] = row.get("external_reference") or row.get("request_id")
        groups = [group]
    elif grouping_mode != "request_id_grouping":
        return [], ["Mode penggabungan import tidak dikenali."]
    if grouping_mode == "request_id_grouping":
        for row in rows:
            rid = re.sub(r"\s+", " ", str(row.get("request_id") or "")).strip()
            if rid:
                normalized_request_id = rid.casefold()
                if normalized_request_id not in by_request_id:
                    group = {"request_id": rid, "rows": [], "customer_name": None, "requester_name": None, "work_type": row.get("work_type", "non_project"), "project_name": row.get("project_name")}
                    by_request_id[normalized_request_id] = group
                    groups.append(group)
                group = by_request_id[normalized_request_id]
                row["request_id"] = rid
            else:
                group = {"request_id": None, "rows": [], "customer_name": None, "requester_name": None, "work_type": row.get("work_type", "non_project"), "project_name": row.get("project_name")}
                groups.append(group)
            group["rows"].append(row)
    request_fields = (("customer_name", "Customer"), ("requester_name", "Requester"), ("request_due_date", "Due Date"), ("notes", "Notes"), ("work_type", "Work Type"), ("project_name", "Project Name"))
    for group in groups:
        rows_in_group = group["rows"]
        for field, label in request_fields:
            values = [(r["_row_no"], str(r[field]).strip()) for r in rows_in_group if r.get(field) is not None and str(r[field]).strip()]
            if len({v.casefold() for _, v in values}) > 1:
                issues.append(f"Request ID {group['request_id'] or '(kosong / baris terpisah)'}: {label} berbeda pada baris {', '.join(str(n) for n,_ in values)}.")
            elif values:
                value = values[0][1]
                for r in rows_in_group: r[field] = value
        group["customer_name"] = next((r.get("customer_name") for r in rows_in_group if r.get("customer_name")), None)
        group["requester_name"] = next((r.get("requester_name") for r in rows_in_group if r.get("requester_name")), None)
        group["work_type"] = next((r.get("work_type", "non_project") for r in rows_in_group), "non_project")
        group["project_name"] = next((r.get("project_name") for r in rows_in_group if r.get("project_name")), None)
        if not group["customer_name"]: issues.append(f"Customer wajib diisi untuk Work Item dari baris {rows_in_group[0]['_row_no']}.")
        if not group["requester_name"]: issues.append(f"Requester wajib diisi untuk Work Item dari baris {rows_in_group[0]['_row_no']}.")
    return groups, issues


def _leasing_import_options():
    source = request.form if request.form else (request.get_json(silent=True) or {})
    mode = str(source.get("grouping_mode") or "request_id_grouping").strip().lower()
    combined_id = str(source.get("combined_request_id") or "").strip() or None
    return mode, combined_id


def _leasing_import_preview_data():
    grouping_mode, combined_request_id = _leasing_import_options()
    raw_rows, source_headers, source_name, source_fingerprint = _leasing_read_import_source()
    if not raw_rows:
        raise ValueError("Tidak ada baris data untuk diimport.")
    normalized, mapped_headers, unmapped_headers, issues = _leasing_normalize_import_rows(raw_rows, source_headers)
    groups, group_issues = _leasing_import_groups(normalized, grouping_mode, combined_request_id)
    issues.extend(group_issues)
    request_ids = [g["request_id"] for g in groups if g.get("request_id")]
    existing_ids = set()
    if request_ids and not issues:
        with get_leasing_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT request_id FROM leasing.work_items WHERE LOWER(BTRIM(request_id)) = ANY(%s)", ([x.strip().lower() for x in request_ids],))
                existing_ids = {r[0] for r in cur.fetchall()}
        for existing_id in sorted(existing_ids):
            issues.append(f"Request ID {existing_id!r} sudah digunakan di Leasing. Gunakan ID berbeda atau kosongkan Request ID untuk membuat ID otomatis.")
    # Warn if raw fields exist but the simple intake importer won't create partner offer/negotiation data.
    commercial_keys = {_leasing_header_key(x) for x in ["Mitra", "MU", "MRC", "OTC", "SPH Mitra", "Start Presales", "durasi presales"]}
    commercial_columns = [h for h in source_headers if _leasing_header_key(h) in commercial_keys and any(_leasing_cell_value(r.get(h)) is not None for r in raw_rows[:50])]
    warnings = []
    if unmapped_headers:
        warnings.append("Kolom yang tidak dikenali dan tidak akan diimpor: " + ", ".join(unmapped_headers[:20]))
    if commercial_columns:
        warnings.append("Kolom komersial/historis berikut belum dimigrasikan oleh import intake ini: " + ", ".join(commercial_columns) + ". Import ini fokus pada Work Item dan requirement; jangan gunakan untuk migrasi historis final bila data penawaran harus dipertahankan.")
    fingerprint_material = f"{source_fingerprint or ''}|{grouping_mode}|{(combined_request_id or '').strip().lower()}"
    batch_fingerprint = hashlib.sha256(fingerprint_material.encode("utf-8")).hexdigest()
    duplicate_batch = None
    if batch_fingerprint:
        try:
            with get_leasing_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""SELECT id,source_filename,created_at,created_count,requirement_count,work_item_ids
                        FROM leasing.import_batches WHERE fingerprint=%s AND uploaded_by=%s AND allow_duplicate=FALSE
                        ORDER BY created_at DESC LIMIT 1""", (batch_fingerprint, session.get("username")))
                    duplicate_batch = cur.fetchone()
            if duplicate_batch:
                warnings.append(f"File dengan isi dan mode grouping yang sama pernah diimpor sebagai batch #{duplicate_batch['id']} pada {duplicate_batch['created_at']}. Import ulang akan membuat data baru; centang konfirmasi duplikasi bila memang disengaja.")
        except psycopg2.Error:
            app.logger.exception("Import batch duplicate check failed; schema migration may be missing")
            warnings.append("Riwayat duplikasi belum dapat diperiksa. Pastikan leasing_scale_hardening_migration.sql sudah diterapkan sebelum import produksi.")
    return {"source_name": source_name, "source_headers": source_headers, "rows": normalized, "groups": groups,
            "mapped_headers": mapped_headers, "unmapped_headers": unmapped_headers, "issues": issues,
            "warnings": warnings, "existing_ids": existing_ids, "grouping_mode": grouping_mode,
            "combined_request_id": combined_request_id, "batch_fingerprint": batch_fingerprint,
            "duplicate_batch": dict(duplicate_batch) if duplicate_batch else None}


def _leasing_import_response_preview(data):
    rows = data["rows"]
    return {"success": True, "source_name": data["source_name"], "source_headers": data["source_headers"],
            "mapped_columns": data["mapped_headers"], "unmapped_columns": data["unmapped_headers"],
            "row_count": len(rows), "work_item_count": len(data["groups"]),
            "requirement_count": len(rows), "issues": data["issues"], "warnings": data["warnings"],
            "sample_rows": [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows[:8]],
            "duplicate_batch": data.get("duplicate_batch"), "grouping_mode": data.get("grouping_mode"),
            "grouping_rule": ("Semua baris dalam file digabung menjadi satu Work Item dengan Request ID Work Item yang ditentukan pada form; Request ID lama per baris disimpan sebagai External Reference." if data.get("grouping_mode") == "single_work_item" else "Baris dengan Request ID sama digabung menjadi satu Work Item; baris dengan Request ID kosong masing-masing menjadi Work Item terpisah. Customer, Requester, Due Date, dan Notes harus konsisten dalam tiap grup.")}


@app.route("/api/leasing/import-batches", methods=["GET"])
@leasing_login_required
def leasing_import_batches():
    """Recent batch ledger so the buyer can audit imports and safely undo pristine batches."""
    page = _leasing_query_int(request.args.get("page"), 1, 1, 100000)
    size = _leasing_query_int(request.args.get("page_size"), 20, 10, 50)
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                where = "TRUE" if _is_leasing_admin() else "uploaded_by=%s"
                args = [] if _is_leasing_admin() else [session["username"]]
                cur.execute(f"SELECT COUNT(*) AS total FROM leasing.import_batches WHERE {where}", tuple(args))
                total = int(cur.fetchone()["total"] or 0)
                pages = max(1, math.ceil(total / size)); page = min(page, pages)
                cur.execute(f"""SELECT id,fingerprint,uploaded_by,source_filename,grouping_mode,work_item_ids,metadata,
                    created_count,requirement_count,created_at,allow_duplicate,undone_at,undone_by,undone_reason
                    FROM leasing.import_batches WHERE {where} ORDER BY created_at DESC,id DESC LIMIT %s OFFSET %s""",
                    tuple(args + [size, (page-1)*size]))
                batches = [dict(x) for x in cur.fetchall()]
        return jsonify({"success": True,"batches": batches,"pagination":{"page":page,"page_size":size,"total":total,"total_pages":pages}})
    except psycopg2.Error:
        app.logger.exception("Leasing import batch history failed")
        return jsonify({"success": False,"message":"Riwayat import belum tersedia. Pastikan migration reliability sudah diterapkan."}), 503


@app.route("/api/leasing/import-batches/<int:batch_id>/undo", methods=["POST"])
@leasing_login_required
def leasing_undo_import_batch(batch_id):
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    if len(reason) < 10:
        return jsonify({"success":False,"message":"Alasan membatalkan import wajib minimal 10 karakter."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leasing.import_batches WHERE id=%s FOR UPDATE", (batch_id,))
                batch = cur.fetchone()
                if not batch: return jsonify({"success":False,"message":"Batch import tidak ditemukan."}),404
                if not _is_leasing_admin() and batch["uploaded_by"] != session["username"]:
                    return jsonify({"success":False,"message":"Hanya uploader atau admin yang dapat membatalkan batch ini."}),403
                if batch.get("undone_at"):
                    return jsonify({"success":False,"message":"Batch ini sudah dibatalkan. Gunakan Pulihkan bila ingin mengembalikannya."}),409
                batch_metadata = batch.get("metadata") or {}
                batch_kind = str(batch_metadata.get("kind") or "").strip().lower() if isinstance(batch_metadata, dict) else ""
                if str(batch.get("grouping_mode") or "").strip().lower() == "commercial_targets" or batch_kind == "commercial_targets":
                    return jsonify({"success":False,"code":"UNSUPPORTED_BATCH_KIND","message":"Batch ini berisi perubahan Commercial Target, bukan pembuatan Work Item. Undo Work Item ditolak agar seluruh Work Item tidak terarsip tanpa sengaja. Tinjau riwayat target dan lakukan koreksi target yang terkontrol."}),409
                ids = [int(x) for x in (batch.get("work_item_ids") or [])]
                if not ids: return jsonify({"success":False,"message":"Batch tidak memiliki Work Item yang dapat dibatalkan."}),409
                cur.execute("SELECT id,request_id,archived_at,updated_at FROM leasing.work_items WHERE id=ANY(%s) FOR UPDATE", (ids,))
                items = cur.fetchall()
                if len(items) != len(ids) or any(row["archived_at"] for row in items):
                    return jsonify({"success":False,"message":"Sebagian Work Item tidak ada atau sudah diarsipkan; batch tidak diubah."}),409
                cur.execute("""SELECT COUNT(*) AS n FROM leasing.partner_outreaches WHERE work_item_id=ANY(%s)""", (ids,)); outreach_n=int(cur.fetchone()["n"] or 0)
                cur.execute("""SELECT COUNT(*) AS n FROM leasing.result_submissions WHERE work_item_id=ANY(%s)""", (ids,)); submission_n=int(cur.fetchone()["n"] or 0)
                cur.execute("""SELECT COUNT(*) AS n FROM leasing.commercial_targets WHERE work_item_id=ANY(%s)""", (ids,)); target_n=int(cur.fetchone()["n"] or 0)
                cur.execute("""SELECT COUNT(*) AS n FROM leasing.requirements r JOIN leasing.work_items w ON w.id=r.work_item_id
                    WHERE w.id=ANY(%s) AND r.updated_at > %s""", (ids,batch["created_at"])); changed_req_n=int(cur.fetchone()["n"] or 0)
                cur.execute("""SELECT COUNT(*) AS n FROM leasing.activity_events WHERE work_item_id=ANY(%s)
                    AND event_type NOT IN ('work_item_imported','work_item_created') AND occurred_at > %s""", (ids,batch["created_at"])); later_activity=int(cur.fetchone()["n"] or 0)
                cur.execute("SELECT COUNT(*) AS n FROM leasing.work_items WHERE id=ANY(%s) AND updated_at > %s", (ids,batch["created_at"])); changed_items=int(cur.fetchone()["n"] or 0)
                if any((outreach_n,submission_n,target_n,changed_req_n,later_activity,changed_items)):
                    return jsonify({"success":False,"code":"BATCH_HAS_LATER_CHANGES","message":"Undo otomatis ditolak karena batch sudah digunakan/diubah setelah import. Arsipkan Work Item secara terpisah setelah meninjau histori agar data operasional tidak hilang.","checks":{"outreaches":outreach_n,"submissions":submission_n,"targets":target_n,"edited_requirements":changed_req_n,"later_activity":later_activity,"edited_work_items":changed_items}}),409
                archive_reason=f"Undo import batch #{batch_id}: {reason}"
                cur.execute("UPDATE leasing.work_items SET archived_at=NOW(),archived_by=%s,archive_reason=%s,updated_at=NOW() WHERE id=ANY(%s)", (session["username"],archive_reason,ids))
                cur.execute("UPDATE leasing.import_batches SET undone_at=NOW(),undone_by=%s,undone_reason=%s WHERE id=%s", (session["username"],reason,batch_id))
                for item in items:
                    _leasing_field_audit(cur,"work_item",item["id"],item["id"],"undo_import_batch",session["username"],{"archived_at":None},{"archived_at":"NOW()","import_batch_id":batch_id},reason)
                    leasing_activity(cur,item["id"],"work_item_import_undo",f"Import batch #{batch_id} dibatalkan",session["username"],{"batch_id":batch_id,"reason":reason})
            conn.commit()
        return jsonify({"success":True,"message":f"Batch #{batch_id} dibatalkan secara aman; {len(ids)} Work Item diarsipkan dan tetap dapat dipulihkan."})
    except psycopg2.Error:
        app.logger.exception("Leasing import batch undo failed")
        return jsonify({"success":False,"message":"Undo gagal; transaksi dibatalkan. Pastikan migration reliability telah diterapkan."}),503


@app.route("/api/leasing/import-batches/<int:batch_id>/restore", methods=["POST"])
@leasing_login_required
def leasing_restore_import_batch(batch_id):
    payload=request.get_json(silent=True) or {}; reason=str(payload.get("reason") or "").strip()
    if len(reason)<10: return jsonify({"success":False,"message":"Alasan pemulihan batch wajib minimal 10 karakter."}),400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leasing.import_batches WHERE id=%s FOR UPDATE",(batch_id,)); batch=cur.fetchone()
                if not batch: return jsonify({"success":False,"message":"Batch tidak ditemukan."}),404
                if not _is_leasing_admin() and batch["uploaded_by"]!=session["username"]: return jsonify({"success":False,"message":"Hanya uploader atau admin yang dapat memulihkan batch ini."}),403
                if not batch.get("undone_at"): return jsonify({"success":False,"message":"Batch ini tidak sedang dibatalkan."}),409
                batch_metadata = batch.get("metadata") or {}
                batch_kind = str(batch_metadata.get("kind") or "").strip().lower() if isinstance(batch_metadata, dict) else ""
                if str(batch.get("grouping_mode") or "").strip().lower() == "commercial_targets" or batch_kind == "commercial_targets":
                    return jsonify({"success":False,"code":"UNSUPPORTED_BATCH_KIND","message":"Batch ini adalah import Commercial Target. Pemulihan sebagai batch Work Item tidak diizinkan."}),409
                ids=[int(x) for x in (batch.get("work_item_ids") or [])]
                expected=f"Undo import batch #{batch_id}: {batch.get('undone_reason') or ''}"
                cur.execute("SELECT id,archive_reason,archived_at FROM leasing.work_items WHERE id=ANY(%s) FOR UPDATE",(ids,)); items=cur.fetchall()
                if len(items)!=len(ids) or any((not row["archived_at"] or row["archive_reason"]!=expected) for row in items):
                    return jsonify({"success":False,"message":"Status arsip salah satu Work Item berubah setelah undo; pemulihan batch otomatis ditolak."}),409
                cur.execute("UPDATE leasing.work_items SET archived_at=NULL,archived_by=NULL,archive_reason=NULL,updated_at=NOW() WHERE id=ANY(%s)",(ids,))
                cur.execute("UPDATE leasing.import_batches SET undone_at=NULL,undone_by=NULL,undone_reason=NULL WHERE id=%s",(batch_id,))
                for item in items:
                    _leasing_field_audit(cur,"work_item",item["id"],item["id"],"restore_import_batch",session["username"],{"archived_at":item["archived_at"]},{"archived_at":None},reason)
                    leasing_activity(cur,item["id"],"work_item_import_restored",f"Import batch #{batch_id} dipulihkan",session["username"],{"batch_id":batch_id,"reason":reason})
            conn.commit()
        return jsonify({"success":True,"message":f"Batch #{batch_id} dipulihkan ({len(ids)} Work Item)."})
    except psycopg2.Error:
        app.logger.exception("Leasing import batch restore failed")
        return jsonify({"success":False,"message":"Pemulihan batch gagal; transaksi dibatalkan."}),503


@app.route("/api/leasing/system/schema-status", methods=["GET"])
@leasing_admin_required
def leasing_schema_status():
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT version,description,checksum_sha256,applied_at,applied_by FROM leasing.schema_migrations ORDER BY applied_at DESC,version DESC")
                rows=[dict(x) for x in cur.fetchall()]
        return jsonify({"success":True,"migrations":rows,"latest_version":rows[0]["version"] if rows else None,
                        "expected_release":"20261028_quality_reliability_r2"})
    except psycopg2.Error:
        app.logger.exception("Leasing schema status unavailable")
        return jsonify({"success":False,"message":"Migration registry belum tersedia. Terapkan migration reliability r2 setelah backup dan validasi schema prasyarat."}),503


@app.route("/api/leasing/import/template", methods=["GET"])
@leasing_login_required
def leasing_import_template():
    template_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Template_Import_Leasing.xlsx")
    if not os.path.isfile(template_path):
        app.logger.error("Leasing XLSX template missing: %s", template_path)
        return jsonify({"success": False, "message": "Template XLSX belum tersedia di folder aplikasi. Deploy Template_Import_Leasing.xlsx bersama app.py."}), 500
    return send_file(template_path, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name="Template_Import_Leasing.xlsx", conditional=True)


@app.route("/api/leasing/import/preview", methods=["POST"])
@leasing_login_required
def leasing_import_preview():
    try:
        data = _leasing_import_preview_data()
        return jsonify(_leasing_import_response_preview(data))
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception:
        app.logger.exception("Leasing import preview failed")
        return jsonify({"success": False, "message": "Gagal membaca data import. Periksa format file/kolom dan log server."}), 400


@app.route("/api/leasing/import", methods=["POST"])
@leasing_login_required
def leasing_import():
    try:
        data = _leasing_import_preview_data()
        if data["issues"]:
            return jsonify({"success": False, "message": "Import dibatalkan karena ada masalah pada data.", "issues": data["issues"], "warnings": data["warnings"]}), 400
        rows, groups = data["rows"], data["groups"]
        username = session["username"]
        owner_payload = request.form if request.form else (request.get_json(silent=True) or {})
        allow_duplicate_import = str(owner_payload.get("allow_duplicate_import") or "").strip().lower() in {"1", "true", "yes", "on"}
        if data.get("duplicate_batch") and not allow_duplicate_import:
            return jsonify({"success": False, "duplicate_batch": data["duplicate_batch"],
                "message": f"File ini sudah diimpor pada batch #{data['duplicate_batch']['id']}. Untuk menghindari duplikasi, import diblokir. Bila sengaja membuat batch baru, konfirmasi duplikasi pada preview dan coba lagi."}), 409
        # Older clients may not send buyer_owner_id; preserve the historical self-assign behavior.
        # The current UI sends a selected owner explicitly for each import batch.
        if "buyer_owner_id" in owner_payload:
            default_owner = str(owner_payload.get("buyer_owner_id") or "").strip()
            if not _is_leasing_admin() and default_owner != username:
                return jsonify({"success": False, "message": "Buyer hanya boleh mengimpor ke antreannya sendiri; assignment batch antar-buyer dilakukan admin."}), 403
            if not default_owner or not leasing_owner_is_valid(default_owner):
                return jsonify({"success": False, "message": "Buyer/PIC owner tidak valid. Pilih akun dengan role Buyer/Admin Leasing."}), 400
        else:
            default_owner = username if leasing_owner_is_valid(username) else None
        created_ids = []
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                for group in groups:
                    group_rows = group["rows"]
                    first = group_rows[0]
                    raw_request_id = group["request_id"] or ("LEA-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper())
                    request_id = _leasing_assert_request_id_available(cur, raw_request_id)
                    customer_name = str(group["customer_name"] or "").strip()
                    requester_name = str(group["requester_name"] or "").strip()
                    cur.execute("SELECT id FROM leasing.customers WHERE lower(customer_name)=lower(%s) ORDER BY id LIMIT 1", (customer_name,))
                    customer = cur.fetchone()
                    if not customer:
                        cur.execute("INSERT INTO leasing.customers (customer_name) VALUES (%s) RETURNING id", (customer_name,))
                        customer = cur.fetchone()
                    cur.execute("""INSERT INTO leasing.work_items
                        (request_id, customer_id, requester_name, request_due_date, buyer_owner_id, notes, created_by, work_type, project_name)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (request_id, customer["id"], requester_name, first.get("request_due_date"), default_owner,
                         first.get("notes"), username, group.get("work_type", "non_project"), group.get("project_name")))
                    work_id = cur.fetchone()["id"]
                    created_ids.append({"id": work_id, "request_id": request_id, "requirement_count": len(group_rows)})
                    for idx, row in enumerate(group_rows, start=1):
                        fields = _leasing_validate_requirement_payload(row, f"Baris {row['_row_no']}", group.get("work_type", "non_project"))
                        cur.execute("""INSERT INTO leasing.requirements
                            (work_item_id, requirement_no, order_type, si, area, address, gedung_kawasan, latitude, longitude,
                             a_end, z_end, bandwidth, bandwidth_unit, service_type, special_features,
                             existing_mrc_amount, existing_mrc_currency, zone, site_name, postal_code,
                             project_mrc_inet_dedicated_25, project_mrc_metro_25, requested_otc, project_notes,
                             external_reference, existing_mrc_inet_dedicated_25_amount, existing_mrc_metro_25_amount, requested_services)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (work_id, idx, fields["order_type"], fields["si"], fields["area"], fields["address"], fields["gedung_kawasan"], fields["latitude"], fields["longitude"], fields["a_end"], fields["z_end"], fields["bandwidth"], fields["bandwidth_unit"], fields["service_type"], fields["special_features"], fields["existing_mrc_amount"], fields["existing_mrc_currency"], fields.get("zone"), fields.get("site_name"), fields.get("postal_code"), fields.get("project_mrc_inet_dedicated_25"), fields.get("project_mrc_metro_25"), fields.get("requested_otc"), fields.get("project_notes"), fields.get("external_reference"), fields.get("existing_mrc_inet_dedicated_25_amount"), fields.get("existing_mrc_metro_25_amount"), fields.get("requested_services") or []))
                    leasing_activity(cur, work_id, "work_item_imported", f"Work Item diimpor dari {data['source_name']}", username,
                        {"request_id": request_id, "source_row_numbers": [r["_row_no"] for r in group_rows], "requirement_count": len(group_rows), "import_mode": data.get("grouping_mode", "request_id_grouping"), "source_request_ids": [r.get("request_id") for r in group_rows if r.get("request_id")]})
                cur.execute("""INSERT INTO leasing.import_batches
                    (fingerprint,uploaded_by,source_filename,grouping_mode,work_item_ids,created_count,requirement_count,allow_duplicate,metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                    (data["batch_fingerprint"], username, data["source_name"], data["grouping_mode"],
                     [int(x["id"]) for x in created_ids], len(created_ids), len(rows), allow_duplicate_import,
                     json.dumps({"combined_request_id": data.get("combined_request_id"), "source_fingerprint": data.get("source_fingerprint") or data.get("batch_fingerprint")})))
            conn.commit()
        return jsonify({"success": True, "message": f"Import berhasil: {len(created_ids)} Work Item, {len(rows)} requirement.",
                        "work_item_count": len(created_ids), "requirement_count": len(rows), "created_work_items": created_ids,
                        "warnings": data["warnings"]}), 201
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.IntegrityError:
        app.logger.info("Leasing import blocked by request-ID or idempotency uniqueness constraint")
        return jsonify({"success": False, "message": "Import duplikat atau konflik data terdeteksi. Tidak ada perubahan yang disimpan; gunakan ID baru atau konfirmasi batch duplikat bila memang disengaja."}), 409
    except psycopg2.Error:
        app.logger.exception("Leasing import failed")
        return jsonify({"success": False, "message": "Import gagal disimpan ke database. Transaksi dibatalkan; periksa log server."}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    
    # PERHATIAN: 
    # Untuk lingkungan Development, Anda bisa menggunakan app.run ini.
    # Namun saat aplikasi sudah final (Production), 
    # sangat direkomendasikan untuk menjalankannya dengan Gunicorn.
    # Contoh perintah di terminal: 
    # gunicorn -w 4 -b 0.0.0.0:5001 app:app
    app.run(host="0.0.0.0", port=port, debug=True)