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
import re
import unicodedata
from datetime import datetime
import contextlib
from werkzeug.utils import secure_filename

# ============================================================================
# APP CONFIGURATION
# ============================================================================
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
CORS(app)
app.secret_key = "presourcing_secret_key_123"

# Konfigurasi Koneksi PostgreSQL
DB_HOST = "localhost"
DB_NAME = "presourcing_db"
DB_USER = "presourcing_master"  
DB_PASS = "R1L1DemDldxks@"     

# Inisialisasi Connection Pool (Min 1, Max 20 koneksi secara bersamaan)
db_pool = ThreadedConnectionPool(
    1, 20,
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
LEASING_DB_NAME = os.getenv("LEASING_DB_NAME", "leasing_db")
leasing_db_pool = ThreadedConnectionPool(
    1, 10,
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
    if not has_leasing_access(session.get("role")):
        return "Akses Leasing hanya untuk Buyer/Admin Leasing.", 403
    return render_template(
        "leasing-dashboard.html",
        can_access_ms=has_ms_access(session.get("role")),
    )

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
            
            # DEFAULT USERS
            for user_data in [
                ("admin", "admin123", "Admin Presourcing", "Presourcing Control", "admin"),
                ("master", "master123", "Master Admin", "System Control", "admin"),
                ("tester", "tester123", "QA Tester", "Testing Team", "sa"),
            ]:
                cursor.execute("SELECT COUNT(*) FROM users WHERE username = %s", (user_data[0],))
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO users (username, password, full_name, department, role) VALUES (%s, %s, %s, %s, %s)", user_data)
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
    payload = request.json or {}
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO users (username, password, full_name, department, role) VALUES (%s, %s, %s, %s, %s)", 
                    (payload.get("username"), payload.get("password"), payload.get("full_name"), payload.get("department", ""), payload.get("role", "sa"))
                )
                conn.commit()
                return jsonify({"success": True, "message": "Registrasi berhasil!"}), 201
    except psycopg2.IntegrityError:
        return jsonify({"success": False, "message": "Username sudah terdaftar!"}), 400

@app.route("/api/login", methods=["POST"])
def login():
    payload = request.json or {}
    with get_db_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT username, full_name, department, role FROM users WHERE username = %s AND password = %s", (payload.get("username"), payload.get("password")))
            user = cursor.fetchone()
            if user:
                session.update({"username": user["username"], "full_name": user["full_name"], "department": user["department"], "role": user["role"]})
                return jsonify({
                    "success": True,
                    "user": user,
                    "redirect_url": url_for(preferred_landing_endpoint(user["role"])),
                }), 200
            return jsonify({"success": False, "message": "Username atau Password salah!"}), 401

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


def leasing_login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("username"):
            return jsonify({"success": False, "message": "Login diperlukan."}), 401
        if not has_leasing_access(session.get("role")):
            return jsonify({"success": False, "message": "Akses Leasing hanya untuk Buyer/Admin Leasing."}), 403
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

def leasing_activity(cursor, work_item_id, event_type, summary, actor, metadata=None):
    cursor.execute(
        "INSERT INTO leasing.activity_events (work_item_id, event_type, event_summary, actor_id, metadata) "
        "VALUES (%s, %s, %s, %s, %s::jsonb)",
        (work_item_id, event_type, summary, actor, json.dumps(metadata or {}))
    )


@app.route("/api/leasing/dashboard", methods=["GET"])
@leasing_login_required
def leasing_dashboard():
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT
                    COUNT(*) FILTER (WHERE case_status='open') AS open_cases,
                    COUNT(*) FILTER (WHERE case_status='open' AND request_due_date < CURRENT_DATE) AS overdue_cases,
                    COUNT(*) FILTER (WHERE case_status='open' AND request_due_date = CURRENT_DATE) AS due_today,
                    COUNT(*) FILTER (WHERE case_status='open' AND current_stage='result_submission') AS pending_submission
                    FROM leasing.work_items""")
                summary = dict(cur.fetchone())
                cur.execute("""SELECT w.id, w.request_id, c.customer_name, w.requester_name,
                    w.requester_division, w.request_due_date, w.current_stage, w.case_status,
                    w.buyer_owner_id, w.created_at,
                    COUNT(DISTINCT r.id) AS requirement_count,
                    COUNT(DISTINCT r.id) FILTER (WHERE r.status IN ('resolved','stopped')) AS resolved_count,
                    COUNT(DISTINCT o.id) FILTER (WHERE o.response_status IN ('sent','awaiting_response','partial_response')) AS pending_partner_responses,
                    MIN(o.next_follow_up_at) FILTER (WHERE o.next_follow_up_at IS NOT NULL AND o.response_status IN ('sent','awaiting_response','partial_response')) AS next_follow_up_at
                    FROM leasing.work_items w
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    LEFT JOIN leasing.requirements r ON r.work_item_id=w.id
                    LEFT JOIN leasing.partner_outreaches o ON o.work_item_id=w.id
                    GROUP BY w.id, c.customer_name
                    ORDER BY CASE WHEN w.case_status='open' AND w.request_due_date < CURRENT_DATE THEN 0 ELSE 1 END,
                    w.request_due_date NULLS LAST, w.updated_at DESC LIMIT 200""")
                items = [dict(row) for row in cur.fetchall()]
                cur.execute("""SELECT
                    COALESCE(NULLIF(w.buyer_owner_id, ''), '__unassigned__') AS buyer_owner_id,
                    COUNT(*) FILTER (WHERE w.case_status='open') AS open_cases,
                    COUNT(*) FILTER (WHERE w.case_status='open' AND w.request_due_date < CURRENT_DATE) AS overdue_cases,
                    COUNT(*) FILTER (WHERE w.case_status='open' AND w.request_due_date = CURRENT_DATE) AS due_today,
                    COUNT(*) FILTER (WHERE w.case_status='open' AND w.current_stage='result_submission') AS pending_submission
                    FROM leasing.work_items w
                    GROUP BY COALESCE(NULLIF(w.buyer_owner_id, ''), '__unassigned__')
                    ORDER BY open_cases DESC, buyer_owner_id""")
                buyer_workload = [dict(row) for row in cur.fetchall()]
                cur.execute("""SELECT
                    COALESCE(NULLIF(o.follow_up_owner_id, ''), NULLIF(w.buyer_owner_id, ''), '__unassigned__') AS buyer_owner_id,
                    COUNT(*) AS pending_followups
                    FROM leasing.partner_outreaches o
                    JOIN leasing.work_items w ON w.id=o.work_item_id
                    WHERE w.case_status='open'
                      AND o.response_status IN ('sent','awaiting_response','partial_response')
                    GROUP BY COALESCE(NULLIF(o.follow_up_owner_id, ''), NULLIF(w.buyer_owner_id, ''), '__unassigned__')""")
                followup_counts = {row['buyer_owner_id']: row['pending_followups'] for row in cur.fetchall()}
                for owner_row in buyer_workload:
                    owner_row['pending_followups'] = followup_counts.get(owner_row['buyer_owner_id'], 0)
                cur.execute("""SELECT o.id, o.work_item_id, w.request_id, p.partner_name,
                    o.response_status, o.next_follow_up_at, o.sent_at,
                    COALESCE(NULLIF(o.follow_up_owner_id, ''), NULLIF(w.buyer_owner_id, ''), '__unassigned__') AS buyer_owner_id,
                    c.customer_name
                    FROM leasing.partner_outreaches o
                    JOIN leasing.work_items w ON w.id=o.work_item_id
                    JOIN leasing.partners p ON p.id=o.partner_id
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id
                    WHERE w.case_status='open' AND o.response_status IN ('sent','awaiting_response','partial_response')
                    ORDER BY o.next_follow_up_at NULLS FIRST LIMIT 100""")
                followups = [dict(row) for row in cur.fetchall()]
        # Resolve friendly labels from shared M&S identity table; data remains isolated in leasing_db.
        try:
            with get_db_connection() as identity_conn:
                with identity_conn.cursor(cursor_factory=RealDictCursor) as identity_cur:
                    identity_cur.execute("""SELECT username, full_name, department, role
                        FROM public.users WHERE role IN ('buyer','leasing_admin','platform_admin')
                        ORDER BY full_name, username""")
                    assignees = [dict(row) for row in identity_cur.fetchall()]
        except psycopg2.Error:
            app.logger.exception("Unable to load Leasing assignees from shared identity store")
            assignees = []
        # Include eligible Leasing users with zero assigned work so workload comparison is fair.
        workload_by_owner = {row["buyer_owner_id"]: row for row in buyer_workload}
        expanded_workload = []
        for assignee in assignees:
            owner = assignee["username"]
            expanded_workload.append(workload_by_owner.pop(owner, {
                "buyer_owner_id": owner, "open_cases": 0, "overdue_cases": 0,
                "due_today": 0, "pending_submission": 0, "pending_followups": 0
            }))
        # Preserve unassigned items and legacy owners whose accounts no longer carry a Leasing role.
        if "__unassigned__" in workload_by_owner:
            expanded_workload.append(workload_by_owner.pop("__unassigned__"))
        expanded_workload.extend(workload_by_owner.values())
        return jsonify({"success": True, "summary": summary, "work_items": items,
                        "follow_ups": followups, "buyer_workload": expanded_workload,
                        "assignees": assignees})
    except psycopg2.Error:
        app.logger.exception("Leasing dashboard query failed")
        return jsonify({"success": False, "message": "Gagal memuat dashboard Leasing. Pastikan schema Leasing sudah diterapkan."}), 500


@app.route("/api/leasing/assignees", methods=["GET"])
@leasing_login_required
def leasing_assignees():
    """List accounts eligible for Leasing ownership from the shared identity database."""
    try:
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT username, full_name, department, role
                    FROM public.users
                    WHERE role IN ('buyer','leasing_admin','platform_admin')
                    ORDER BY CASE role WHEN 'buyer' THEN 0 WHEN 'leasing_admin' THEN 1 ELSE 2 END,
                             full_name, username""")
                return jsonify({"success": True, "assignees": [dict(row) for row in cur.fetchall()]})
    except psycopg2.Error:
        app.logger.exception("Leasing assignee list failed")
        return jsonify({"success": False, "message": "Gagal memuat daftar Buyer/PIC."}), 500


@app.route("/api/leasing/work-items", methods=["GET", "POST"])
@leasing_login_required
def leasing_work_items():
    if request.method == "GET":
        try:
            with get_leasing_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""SELECT w.*, c.customer_name,
                        COUNT(DISTINCT r.id) AS requirement_count,
                        COUNT(DISTINCT r.id) FILTER (WHERE r.status IN ('resolved','stopped')) AS resolved_count
                        FROM leasing.work_items w LEFT JOIN leasing.customers c ON c.id=w.customer_id
                        LEFT JOIN leasing.requirements r ON r.work_item_id=w.id
                        GROUP BY w.id, c.customer_name ORDER BY w.created_at DESC LIMIT 500""")
                    return jsonify({"success": True, "work_items": [dict(x) for x in cur.fetchall()]})
        except psycopg2.Error:
            app.logger.exception("Leasing work item list failed")
            return jsonify({"success": False, "message": "Schema Leasing belum tersedia atau query gagal."}), 500

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
    if not leasing_owner_is_valid(owner):
        return jsonify({"success": False, "message": "Buyer/PIC tidak ditemukan atau tidak memiliki role Leasing. Pilih akun pada daftar Buyer/PIC."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
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
                         existing_mrc_amount, existing_mrc_currency)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (work_item_id, idx, req["order_type"], req["si"], req["area"], req["address"],
                         req["gedung_kawasan"], req["latitude"], req["longitude"], req["a_end"], req["z_end"], req["bandwidth"],
                         req["bandwidth_unit"], req["service_type"], req["special_features"],
                         req["existing_mrc_amount"], req["existing_mrc_currency"]))
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
                    cur.execute("SELECT id FROM leasing.work_items WHERE id=%s", (work_item_id,))
                    if not cur.fetchone(): return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                    if changes.get("case_status") == "closed":
                        cur.execute("SELECT COUNT(*) AS total, COUNT(*) FILTER (WHERE status IN ('resolved','stopped')) AS done FROM leasing.requirements WHERE work_item_id=%s", (work_item_id,))
                        progress = cur.fetchone()
                        if progress["total"] == 0 or progress["total"] != progress["done"]:
                            return jsonify({"success": False, "message": "Case belum bisa ditutup: semua requirement harus resolved/stopped."}), 409
                    assignments, values = [], []
                    for key, value in changes.items():
                        if key == "closed_at":
                            assignments.append("closed_at = NOW()" if value == "NOW()" else "closed_at = NULL")
                        else:
                            assignments.append(f"{key} = %s")
                            values.append(value or None if key == "request_due_date" else value)
                    values.append(work_item_id)
                    cur.execute(f"UPDATE leasing.work_items SET {', '.join(assignments)} WHERE id=%s", values)
                    leasing_activity(cur, work_item_id, "work_item_updated", "Work Item diperbarui", session["username"], changes)
                conn.commit()
            return jsonify({"success": True, "message": "Work Item diperbarui."})
        except psycopg2.Error:
            app.logger.exception("Leasing work item update failed")
            return jsonify({"success": False, "message": "Gagal memperbarui Work Item."}), 400

    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT w.*, c.customer_name FROM leasing.work_items w
                    LEFT JOIN leasing.customers c ON c.id=w.customer_id WHERE w.id=%s""", (work_item_id,))
                work_item = cur.fetchone()
                if not work_item: return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                cur.execute("SELECT * FROM leasing.requirements WHERE work_item_id=%s ORDER BY requirement_no", (work_item_id,))
                requirements = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT o.*, p.partner_name FROM leasing.partner_outreaches o
                    JOIN leasing.partners p ON p.id=o.partner_id WHERE o.work_item_id=%s ORDER BY o.created_at DESC""", (work_item_id,))
                outreaches = [dict(x) for x in cur.fetchall()]
                cur.execute("""SELECT oro.outreach_id, oro.requirement_id,
                    CASE current_line.feasibility_status
                        WHEN 'can_provide' THEN 'can_provide' WHEN 'cannot_provide' THEN 'cannot_provide'
                        WHEN 'needs_clarification' THEN 'needs_clarification' ELSE oro.response_status END AS requirement_response_status,
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
                    o.partner_id, p.partner_name, r.requirement_no, r.order_type, r.si, r.area, r.address, r.gedung_kawasan, r.a_end, r.z_end,
                    r.bandwidth, r.bandwidth_unit, r.service_type
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
        return jsonify({"success": True, "work_item": dict(work_item), "requirements": requirements,
                        "partner_outreaches": outreaches, "outreach_requirements": outreach_requirements,
                        "offers": offers, "offer_lines": offer_lines,
                        "commercial_targets": commercial_targets, "negotiation_events": negotiation_events, "result_submissions": submissions,
                        "submission_lines": submission_lines, "activity": activity})
    except psycopg2.Error:
        app.logger.exception("Leasing work item detail failed")
        return jsonify({"success": False, "message": "Gagal memuat detail Work Item."}), 500


@app.route("/api/leasing/partners", methods=["GET", "POST"])
@leasing_login_required
def leasing_partners():
    payload = request.get_json(silent=True) or {}
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if request.method == "POST":
                    name = str(payload.get("partner_name") or "").strip()
                    if not name: return jsonify({"success": False, "message": "partner_name wajib diisi."}), 400
                    cur.execute("""INSERT INTO leasing.partners (partner_name, partner_code, contact_name, contact_email, contact_phone, notes)
                        VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""", (name, payload.get("partner_code"), payload.get("contact_name"), payload.get("contact_email"), payload.get("contact_phone"), payload.get("notes")))
                    partner = dict(cur.fetchone()); conn.commit()
                    return jsonify({"success": True, "partner": partner}), 201
                cur.execute("SELECT * FROM leasing.partners WHERE is_active=TRUE ORDER BY partner_name")
                return jsonify({"success": True, "partners": [dict(x) for x in cur.fetchall()]})
    except psycopg2.IntegrityError:
        return jsonify({"success": False, "message": "Partner code sudah digunakan."}), 409
    except psycopg2.Error:
        app.logger.exception("Leasing partners query failed")
        return jsonify({"success": False, "message": "Gagal memproses data partner."}), 500


@app.route("/api/leasing/work-items/<int:work_item_id>/outreaches", methods=["POST"])
@leasing_login_required
def leasing_create_outreach(work_item_id):
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
    if not changes: return jsonify({"success": False, "message": "Tidak ada field yang diperbarui."}), 400
    if "response_status" in changes and changes["response_status"] not in {"draft", "sent", "awaiting_response", "partial_response", "responded", "no_bid", "cancelled"}:
        return jsonify({"success": False, "message": "response_status tidak valid."}), 400
    if "follow_up_owner_id" in changes:
        owner = str(changes.get("follow_up_owner_id") or "").strip()
        if owner and not leasing_owner_is_valid(owner):
            return jsonify({"success": False, "message": "PIC follow-up tidak ditemukan atau tidak memiliki role Leasing."}), 400
        changes["follow_up_owner_id"] = owner or None
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT work_item_id FROM leasing.partner_outreaches WHERE id=%s", (outreach_id,)); row=cur.fetchone()
                if not row: return jsonify({"success": False, "message": "Outreach tidak ditemukan."}), 404
                sets=[]; vals=[]
                for k,v in changes.items(): sets.append(f"{k}=%s"); vals.append(v or None)
                vals.append(outreach_id)
                cur.execute(f"UPDATE leasing.partner_outreaches SET {', '.join(sets)} WHERE id=%s", vals)
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
    if not isinstance(lines, list) or not lines:
        return jsonify({"success": False, "message": "Minimal satu baris penawaran harus dicatat."}), 400
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
            for field, label in (("mrc_amount", "MRC"), ("otc_amount", "OTC")):
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
            has_price = amounts["mrc_amount"] is not None or amounts["otc_amount"] is not None
            if has_price and feasibility == "pending":
                raise ValueError(f"Baris {index}: pilih Can Provide sebelum memasukkan harga.")
            if has_price and feasibility == "cannot_provide":
                raise ValueError(f"Baris {index}: harga tidak boleh diisi jika status Cannot Provide.")
            if has_price:
                if not re.fullmatch(r"[A-Z]{3}", currency):
                    raise ValueError(f"Baris {index}: currency wajib berupa kode 3 huruf saat harga diisi.")
            else:
                currency = None
            if feasibility == "pending" and not notes:
                continue
            normalized_lines.append({"requirement_id": requirement_id, **amounts, "feasibility_status": feasibility,
                                     "currency": currency, "notes": notes})
        if not normalized_lines:
            raise ValueError("Isi setidaknya satu hasil penawaran.")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                result = _leasing_record_offer_version(
                    cur, outreach_id, normalized_lines, session["username"], "manual",
                    offer_notes=payload.get("notes"), received_at=payload.get("received_at"),
                    valid_until=payload.get("valid_until"), source_label="manual input")
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
    if request.method == "GET":
        try:
            with get_leasing_db_connection() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""SELECT ct.*, r.requirement_no, r.gedung_kawasan
                        FROM leasing.commercial_targets ct LEFT JOIN leasing.requirements r ON r.id=ct.requirement_id
                        WHERE ct.work_item_id=%s ORDER BY ct.requirement_id NULLS FIRST, ct.metric, ct.created_at DESC""", (work_item_id,))
                    return jsonify({"success": True, "commercial_targets": [dict(x) for x in cur.fetchall()]})
        except psycopg2.Error:
            app.logger.exception("Leasing commercial targets query failed")
            return jsonify({"success": False, "message": "Gagal memuat commercial target."}), 500

    payload = request.get_json(silent=True) or {}
    metric = payload.get("metric")
    if metric not in {"mrc", "otc"}:
        return jsonify({"success": False, "message": "metric harus mrc atau otc."}), 400
    try:
        amount = float(payload.get("target_amount"))
        if amount < 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "target_amount harus angka non-negatif."}), 400
    currency = str(payload.get("currency") or "IDR").strip().upper()
    if len(currency) != 3:
        return jsonify({"success": False, "message": "currency harus berupa kode 3 huruf, misalnya IDR."}), 400
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT id FROM leasing.work_items WHERE id=%s", (work_item_id,))
                if not cur.fetchone():
                    return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                requirement_id = payload.get("requirement_id") or None
                if requirement_id:
                    try:
                        requirement_id = int(requirement_id)
                    except (TypeError, ValueError):
                        return jsonify({"success": False, "message": "requirement_id tidak valid."}), 400
                    cur.execute("SELECT id FROM leasing.requirements WHERE id=%s AND work_item_id=%s", (requirement_id, work_item_id))
                    if not cur.fetchone():
                        return jsonify({"success": False, "message": "Requirement bukan milik Work Item ini."}), 400
                cur.execute("""INSERT INTO leasing.commercial_targets
                    (work_item_id, requirement_id, metric, target_amount, currency, target_source, notes, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (work_item_id, requirement_id, metric, amount, currency,
                     payload.get("target_source", "requester"), payload.get("notes"), session["username"]))
                target_id = cur.fetchone()["id"]
                leasing_activity(cur, work_item_id, "commercial_target_recorded", "Target komersial dicatat", session["username"],
                                 {"target_id": target_id, "metric": metric, "target_amount": amount, "currency": currency, "requirement_id": requirement_id})
            conn.commit()
        return jsonify({"success": True, "target_id": target_id}), 201
    except psycopg2.Error:
        app.logger.exception("Leasing commercial target save failed")
        return jsonify({"success": False, "message": "Gagal menyimpan commercial target."}), 400


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
        if number < 0:
            raise ValueError(f"{field_name} tidak boleh negatif.")
        return number
    try:
        mrc = optional_nonnegative_number(payload.get("mrc_amount"), "MRC")
        otc = optional_nonnegative_number(payload.get("otc_amount"), "OTC")
        currency = (str(payload.get("currency") or "IDR").strip().upper() if mrc is not None or otc is not None else None)
        if currency is not None and len(currency) != 3:
            raise ValueError("Currency harus berupa kode 3 huruf.")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT o.work_item_id FROM leasing.partner_offer_lines pol
                    JOIN leasing.partner_offers po ON po.id=pol.offer_id
                    JOIN leasing.partner_outreaches o ON o.id=po.outreach_id WHERE pol.id=%s""", (offer_line_id,))
                line = cur.fetchone()
                if not line:
                    return jsonify({"success": False, "message": "Offer line tidak ditemukan."}), 404
                cur.execute("""INSERT INTO leasing.negotiation_events
                    (offer_line_id, event_type, mrc_amount, otc_amount, currency, notes, created_by)
                    VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (offer_line_id, event_type, mrc, otc, currency, payload.get("notes"), session["username"]))
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


@app.route("/api/leasing/work-items/<int:work_item_id>/result-submissions", methods=["POST"])
@leasing_login_required
def leasing_create_result_submission(work_item_id):
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
    payload = request.get_json(silent=True) or {}
    try:
        values = _leasing_validate_requirement_payload(payload, "Requirement baru")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT case_status FROM leasing.work_items WHERE id=%s FOR UPDATE", (work_item_id,))
                work_item = cur.fetchone()
                if not work_item:
                    return jsonify({"success": False, "message": "Work Item tidak ditemukan."}), 404
                if work_item["case_status"] != "open":
                    return jsonify({"success": False, "message": "Requirement baru hanya bisa ditambahkan ke Work Item yang masih open."}), 409
                cur.execute("SELECT COALESCE(MAX(requirement_no),0)+1 AS next_no FROM leasing.requirements WHERE work_item_id=%s", (work_item_id,))
                next_no = cur.fetchone()["next_no"]
                cur.execute("""INSERT INTO leasing.requirements
                    (work_item_id, requirement_no, order_type, si, area, address, gedung_kawasan, latitude, longitude,
                     a_end, z_end, bandwidth, bandwidth_unit, service_type, special_features,
                     existing_mrc_amount, existing_mrc_currency)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id, requirement_no""",
                    (work_item_id, next_no, values["order_type"], values["si"], values["area"], values["address"],
                     values["gedung_kawasan"], values["latitude"], values["longitude"], values["a_end"], values["z_end"], values["bandwidth"], values["bandwidth_unit"],
                     values["service_type"], values["special_features"], values["existing_mrc_amount"], values["existing_mrc_currency"]))
                created = dict(cur.fetchone())
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
    payload = request.get_json(silent=True) or {}
    allowed = {"status", "resolution_note", "order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end", "bandwidth", "bandwidth_unit", "service_type", "special_features", "existing_mrc_amount", "existing_mrc_currency"}
    changes = {k: payload[k] for k in allowed if k in payload}
    if not changes:
        return jsonify({"success": False, "message": "Tidak ada field yang diperbarui."}), 400
    if "status" in changes and changes["status"] not in LEASING_REQUIREMENT_STATUSES:
        return jsonify({"success": False, "message": "Status requirement tidak valid."}), 400
    detail_fields = {"order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end", "bandwidth", "bandwidth_unit", "service_type", "special_features", "existing_mrc_amount", "existing_mrc_currency"}
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM leasing.requirements WHERE id=%s FOR UPDATE", (requirement_id,))
                existing = cur.fetchone()
                if not existing:
                    return jsonify({"success": False, "message": "Requirement tidak ditemukan."}), 404
                if detail_fields.intersection(changes):
                    merged = {key: existing.get(key) for key in detail_fields}
                    merged.update({k: v for k, v in changes.items() if k in detail_fields})
                    changes.update(_leasing_validate_requirement_payload(merged, f"Requirement #{requirement_id}"))
                sets, vals = [], []
                for key, value in changes.items():
                    sets.append(f"{key}=%s")
                    vals.append(value)
                vals.append(requirement_id)
                cur.execute(f"UPDATE leasing.requirements SET {', '.join(sets)} WHERE id=%s", vals)
                leasing_activity(cur, existing["work_item_id"], "requirement_updated", "Requirement diperbarui", session["username"], {"requirement_id": requirement_id, **changes})
            conn.commit()
        return jsonify({"success": True})
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
    except psycopg2.Error:
        app.logger.exception("Leasing requirement update failed")
        return jsonify({"success": False, "message": "Gagal memperbarui requirement."}), 400


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
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                sql = """SELECT w.id AS work_item_db_id, w.request_id, c.customer_name, w.requester_name,
                    w.request_due_date, w.current_stage, w.case_status, w.buyer_owner_id, w.created_at,
                    r.requirement_no, r.order_type, r.si, r.area, r.address, r.gedung_kawasan,
                    r.latitude, r.longitude, r.a_end, r.z_end, r.bandwidth, r.bandwidth_unit,
                    r.service_type, r.special_features, r.status AS requirement_status,
                    r.existing_mrc_amount, r.existing_mrc_currency,
                    p.partner_name, o.response_status AS partner_response_status,
                    o.next_follow_up_at, po.offer_status, pol.feasibility_status, pol.mrc_amount AS offered_mrc,
                    pol.otc_amount AS offered_otc, pol.currency AS offer_currency
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
                    ORDER BY w.created_at DESC, w.id, r.requirement_no, p.partner_name, po.version_no DESC"""
                cur.execute(sql, (work_item_id, work_item_id, partner_id, partner_id,
                                  from_date, from_date, to_date, to_date))
                rows = [dict(row) for row in cur.fetchall()]
        wb = Workbook()
        ws = wb.active
        ws.title = "Leasing Report"
        headers = ["Work Item DB ID", "Request ID", "Customer", "Requester", "Due Date", "Stage", "Case Status", "Buyer Username",
            "Requirement No", "Jenis Order", "SI", "Area", "Alamat", "Gedung/Kawasan", "Latitude", "Longitude", "A End", "Z End",
            "Bandwidth", "Satuan", "Jasa", "Fitur Khusus", "Requirement Status", "MRC Eksisting", "Currency MRC Eksisting",
            "Partner", "Partner Response", "Next Follow-up", "Offer Status", "Feasibility", "MRC Offer", "OTC Offer", "Currency Offer"]
        ws.append(headers)
        def safe_excel_value(value):
            # Use the shared sanitizer: it also catches formula-like values preceded by whitespace.
            return _leasing_excel_safe(value)
        for row in rows:
            vals = [row.get(k) for k in ["work_item_db_id", "request_id", "customer_name", "requester_name", "request_due_date", "current_stage", "case_status", "buyer_owner_id",
                "requirement_no", "order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end", "bandwidth", "bandwidth_unit",
                "service_type", "special_features", "requirement_status", "existing_mrc_amount", "existing_mrc_currency", "partner_name", "partner_response_status", "next_follow_up_at", "offer_status", "feasibility_status", "offered_mrc", "offered_otc", "offer_currency"]]
            ws.append([safe_excel_value(v.isoformat() if hasattr(v, "isoformat") else v) for v in vals])
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        ws.row_dimensions[1].height = 30
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="35266E")
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for col in ws.columns:
            letter = col[0].column_letter
            max_len = min(36, max(12, max(len(str(c.value or "")) for c in col[:200])))
            ws.column_dimensions[letter].width = max_len
        output = BytesIO(); wb.save(output); output.seek(0)
        suffix = f"_work_item_{work_item_id}" if work_item_id else (f"_partner_{partner_id}" if partner_id else "")
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True,
                         download_name=f"leasing_report{suffix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")
    except Exception:
        app.logger.exception("Leasing Excel export failed")
        return jsonify({"success": False, "message": "Export Excel gagal. Periksa log aplikasi."}), 500


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
                                  source_label=None):
    """Create a current offer snapshot while carrying forward untouched requirement lines.

    A partner may return prices for 10 of 100 sites today and the remaining sites later.
    Treating each spreadsheet as a full replacement would silently erase those earlier prices.
    This creates an immutable version, overlays changed lines, and copies forward untouched
    lines so the current comparison remains complete while the history stays auditable.
    """
    cur.execute("SELECT id, work_item_id FROM leasing.partner_outreaches WHERE id=%s FOR UPDATE", (outreach_id,))
    outreach = cur.fetchone()
    if not outreach:
        raise LookupError("Outreach tidak ditemukan.")

    cur.execute("SELECT requirement_id FROM leasing.outreach_requirements WHERE outreach_id=%s", (outreach_id,))
    allowed_ids = {int(row["requirement_id"]) for row in cur.fetchall()}
    if not allowed_ids:
        raise ValueError("Outreach ini belum memiliki requirement yang dikirim.")

    incoming = {}
    for line in incoming_lines:
        req_id = int(line["requirement_id"])
        if req_id in incoming:
            raise ValueError(f"Requirement ID {req_id} muncul lebih dari sekali.")
        if req_id not in allowed_ids:
            raise ValueError(f"Requirement ID {req_id} bukan bagian dari outreach ini.")
        normalized = dict(line)
        normalized["requirement_id"] = req_id
        if normalized.get("feasibility_status") == "pending" and (normalized.get("mrc_amount") is not None or normalized.get("otc_amount") is not None):
            raise ValueError(f"Requirement ID {req_id}: pilih Can Provide sebelum memasukkan harga.")
        incoming[req_id] = normalized
    if not incoming:
        raise ValueError("Tidak ada baris respons partner yang dapat disimpan.")

    cur.execute("""SELECT id, version_no, notes, valid_until FROM leasing.partner_offers
        WHERE outreach_id=%s AND offer_status='current' ORDER BY version_no DESC LIMIT 1 FOR UPDATE""", (outreach_id,))
    previous_offer = cur.fetchone()
    merged = {}
    cur.execute("""SELECT pol.requirement_id, pol.feasibility_status, pol.mrc_amount, pol.otc_amount,
        pol.currency, pol.notes, po.version_no
        FROM leasing.partner_offer_lines pol JOIN leasing.partner_offers po ON po.id=pol.offer_id
        WHERE po.outreach_id=%s AND po.offer_status='current'
        ORDER BY po.version_no DESC, pol.requirement_id""", (outreach_id,))
    for old_line in cur.fetchall():
        req_id = int(old_line["requirement_id"])
        if req_id not in merged:
            merged[req_id] = {k: old_line[k] for k in ("requirement_id", "feasibility_status", "mrc_amount", "otc_amount", "currency", "notes")}
    # Safer spreadsheet semantics: a status/note-only update must not silently erase a
    # quote already on file. If at least one price is provided, that row is a full price
    # revision (blank counterpart price is intentionally cleared). To withdraw a quote,
    # explicitly choose cannot_provide; that status clears any previous prices.
    for req_id, new_line in incoming.items():
        old_line = merged.get(req_id)
        if (old_line and new_line.get("feasibility_status") in {"can_provide", "needs_clarification"}
                and new_line.get("mrc_amount") is None and new_line.get("otc_amount") is None):
            for field in ("mrc_amount", "otc_amount", "currency"):
                if new_line.get(field) in (None, ""):
                    new_line[field] = old_line.get(field)
    retained_line_count = sum(1 for req_id in merged if req_id not in incoming)
    merged.update(incoming)

    cur.execute("SELECT COALESCE(MAX(version_no),0)+1 AS v FROM leasing.partner_offers WHERE outreach_id=%s", (outreach_id,))
    version = int(cur.fetchone()["v"])
    cur.execute("UPDATE leasing.partner_offers SET offer_status='superseded' WHERE outreach_id=%s AND offer_status='current'", (outreach_id,))
    effective_notes = str(offer_notes).strip() if offer_notes is not None and str(offer_notes).strip() else (previous_offer["notes"] if previous_offer else None)
    effective_valid_until = valid_until if valid_until not in (None, "") else (previous_offer["valid_until"] if previous_offer else None)
    cur.execute("""INSERT INTO leasing.partner_offers
        (outreach_id, version_no, received_at, valid_until, notes, created_by)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
        (outreach_id, version, received_at or datetime.now(), effective_valid_until, effective_notes, username))
    offer_id = cur.fetchone()["id"]
    for req_id in sorted(merged):
        line = merged[req_id]
        cur.execute("""INSERT INTO leasing.partner_offer_lines
            (offer_id, requirement_id, feasibility_status, mrc_amount, otc_amount, currency, notes)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (offer_id, req_id, line.get("feasibility_status") or "pending", line.get("mrc_amount"),
             line.get("otc_amount"), line.get("currency"), line.get("notes")))

    # Reflect the latest current snapshot on the requirement-level coverage matrix.
    cur.execute("UPDATE leasing.outreach_requirements SET response_status='awaiting_response', response_note=NULL WHERE outreach_id=%s", (outreach_id,))
    response_map = {
        "pending": "awaiting_response",
        "can_provide": "can_provide",
        "cannot_provide": "cannot_provide",
        "needs_clarification": "needs_clarification",
    }
    for req_id, line in merged.items():
        cur.execute("""UPDATE leasing.outreach_requirements SET response_status=%s, response_note=%s
            WHERE outreach_id=%s AND requirement_id=%s""",
            (response_map.get(line.get("feasibility_status"), "awaiting_response"), line.get("notes"), outreach_id, req_id))

    responded_count = sum(1 for line in merged.values() if line.get("feasibility_status") not in (None, "pending"))
    complete_count = sum(1 for line in merged.values() if (
        line.get("feasibility_status") == "cannot_provide" or
        (line.get("feasibility_status") == "can_provide" and
         (line.get("mrc_amount") is not None or line.get("otc_amount") is not None))))
    total_count = len(allowed_ids)
    if complete_count >= total_count and len(merged) >= total_count:
        response_status = "responded"
    elif responded_count:
        response_status = "partial_response"
    else:
        response_status = "awaiting_response"
    now = datetime.now()
    cur.execute("""UPDATE leasing.partner_outreaches
        SET response_status=%s,
            responded_at=CASE WHEN %s THEN %s ELSE responded_at END,
            next_follow_up_at=CASE WHEN %s THEN NULL ELSE next_follow_up_at END
        WHERE id=%s""",
        (response_status, responded_count > 0, now, response_status == "responded", outreach_id))
    leasing_activity(cur, outreach["work_item_id"], "partner_offer_recorded", "Penawaran partner diperbarui",
        username, {"offer_id": offer_id, "version_no": version, "source": source,
                   "imported_line_count": len(incoming), "current_line_count": len(merged),
                   "retained_line_count": retained_line_count, "response_status": response_status,
                   "source_label": source_label})
    return {"offer_id": offer_id, "version_no": version, "line_count": len(incoming),
            "current_line_count": len(merged), "retained_line_count": retained_line_count,
            "response_status": response_status}


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
                cur.execute("""SELECT r.id AS requirement_id, r.requirement_no, r.area, r.address,
                    r.gedung_kawasan, r.latitude, r.longitude, r.si, r.a_end, r.z_end,
                    r.bandwidth, r.bandwidth_unit, r.service_type
                    FROM leasing.outreach_requirements oro
                    JOIN leasing.requirements r ON r.id=oro.requirement_id
                    WHERE oro.outreach_id=%s ORDER BY r.requirement_no""", (outreach_id,))
                requirements = [dict(x) for x in cur.fetchall()]
        if not requirements:
            return jsonify({"success": False, "message": "Outreach ini belum memiliki requirement terkait. Catat ulang outreach dengan memilih lokasi yang dikirim."}), 409
        wb = Workbook()
        ws = wb.active
        ws.title = "Offer Input"
        headers = ["Requirement ID", "Requirement No", "Area", "Address", "Building / Complex", "Latitude", "Longitude", "SI", "A-End", "Z-End", "Bandwidth", "Unit", "Service", "Feasibility Status", "MRC", "OTC", "Currency", "Notes"]
        ws.append(headers)
        for row in requirements:
            ws.append([_leasing_excel_safe(row.get(k)) for k in ["requirement_id", "requirement_no", "area", "address", "gedung_kawasan", "latitude", "longitude", "si", "a_end", "z_end", "bandwidth", "bandwidth_unit", "service_type"]] + [None, None, None, "IDR", None])
        _leasing_style_report_sheet(ws)
        # Response columns N:R are editable; requirement identifiers and site details remain intact.
        for cell in ws[1][13:18]:
            cell.fill = PatternFill("solid", fgColor="16765B")
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"
        ws.column_dimensions["D"].width = 34
        ws.column_dimensions["E"].width = 24
        ws.column_dimensions["F"].width = 13
        ws.column_dimensions["G"].width = 13
        ws.column_dimensions["N"].width = 22
        ws.column_dimensions["R"].width = 34
        if requirements:
            last_row = len(requirements) + 1
            dv = DataValidation(type="list", formula1='"pending,can_provide,cannot_provide,needs_clarification"', allow_blank=True)
            dv.add(f"N2:N{last_row}")
            ws.add_data_validation(dv)
            price_validation = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0", allow_blank=True)
            price_validation.error = "Harga harus berupa angka nol atau lebih."
            price_validation.errorTitle = "Harga tidak valid"
            price_validation.showErrorMessage = True
            price_validation.add(f"O2:P{last_row}")
            ws.add_data_validation(price_validation)
            for row_idx in range(2, last_row + 1):
                ws[f"O{row_idx}"].number_format = '#,##0.00'
                ws[f"P{row_idx}"].number_format = '#,##0.00'
        guide = wb.create_sheet("Instructions")
        guide.append(["Partner offer template", "Instructions"])
        guide.append(["Work Item", outreach["request_id"]])
        guide.append(["Customer", outreach["customer_name"]])
        guide.append(["Partner", outreach["partner_name"]])
        guide.append(["Outreach round", outreach["outreach_round"]])
        guide.append(["How to use", "Edit columns N:R only. Keep Requirement ID, Requirement No, coordinates, and other site detail columns unchanged. Leave sites without a new response blank. Import creates a new version and carries forward existing prices for unchanged sites. For an existing quote, a status/note-only update with both price cells blank preserves the prior prices; entering either price makes the row a full price revision (the other blank price is cleared). Use cannot_provide to withdraw a quote and explicitly mark a site unserviceable; deleting a previously quoted row does not withdraw its quote."])
        guide.append(["Feasibility Status", "Use: pending, can_provide, cannot_provide, needs_clarification"])
        guide.append(["Currency", "Use a three-letter currency code such as IDR, USD, or SGD when MRC/OTC is entered."])
        guide.column_dimensions["A"].width = 22
        guide.column_dimensions["B"].width = 105
        for cell in guide[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="24345B")
        guide.freeze_panes = "A2"
        guide.row_dimensions[6].height = 88
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
            except ValueError as exc:
                row_issues.append(str(exc))
                continue
            notes = str(cell(row, "notes") or "").strip() or None
            # A template row has a system ID even when the partner did not respond.
            # Ignore untouched rows instead of recording 100 empty/pending pseudo-responses.
            has_response_value = bool(raw_feasibility) or mrc is not None or otc is not None or bool(notes)
            if not has_response_value:
                continue
            if raw_feasibility == "pending" and mrc is None and otc is None and not notes:
                continue
            if not raw_feasibility:
                raw_feasibility = "can_provide" if (mrc is not None or otc is not None) else "needs_clarification"
            if raw_feasibility == "pending" and (mrc is not None or otc is not None):
                row_issues.append(f"Baris {excel_row_no}: pilih can_provide sebelum memasukkan MRC/OTC.")
                continue
            if raw_feasibility == "cannot_provide" and (mrc is not None or otc is not None):
                row_issues.append(f"Baris {excel_row_no}: harga tidak boleh diisi jika status cannot_provide.")
                continue
            currency = str(cell(row, "currency") or "").strip().upper()
            if mrc is not None or otc is not None:
                if not re.fullmatch(r"[A-Z]{3}", currency):
                    row_issues.append(f"Baris {excel_row_no}: Currency wajib kode 3 huruf jika MRC/OTC diisi.")
                    continue
            else:
                currency = None
            parsed_lines.append({"requirement_id": req_id, "feasibility_status": raw_feasibility,
                                 "mrc_amount": mrc, "otc_amount": otc, "currency": currency, "notes": notes})
        wb.close()
        if row_issues:
            return jsonify({"success": False, "message": "Template penawaran belum valid; data belum disimpan.", "issues": row_issues[:100]}), 400
        if not parsed_lines:
            raise ValueError("Tidak ada baris penawaran yang bisa diimpor.")
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                result = _leasing_record_offer_version(
                    cur, outreach_id, parsed_lines, session["username"], "xlsx_import",
                    received_at=datetime.now(), source_label=secure_filename(file_obj.filename or "offer.xlsx"))
            conn.commit()
        return jsonify({"success": True, **result,
                        "message": f"Respons {result['line_count']} lokasi diimpor ke versi {result['version_no']}; snapshot aktif memuat {result['current_line_count']} lokasi, termasuk {result['retained_line_count']} baris lama yang dibawa otomatis."}), 201
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
    """Auditable multi-sheet report for one Work Item; one row per site/event, never one card per site."""
    try:
        with get_leasing_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""SELECT w.id, w.request_id, w.requester_name, w.requester_division, w.request_due_date,
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
                    "Requirements": ("""SELECT id AS requirement_id, requirement_no, status, order_type, si, area, address, gedung_kawasan,
                        latitude, longitude, a_end, z_end, bandwidth, bandwidth_unit, service_type, special_features,
                        existing_mrc_amount, existing_mrc_currency, resolution_note, created_at
                        FROM leasing.requirements WHERE work_item_id=%s ORDER BY requirement_no""", (work_item_id,)),
                    "Partner Activity": ("""SELECT o.id AS outreach_id, p.partner_name, o.outreach_round, o.sent_at,
                        o.response_status, o.responded_at, o.next_follow_up_at, o.follow_up_owner_id, o.created_by, o.notes,
                        (SELECT COUNT(*) FROM leasing.outreach_requirements oro WHERE oro.outreach_id=o.id) AS locations_sent,
                        (SELECT COUNT(DISTINCT pol.requirement_id) FROM leasing.partner_offer_lines pol
                         JOIN leasing.partner_offers po ON po.id=pol.offer_id WHERE po.outreach_id=o.id AND po.offer_status='current'
                           AND pol.feasibility_status <> 'pending') AS locations_responded,
                        (SELECT COUNT(DISTINCT pol.requirement_id) FROM leasing.partner_offer_lines pol
                         JOIN leasing.partner_offers po ON po.id=pol.offer_id WHERE po.outreach_id=o.id AND po.offer_status='current'
                           AND (pol.mrc_amount IS NOT NULL OR pol.otc_amount IS NOT NULL)) AS locations_quoted,
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
                        r.address, r.gedung_kawasan, r.a_end, r.z_end, r.bandwidth, r.bandwidth_unit
                        FROM leasing.outreach_requirements oro JOIN leasing.partner_outreaches o ON o.id=oro.outreach_id
                        JOIN leasing.partners p ON p.id=o.partner_id JOIN leasing.requirements r ON r.id=oro.requirement_id
                        LEFT JOIN LATERAL (SELECT pol.feasibility_status, pol.notes
                            FROM leasing.partner_offers po JOIN leasing.partner_offer_lines pol ON pol.offer_id=po.id
                            WHERE po.outreach_id=o.id AND po.offer_status='current' AND pol.requirement_id=oro.requirement_id
                            ORDER BY po.version_no DESC LIMIT 1) current_line ON TRUE
                        WHERE o.work_item_id=%s ORDER BY p.partner_name, o.outreach_round, r.requirement_no""", (work_item_id,)),
                    "Commercial Comparison": ("""SELECT pol.id AS offer_line_id, pol.requirement_id, p.partner_name, o.outreach_round, po.version_no, po.offer_status, po.received_at,
                        po.valid_until, r.requirement_no, r.order_type, r.si, r.area, r.address, r.gedung_kawasan,
                        r.a_end, r.z_end, r.bandwidth, r.bandwidth_unit, r.service_type, pol.feasibility_status,
                        pol.mrc_amount, pol.otc_amount, pol.currency, pol.notes AS line_notes, po.notes AS offer_notes,
                        ne.event_type AS latest_negotiation_event, ne.mrc_amount AS latest_negotiated_mrc,
                        ne.otc_amount AS latest_negotiated_otc, ne.currency AS latest_negotiated_currency,
                        ne.occurred_at AS latest_negotiation_at, ne.notes AS latest_negotiation_notes
                        FROM leasing.partner_offer_lines pol JOIN leasing.partner_offers po ON po.id=pol.offer_id
                        JOIN leasing.partner_outreaches o ON o.id=po.outreach_id JOIN leasing.partners p ON p.id=o.partner_id
                        JOIN leasing.requirements r ON r.id=pol.requirement_id
                        LEFT JOIN LATERAL (SELECT n.* FROM leasing.negotiation_events n WHERE n.offer_line_id=pol.id
                                           ORDER BY n.occurred_at DESC LIMIT 1) ne ON TRUE
                        WHERE o.work_item_id=%s ORDER BY r.requirement_no, p.partner_name, po.version_no DESC""", (work_item_id,)),
                    "Activity Log": ("""SELECT occurred_at, event_type, event_summary, actor_id, metadata
                        FROM leasing.activity_events WHERE work_item_id=%s ORDER BY occurred_at""", (work_item_id,)),
                    "Results Sent": ("""SELECT rs.submission_no, rs.submission_status, rs.channel, rs.recipient_name, rs.recipient_email,
                        rs.sent_at, rs.created_at, rs.created_by, rs.notes, rsl.requirement_id, r.requirement_no,
                        r.area, r.address, r.gedung_kawasan, p.partner_name, pol.mrc_amount, pol.otc_amount, pol.currency,
                        rsl.result_note
                        FROM leasing.result_submissions rs LEFT JOIN leasing.result_submission_lines rsl ON rsl.submission_id=rs.id
                        LEFT JOIN leasing.requirements r ON r.id=rsl.requirement_id
                        LEFT JOIN leasing.partner_offer_lines pol ON pol.id=rsl.offer_line_id
                        LEFT JOIN leasing.partner_offers po ON po.id=pol.offer_id
                        LEFT JOIN leasing.partner_outreaches o ON o.id=po.outreach_id
                        LEFT JOIN leasing.partners p ON p.id=o.partner_id
                        WHERE rs.work_item_id=%s ORDER BY rs.submission_no, r.requirement_no""", (work_item_id,)),
                    "Commercial Targets": ("""SELECT ct.metric, ct.target_amount, ct.currency, ct.target_source, ct.notes,
                        ct.requirement_id, r.requirement_no, r.area, r.address, ct.created_at, ct.created_by
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
    "request_id": {"request_id", "request id", "work_item_id", "work item id", "work_item", "work item", "ticket_id", "ticket id", "id request", "id_request"},
    "customer_name": {"customer", "customer_name", "customer name", "pelanggan", "customer/pelanggan", "customer_pelanggan"},
    "requester_name": {"requester", "requester_name", "requester name", "nama requester", "pemohon"},
    "request_due_date": {"request_due_date", "request due date", "due date", "due_date", "due date submit", "due date requester", "target submit"},
    "notes": {"notes", "catatan", "catatan request", "feedback sales"},
    "order_type": {"order_type", "order type", "jenis order", "jenis_order"},
    "si": {"si", "nomor si", "no si", "si number", "service id"},
    "area": {"area", "wilayah", "regional area"},
    "address": {"address", "alamat", "alamat site", "site address"},
    "latitude": {"latitude", "lat", "lintang"},
    "longitude": {"longitude", "long", "lng", "bujur"},
    "gedung_kawasan": {"gedung_kawasan", "gedung kawasan", "gedung/kawasan", "gedung", "kawasan", "building"},
    "a_end": {"a_end", "a end", "a-end", "aend"},
    "z_end": {"z_end", "z end", "z-end", "zend"},
    "bandwidth": {"bandwidth", "bw", "bandwidth value"},
    "bandwidth_unit": {"bandwidth_unit", "bandwidth unit", "satuan bandwidth", "satuan (default mbps)", "satuan", "unit"},
    "service_type": {"service_type", "service type", "jenis layanan", "jasa", "service", "product"},
    "special_features": {"special_features", "special features", "fitur khusus", "special requirement", "fitur"},
    "existing_mrc_amount": {"existing_mrc_amount", "existing mrc", "mrc eksisting", "mrc existing", "mrc berjalan"},
    "existing_mrc_currency": {"existing_mrc_currency", "existing mrc currency", "currency mrc eksisting", "mata uang mrc eksisting"},
}
LEASING_IMPORT_SUPPORTED_HEADERS = set().union(*LEASING_IMPORT_ALIASES.values())


def _leasing_header_key(value):
    value = unicodedata.normalize("NFKD", str(value or "").replace("\ufeff", ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch)).strip().lower()
    return re.sub(r"[^a-z0-9]+", "_", value).strip("_")


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
    if request.files.get("file"):
        file_obj = request.files["file"]
        filename = secure_filename(file_obj.filename or "")
        suffix = os.path.splitext(filename)[1].lower()
        content = file_obj.read()
        if not filename or not content:
            raise ValueError("File import kosong atau tidak memiliki nama.")
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
    return raw_rows, source_headers, source_name


def _leasing_is_psb(value):
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    normalized = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized.lower()).strip()
    return normalized in {"psb", "pasang baru", "pasang baru psb"}


def _leasing_validate_requirement_payload(payload, label="Requirement"):
    data = {key: _leasing_cell_value(payload.get(key)) for key in (
        "order_type", "si", "area", "address", "gedung_kawasan", "latitude", "longitude", "a_end", "z_end",
        "bandwidth", "bandwidth_unit", "service_type", "special_features", "existing_mrc_amount", "existing_mrc_currency"
    )}
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
    if data.get("existing_mrc_amount") not in (None, ""):
        try: mrc = float(str(data["existing_mrc_amount"]).replace(",", "."))
        except (TypeError, ValueError): raise ValueError(f"{label}: MRC Eksisting harus berupa angka nol atau lebih besar.")
        if not math.isfinite(mrc) or mrc < 0: raise ValueError(f"{label}: MRC Eksisting harus berupa angka nol atau lebih besar.")
        data["existing_mrc_amount"] = mrc
        currency = str(data.get("existing_mrc_currency") or "IDR").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency): raise ValueError(f"{label}: Currency MRC harus berupa kode 3 huruf.")
        data["existing_mrc_currency"] = currency
    else:
        data["existing_mrc_amount"] = None
        data["existing_mrc_currency"] = None
    return data


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
            obj["request_due_date"] = _leasing_parse_date(obj.get("request_due_date"), "Due date", row_idx)
            obj["bandwidth"] = _leasing_parse_number(obj.get("bandwidth"), "Bandwidth", row_idx)
            obj["existing_mrc_amount"] = _leasing_parse_number(obj.get("existing_mrc_amount"), "MRC eksisting", row_idx)
            if obj.get("request_id"): obj["request_id"] = str(obj["request_id"]).strip()
            obj.update(_leasing_validate_requirement_payload(obj, f"Baris {row_idx}"))
            normalized.append(obj)
        except ValueError as exc:
            issues.append(str(exc))
    return normalized, mapped_headers, unmapped_headers, issues


def _leasing_import_groups(rows):
    """Legacy grouping: identical non-empty Request ID values group rows; blank IDs each form a separate Work Item."""
    if not rows: return [], ["Tidak ada baris data requirement untuk diimport."]
    issues, groups, by_request_id = [], [], {}
    for row in rows:
        rid = str(row.get("request_id") or "").strip()
        if rid:
            if rid not in by_request_id:
                group = {"request_id": rid, "rows": [], "customer_name": None, "requester_name": None}
                by_request_id[rid] = group
                groups.append(group)
            group = by_request_id[rid]
        else:
            group = {"request_id": None, "rows": [], "customer_name": None, "requester_name": None}
            groups.append(group)
        group["rows"].append(row)
    request_fields = (("customer_name", "Customer"), ("requester_name", "Requester"), ("request_due_date", "Due Date"), ("notes", "Notes"))
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
        if not group["customer_name"]: issues.append(f"Customer wajib diisi untuk Work Item dari baris {rows_in_group[0]['_row_no']}.")
        if not group["requester_name"]: issues.append(f"Requester wajib diisi untuk Work Item dari baris {rows_in_group[0]['_row_no']}.")
    return groups, issues


def _leasing_import_preview_data():
    raw_rows, source_headers, source_name = _leasing_read_import_source()
    if not raw_rows:
        raise ValueError("Tidak ada baris data untuk diimport.")
    normalized, mapped_headers, unmapped_headers, issues = _leasing_normalize_import_rows(raw_rows, source_headers)
    groups, group_issues = _leasing_import_groups(normalized)
    issues.extend(group_issues)
    request_ids = [g["request_id"] for g in groups if g.get("request_id")]
    existing_ids = set()
    if request_ids and not issues:
        with get_leasing_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT request_id FROM leasing.work_items WHERE request_id = ANY(%s)", (request_ids,))
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
    return {"source_name": source_name, "source_headers": source_headers, "rows": normalized, "groups": groups,
            "mapped_headers": mapped_headers, "unmapped_headers": unmapped_headers, "issues": issues,
            "warnings": warnings, "existing_ids": existing_ids}


def _leasing_import_response_preview(data):
    rows = data["rows"]
    return {"success": True, "source_name": data["source_name"], "source_headers": data["source_headers"],
            "mapped_columns": data["mapped_headers"], "unmapped_columns": data["unmapped_headers"],
            "row_count": len(rows), "work_item_count": len(data["groups"]),
            "requirement_count": len(rows), "issues": data["issues"], "warnings": data["warnings"],
            "sample_rows": [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows[:8]],
            "grouping_rule": "Baris dengan Request ID sama digabung menjadi satu Work Item; baris dengan Request ID kosong masing-masing menjadi Work Item terpisah. Customer, Requester, Due Date, dan Notes harus konsisten dalam tiap grup."}


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
        # Older clients may not send buyer_owner_id; preserve the historical self-assign behavior.
        # The current UI sends a selected owner explicitly for each import batch.
        owner_payload = request.form if request.form else (request.get_json(silent=True) or {})
        if "buyer_owner_id" in owner_payload:
            default_owner = str(owner_payload.get("buyer_owner_id") or "").strip()
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
                    customer_name = str(group["customer_name"] or "").strip()
                    requester_name = str(group["requester_name"] or "").strip()
                    request_id = group["request_id"] or ("LEA-" + datetime.now().strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:8].upper())
                    cur.execute("SELECT id FROM leasing.customers WHERE lower(customer_name)=lower(%s) ORDER BY id LIMIT 1", (customer_name,))
                    customer = cur.fetchone()
                    if not customer:
                        cur.execute("INSERT INTO leasing.customers (customer_name) VALUES (%s) RETURNING id", (customer_name,))
                        customer = cur.fetchone()
                    cur.execute("""INSERT INTO leasing.work_items
                        (request_id, customer_id, requester_name, request_due_date, buyer_owner_id, notes, created_by)
                        VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (request_id, customer["id"], requester_name, first.get("request_due_date"), default_owner, first.get("notes"), username))
                    work_id = cur.fetchone()["id"]
                    created_ids.append({"id": work_id, "request_id": request_id, "requirement_count": len(group_rows)})
                    for idx, row in enumerate(group_rows, start=1):
                        fields = _leasing_validate_requirement_payload(row, f"Baris {row['_row_no']}")
                        cur.execute("""INSERT INTO leasing.requirements
                            (work_item_id, requirement_no, order_type, si, area, address, gedung_kawasan, latitude, longitude,
                             a_end, z_end, bandwidth, bandwidth_unit, service_type, special_features,
                             existing_mrc_amount, existing_mrc_currency)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                            (work_id, idx, fields["order_type"], fields["si"], fields["area"], fields["address"], fields["gedung_kawasan"], fields["latitude"], fields["longitude"], fields["a_end"], fields["z_end"], fields["bandwidth"], fields["bandwidth_unit"], fields["service_type"], fields["special_features"], fields["existing_mrc_amount"], fields["existing_mrc_currency"]))
                    leasing_activity(cur, work_id, "work_item_imported", f"Work Item diimpor dari {data['source_name']}", username,
                        {"request_id": request_id, "source_row_numbers": [r["_row_no"] for r in group_rows], "requirement_count": len(group_rows), "import_mode": "request_id_grouping"})
            conn.commit()
        return jsonify({"success": True, "message": f"Import berhasil: {len(created_ids)} Work Item, {len(rows)} requirement.",
                        "work_item_count": len(created_ids), "requirement_count": len(rows), "created_work_items": created_ids,
                        "warnings": data["warnings"]}), 201
    except ValueError as exc:
        return jsonify({"success": False, "message": str(exc)}), 400
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