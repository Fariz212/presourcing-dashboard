from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file, send_from_directory
from flask_cors import CORS
from openpyxl import load_workbook, Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from copy import copy
import pandas as pd
import sqlite3
import json
import os
import io
import uuid
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
DB_NAME = "presourcing_db.sqlite"

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
    if value is None: return ""
    try:
        if pd.isna(value): return ""
    except (TypeError, ValueError): pass
    if isinstance(value, pd.Timestamp): return value.strftime("%Y-%m-%d")
    if isinstance(value, float) and value.is_integer(): return str(int(value))
    return str(value).strip()

def _excel_qty(value, default=0):
    text = _excel_text(value)
    if text == "": return default
    try: number = float(value)
    except (TypeError, ValueError): raise ValueError("Qty harus berupa angka.")
    if number < 0: raise ValueError("Qty tidak boleh negatif.")
    return number

def optional_number(value):
    """
    Blank -> None
    Valid number -> float
    Invalid -> ValueError
    """
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

    # Membersihkan spasi tak terputus (\xa0) atau spasi tersembunyi dari Excel
    cleaned_text = text.replace("\xa0", "").replace(" ", "").replace(",", ".")

    try:
        number = float(cleaned_text)
    except (TypeError, ValueError):
        raise ValueError(f"Nilai harga harus berupa angka (diterima: '{text}').")

    if number < 0:
        raise ValueError("Harga tidak boleh negatif.")

    return number

def calculate_sph_total(qty, unit_price):
    if qty is None or unit_price is None: return None
    try:
        qty = float(qty)
        unit_price = float(unit_price)
    except (TypeError, ValueError): return None
    return qty * unit_price

def derive_unit_price(qty, total):
    if qty is None or total is None: return None
    try:
        qty = float(qty)
        total = float(total)
    except (TypeError, ValueError): return None
    if qty <= 0: return None
    return total / qty

def resolve_sph_values(qty, unit_price, legacy_total=None):
    unit_price = optional_number(unit_price)
    if unit_price is not None:
        return (unit_price, calculate_sph_total(qty, unit_price))
    return (None, optional_number(legacy_total))

def _read_boq_excel(file, require_system_id=False):
    """
    Membaca Sheet 1 / index 0 dengan deteksi baris header otomatis 
    untuk melewati teks judul/instruksi di bagian atas template.
    """
    file.stream.seek(0)
    
    # Baca file mentah tanpa header untuk mencari baris header tabel secara dinamis
    df_raw = pd.read_excel(file, sheet_name=0, header=None)
    
    header_row_idx = 0
    for idx, row in df_raw.iterrows():
        row_str_values = [str(val).strip() for val in row.values]
        if "Deskripsi Item" in row_str_values or "Item No" in row_str_values:
            header_row_idx = idx
            break

    # Baca ulang file Excel menggunakan baris header yang tepat
    file.stream.seek(0)
    df = pd.read_excel(file, sheet_name=0, header=header_row_idx)

    # Normalisasi nama kolom
    df.columns = [_excel_text(col) for col in df.columns]

    required_columns = BOQ_CORE_COLUMNS + BOQ_DERIVED_COLUMNS

    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise ValueError(
            "Format template tidak sesuai. Kolom wajib tidak ditemukan: "
            + ", ".join(missing)
        )

    if require_system_id and BOQ_SYSTEM_COLUMN not in df.columns:
        raise ValueError(f"Kolom '{BOQ_SYSTEM_COLUMN}' wajib ada untuk file revisi.")

    if BOQ_SYSTEM_COLUMN not in df.columns:
        df[BOQ_SYSTEM_COLUMN] = ""

    for col in BOQ_OPTIONAL_COLUMNS:
        if col not in df.columns: df[col] = ""

    for col in BOQ_DERIVED_COLUMNS:
        if col not in df.columns: df[col] = ""

    return df.fillna("")

def _parse_boq_rows(df):
    rows = []
    issues = []
    seen_ids = {}

    for excel_idx, row in df.iterrows():
        excel_row = excel_idx + 2
        description = _excel_text(row.get("Deskripsi Item"))
        
        if not description: continue # Skip baris kosong

        item_id = _excel_text(row.get(BOQ_SYSTEM_COLUMN))
        if item_id:
            if item_id in seen_ids:
                issues.append({"row": excel_row, "severity": "error", "message": f"Item ID duplikat dengan row {seen_ids[item_id]}."})
            else:
                seen_ids[item_id] = excel_row

        qty_raw = row.get("Qty", "")
        qty = 0
        if _excel_text(qty_raw):
            try: qty = _excel_qty(qty_raw)
            except ValueError as exc: issues.append({"row": excel_row, "severity": "error", "message": str(exc)})
        else:
            issues.append({"row": excel_row, "severity": "warning", "message": "Qty kosong; sistem menyimpan Qty = 0."})

        uom = _excel_text(row.get("UoM"))
        if not uom: issues.append({"row": excel_row, "severity": "warning", "message": "UoM kosong."})

        # Parsing Prices Cleanly
        sph_awal_unit = None
        sph_final_unit = None

        try: sph_awal_unit = optional_number(row.get("SPH Awal / Unit"))
        except ValueError as exc: issues.append({"row": excel_row, "severity": "error", "message": f"SPH Awal / Unit: {exc}"})

        try: sph_final_unit = optional_number(row.get("SPH Final / Unit"))
        except ValueError as exc: issues.append({"row": excel_row, "severity": "error", "message": f"SPH Final / Unit: {exc}"})

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
        if not item["itemNo"]: item["itemNo"] = str(idx)

    return rows, issues

# ============================================================================
# PAGE ROUTES
# ============================================================================
@app.route("/")
def index():
    if "username" not in session or session.get("role") != "admin":
        return redirect(url_for("login_page"))
    return render_template("presourcing-dashboard.html")

@app.route("/login")
def login_page():
    if "username" in session:
        return redirect(url_for("index") if session.get("role") == "admin" else url_for("sa_portal"))
    return render_template("login.html")

@app.route("/portal")
def sa_portal():
    if "username" not in session: return redirect(url_for("login_page"))
    return render_template("sa-portal.html")

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================
def init_db():
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute("""CREATE TABLE IF NOT EXISTS dashboard_state (id INTEGER PRIMARY KEY, data_type TEXT UNIQUE, json_data TEXT)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, full_name TEXT NOT NULL, department TEXT, role TEXT NOT NULL)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT UNIQUE NOT NULL, title TEXT NOT NULL, client_name TEXT, competitor_info TEXT, sla_date TEXT NOT NULL, notes TEXT, status TEXT DEFAULT 'unassigned', requester_username TEXT NOT NULL, pic_username TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS request_items (id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, sow_name TEXT DEFAULT 'General Scope', boq_section TEXT DEFAULT 'General Items', item_no TEXT, description TEXT NOT NULL, preferred_brand TEXT, quantity REAL, uom TEXT, delivery_time TEXT, vendor TEXT, sph_awal_unit REAL, sph_final_unit REAL, FOREIGN KEY (ticket_id) REFERENCES requests(ticket_id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, target_user TEXT NOT NULL, message TEXT NOT NULL, is_read INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT, requestor_name TEXT, requestor_dept TEXT, priority TEXT, status TEXT, lead_id TEXT, sph_mode TEXT, project_sph_awal REAL, project_sph_final REAL, created_at TEXT, closed_at TEXT, target_rfs TEXT, pipeline_stage TEXT, progress_pct INTEGER)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS sows (id TEXT PRIMARY KEY, project_id TEXT, name TEXT, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS boqs (id TEXT PRIMARY KEY, sow_id TEXT, name TEXT, FOREIGN KEY(sow_id) REFERENCES sows(id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, boq_id TEXT, product TEXT, qty REAL, uom TEXT, vendor TEXT, sph_awal REAL, sph_final REAL, notes TEXT, pic_ids TEXT, item_no TEXT, preferred_brand TEXT, delivery_time TEXT, sph_awal_unit REAL, sph_final_unit REAL, FOREIGN KEY(boq_id) REFERENCES boqs(id) ON DELETE CASCADE)""")
        cursor.execute("""CREATE TABLE IF NOT EXISTS comparison_docs (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, vendor_name TEXT, offered_price REAL, file_path TEXT, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
        
        # MIGRATIONS
        for col, dtype in [("target_rfs", "TEXT"), ("pipeline_stage", "TEXT"), ("progress_pct", "INTEGER")]:
            try: cursor.execute(f"ALTER TABLE projects ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError: pass
            
        for col, dtype in [("item_no", "TEXT"), ("preferred_brand", "TEXT"), ("delivery_time", "TEXT"), ("sph_awal_unit", "REAL"), ("sph_final_unit", "REAL")]:
            try: cursor.execute(f"ALTER TABLE items ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError: pass
            
        for col, dtype in [("sph_awal_unit", "REAL"), ("sph_final_unit", "REAL")]:
            try: cursor.execute(f"ALTER TABLE request_items ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError: pass

        # DEFAULT USERS
        for user_data in [
            ("admin", "admin123", "Admin Presourcing", "Presourcing Control", "admin"),
            ("master", "master123", "Master Admin", "System Control", "admin"),
            ("tester", "tester123", "QA Tester", "Testing Team", "sa"),
        ]:
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (user_data[0],))
            if cursor.fetchone()[0] == 0:
                cursor.execute("INSERT INTO users (username, password, full_name, department, role) VALUES (?, ?, ?, ?, ?)", user_data)
        conn.commit()

init_db()

# ============================================================================
# RELATIONAL DATA HELPER
# ============================================================================
def get_projects_relational(cursor):
    cursor.execute("SELECT * FROM projects")
    projects_data = []
    
    for p_row in cursor.fetchall():
        p = dict(p_row)
        cursor.execute("SELECT vendor_name, offered_price, file_path FROM comparison_docs WHERE project_id = ?", (p["id"],))
        p["comparison_docs"] = [dict(d) for d in cursor.fetchall()]

        cursor.execute("SELECT id, name FROM sows WHERE project_id = ?", (p["id"],))
        sows = []
        for s_row in cursor.fetchall():
            s = dict(s_row)
            cursor.execute("SELECT id, name FROM boqs WHERE sow_id = ?", (s["id"],))
            boqs = []
            for b_row in cursor.fetchall():
                b = dict(b_row)
                cursor.execute("SELECT * FROM items WHERE boq_id = ?", (b["id"],))
                items = []
                for i_row in cursor.fetchall():
                    i = dict(i_row)
                    i["picIds"] = json.loads(i["pic_ids"]) if i["pic_ids"] else []
                    i["sphAwal"] = i.pop("sph_awal")
                    i["sphFinal"] = i.pop("sph_final")
                    i["sphAwalUnit"] = i.pop("sph_awal_unit", None)
                    i["sphFinalUnit"] = i.pop("sph_final_unit", None)
                    
                    if i["sphAwalUnit"] is None: i["sphAwalUnit"] = derive_unit_price(i.get("qty"), i.get("sphAwal"))
                    if i["sphFinalUnit"] is None: i["sphFinalUnit"] = derive_unit_price(i.get("qty"), i.get("sphFinal"))

                    i["itemNo"] = i.pop("item_no", "")
                    i["preferredBrand"] = i.pop("preferred_brand", "")
                    i["deliveryTime"] = i.pop("delivery_time", "")
                    items.append(i)
                b["items"] = items
                boqs.append(b)
            s["boqs"] = boqs
            sows.append(s)
        p["sows"] = sows

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
        projects_data.append(p)
    return projects_data

# ============================================================================
# AUTH & NOTIFICATIONS
# ============================================================================
@app.route("/api/register", methods=["POST"])
def register():
    payload = request.json or {}
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO users (username, password, full_name, department, role) VALUES (?, ?, ?, ?, ?)", (payload.get("username"), payload.get("password"), payload.get("full_name"), payload.get("department", ""), payload.get("role", "sa")))
            conn.commit()
            return jsonify({"success": True, "message": "Registrasi berhasil!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Username sudah terdaftar!"}), 400

@app.route("/api/login", methods=["POST"])
def login():
    payload = request.json or {}
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, full_name, department, role FROM users WHERE username = ? AND password = ?", (payload.get("username"), payload.get("password")))
        user = cursor.fetchone()
        if user:
            session.update({"username": user[0], "full_name": user[1], "department": user[2], "role": user[3]})
            return jsonify({"success": True, "user": {"username": user[0], "full_name": user[1], "department": user[2], "role": user[3]}}), 200
        return jsonify({"success": False, "message": "Username atau Password salah!"}), 401

@app.route("/api/logout", methods=["POST"])
def logout():
    session.clear()
    return jsonify({"success": True, "message": "Berhasil logout"})

@app.route("/api/notifications", methods=["GET"])
def get_notifications():
    target = request.args.get("username")
    if not target: return jsonify({"success": False, "message": "Target user diperlukan"}), 400
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if target == "admin":
                cursor.execute("SELECT id, name, target_rfs FROM projects WHERE status = 'ongoing' AND target_rfs IS NOT NULL AND target_rfs != ''")
                for p in cursor.fetchall():
                    try:
                        rfs_date = datetime.strptime(p["target_rfs"], "%Y-%m-%d").date()
                        days_left = (rfs_date - datetime.now().date()).days
                        msg = ""
                        if days_left < 0: msg = f"🚨 OVERDUE: Project '{p['name']}' telah melewati batas Target RFS!"
                        elif days_left <= 14: msg = f"⚠️ AT RISK: Project '{p['name']}' tersisa {days_left} hari menuju RFS."
                        if msg:
                            cursor.execute("SELECT COUNT(*) FROM notifications WHERE target_user = 'admin' AND message = ? AND date(created_at) = date('now', 'localtime')", (msg,))
                            if cursor.fetchone()[0] == 0:
                                cursor.execute("INSERT INTO notifications (target_user, message) VALUES ('admin', ?)", (msg,))
                    except Exception: pass
            conn.commit()
            cursor.execute("SELECT * FROM notifications WHERE target_user = ? OR target_user = 'broadcast' ORDER BY created_at DESC LIMIT 20", (target,))
            return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]}), 200
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/notifications/<int:notif_id>/read", methods=["POST"])
def mark_notification_read(notif_id):
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.cursor().execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
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
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO requests (ticket_id, title, client_name, competitor_info, sla_date, notes, requester_username, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'unassigned')", (ticket_id, payload.get("title"), payload.get("client_name"), payload.get("competitor_info"), payload.get("sla_date"), payload.get("notes"), payload.get("requester_username")))
            cursor.execute("INSERT INTO notifications (target_user, message) VALUES ('admin', ?)", (f"Request Baru: {ticket_id} dari @{payload.get('requester_username')}",))
            conn.commit()
            return jsonify({"success": True, "message": "Request berhasil dibuat", "ticket_id": ticket_id}), 201
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/requests", methods=["GET"])
def get_requests():
    username, role = request.args.get("username"), request.args.get("role")
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = "SELECT r.*, u.full_name, u.department, p.pipeline_stage, p.progress_pct, p.target_rfs FROM requests r LEFT JOIN users u ON r.requester_username = u.username LEFT JOIN projects p ON r.ticket_id = p.id"
            if role != "admin":
                cursor.execute(query + " WHERE r.requester_username = ? ORDER BY r.created_at DESC", (username,))
            else:
                cursor.execute(query + " ORDER BY r.created_at DESC")
            return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]})
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/upload_boq", methods=["POST"])
def upload_boq():
    ticket_id = request.form.get("ticket_id")
    if not ticket_id or "file" not in request.files: return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    file = request.files["file"]
    if not file.filename: return jsonify({"success": False, "message": "Nama file tidak valid."}), 400
    try:
        df = _read_boq_excel(file, require_system_id=False)
        rows, issues = _parse_boq_rows(df)
        for item in rows:
            if item["id"]: issues.append({"row": item["excelRow"], "severity": "error", "message": f"'{BOQ_SYSTEM_COLUMN}' harus kosong untuk Initial Request."})
        
        errors = [x for x in issues if x["severity"] == "error"]
        if errors: return jsonify({"success": False, "message": "Excel memiliki error. Perbaiki file terlebih dahulu.", "issues": issues[:50]}), 400

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM request_items WHERE ticket_id = ?", (ticket_id,))
            for item in rows:
                cursor.execute("INSERT INTO request_items (ticket_id, sow_name, boq_section, item_no, description, preferred_brand, quantity, uom, delivery_time, vendor, sph_awal_unit, sph_final_unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (ticket_id, item["sowName"], item["boqName"], item["itemNo"], item["product"], item["preferredBrand"], item["qty"], item["uom"], item["deliveryTime"], item["vendor"] or None, item["sphAwalUnit"], item["sphFinalUnit"]))
            conn.commit()
        return jsonify({"success": True, "message": "File BoQ berhasil diunggah.", "summary": {"items": len(rows), "warnings": sum(1 for x in issues if x["severity"] == "warning")}}), 200
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/request_items/<ticket_id>", methods=["GET"])
def get_request_items(ticket_id):
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
        return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]}), 200

@app.route("/api/requests/assign", methods=["POST"])
def assign_ticket():
    payload = request.json or {}
    ticket_id, pic_username = payload.get("ticket_id"), payload.get("pic_username")
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("UPDATE requests SET pic_username = ?, status = 'ongoing' WHERE ticket_id = ?", (pic_username, ticket_id))
            cursor.execute("SELECT r.*, u.full_name, u.department FROM requests r LEFT JOIN users u ON r.requester_username = u.username WHERE r.ticket_id = ?", (ticket_id,))
            req = cursor.fetchone()
            
            if req:
                cursor.execute("SELECT COUNT(*) FROM projects WHERE id = ?", (ticket_id,))
                if cursor.fetchone()[0] == 0:
                    cursor.execute("INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, created_at, target_rfs, pipeline_stage, progress_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (ticket_id, f"{req['title']} ({req['client_name'] or 'Klien Umum'})", req["full_name"] or req["requester_username"], req["department"] or "Presales Team", "High", "ongoing", pic_username, "item", req["created_at"][:10] if req["created_at"] else datetime.now().strftime("%Y-%m-%d"), req["sla_date"] if req["sla_date"] else "", "1 - Project Identification", 0))
                    
                    cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
                    grouped_data = {}
                    for it in cursor.fetchall():
                        grouped_data.setdefault(it["sow_name"] or "General Scope of Work", {}).setdefault(it["boq_section"] or "General Items", []).append(it)
                    
                    for s_name, boqs in grouped_data.items():
                        sow_id = f"sow_{uuid.uuid4().hex[:8]}"
                        cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow_id, ticket_id, s_name))
                        for b_name, items_list in boqs.items():
                            boq_id = f"boq_{uuid.uuid4().hex[:8]}"
                            cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq_id, sow_id, b_name))
                            for it in items_list:
                                cursor.execute("INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time, sph_awal_unit, sph_final_unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (f"item_{uuid.uuid4().hex[:8]}", boq_id, it["description"], it["quantity"], it["uom"], it["vendor"] or "", calculate_sph_total(it["quantity"], it["sph_awal_unit"]), calculate_sph_total(it["quantity"], it["sph_final_unit"]), "", json.dumps([pic_username]), it["item_no"] or "", it["preferred_brand"] or "", it["delivery_time"] or "", it["sph_awal_unit"], it["sph_final_unit"]))
                    
                    cursor.execute("INSERT INTO notifications (target_user, message) VALUES (?, ?)", (req["requester_username"], f"Tiket {ticket_id} sudah di-assign ke PIC: {pic_username}"))
            conn.commit()
        return jsonify({"success": True, "message": "Tiket berhasil di-assign!"}), 200
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# PRESOURCING API
# ============================================================================
@app.route("/api/presourcing", methods=["GET", "POST"])
def api_presourcing():
    if request.method == "GET":
        try:
            with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'team'")
                team_row = cursor.fetchone()
                return jsonify({"projects": get_projects_relational(cursor), "team": json.loads(team_row["json_data"]) if team_row and team_row["json_data"] else []}), 200
        except Exception as e: return jsonify({"error": str(e)}), 500

    data = request.json or {}
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            cursor.execute("REPLACE INTO dashboard_state (data_type, json_data) VALUES ('team', ?)", (json.dumps(data.get("team", [])),))

            existing_db_ids = {row[0] for row in cursor.execute("SELECT id FROM projects").fetchall()}
            incoming_ids = {p["id"] for p in data.get("projects", [])}
            
            for del_id in (existing_db_ids - incoming_ids):
                cursor.execute("DELETE FROM projects WHERE id = ?", (del_id,))
                cursor.execute("DELETE FROM request_items WHERE ticket_id = ?", (del_id,))
                cursor.execute("DELETE FROM requests WHERE ticket_id = ?", (del_id,))

            for p in data.get("projects", []):
                cursor.execute("DELETE FROM projects WHERE id = ?", (p["id"],))
                cursor.execute("INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, project_sph_awal, project_sph_final, created_at, closed_at, target_rfs, pipeline_stage, progress_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (p["id"], p.get("name"), p.get("requestorName"), p.get("requestorDept"), p.get("priority"), p.get("status"), p.get("leadId"), p.get("sphMode"), p.get("projectSphAwal"), p.get("projectSphFinal"), p.get("createdAt"), p.get("closedAt"), p.get("targetRfs"), p.get("pipelineStage"), p.get("progressPct")))

                for sow in p.get("sows", []):
                    cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow["id"], p["id"], sow.get("name")))
                    for boq in sow.get("boqs", []):
                        cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq["id"], sow["id"], boq.get("name")))
                        for it in boq.get("items", []):
                            sph_awal_unit, sph_awal_total = resolve_sph_values(it.get("qty"), optional_number(it.get("sphAwalUnit")), it.get("sphAwal"))
                            sph_final_unit, sph_final_total = resolve_sph_values(it.get("qty"), optional_number(it.get("sphFinalUnit")), it.get("sphFinal"))

                            cursor.execute("INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time, sph_awal_unit, sph_final_unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (it["id"], boq["id"], it.get("product"), it.get("qty"), it.get("uom"), it.get("vendor"), sph_awal_total, sph_final_total, it.get("notes"), json.dumps(it.get("picIds", [])), it.get("itemNo", ""), it.get("preferredBrand", ""), it.get("deliveryTime", ""), sph_awal_unit, sph_final_unit))

                for doc in p.get("comparison_docs", []):
                    cursor.execute("INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES (?, ?, ?, ?)", (p["id"], doc.get("vendor_name"), doc.get("offered_price"), doc.get("file_path")))
            conn.commit()
        return jsonify({"success": True}), 200
    except Exception as e: return jsonify({"error": str(e)}), 500

@app.route("/api/projects/<project_id>/download_boq_template", methods=["GET"])
def download_project_boq_template(project_id):
    if "username" not in session: return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    try:
        template_path = os.path.join(app.static_folder, BOQ_TEMPLATE_FILENAME)
        if not os.path.isfile(template_path): return jsonify({"success": False, "message": "Template BoQ tidak ditemukan."}), 404

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT i.item_no, i.product, i.qty, i.uom, i.preferred_brand, i.delivery_time, i.vendor, i.sph_awal, i.sph_final, i.sph_awal_unit, i.sph_final_unit, i.id AS item_id, s.name AS sow_name, b.name AS boq_name FROM items i JOIN boqs b ON i.boq_id = b.id JOIN sows s ON b.sow_id = s.id WHERE s.project_id = ? ORDER BY s.name, b.name, i.item_no, i.rowid", (project_id,))
            items = [dict(row) for row in cursor.fetchall()]

        wb = load_workbook(template_path)
        ws = wb["BoQ Request"]
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=14):
            for cell in row: cell.value = None

        style_row = min(51, ws.max_row)

        for excel_row, item in enumerate(items, start=2):
            awal_unit = item.get("sph_awal_unit") if item.get("sph_awal_unit") is not None else derive_unit_price(item.get("qty"), item.get("sph_awal"))
            final_unit = item.get("sph_final_unit") if item.get("sph_final_unit") is not None else derive_unit_price(item.get("qty"), item.get("sph_final"))

            values = {1: item.get("item_no", ""), 2: item.get("product", ""), 3: item.get("qty", 0), 4: item.get("uom", ""), 5: item.get("preferred_brand", ""), 6: item.get("delivery_time", ""), 7: item.get("sow_name", ""), 8: item.get("boq_name", ""), 9: item.get("vendor", ""), 10: awal_unit, 12: final_unit, 14: item.get("item_id", "")}

            if excel_row > style_row:
                for col in range(1, 15):
                    source, target = ws.cell(style_row, col), ws.cell(excel_row, col)
                    if source.has_style: target._style = copy(source._style)
                    target.number_format = source.number_format

            for col, value in values.items():
                cell = ws.cell(excel_row, col)
                if col == 6 and value:
                    try:
                        cell.value = datetime.strptime(str(value), "%Y-%m-%d").date()
                        cell.number_format = "yyyy-mm-dd"
                    except ValueError: cell.value = value
                else: cell.value = value

            ws.cell(excel_row, 11).value = f'=IF(OR(C{excel_row}="",J{excel_row}=""),"",C{excel_row}*J{excel_row})'
            ws.cell(excel_row, 13).value = f'=IF(OR(C{excel_row}="",L{excel_row}=""),"",C{excel_row}*L{excel_row})'

        if "BoQInputTable" in ws.tables: ws.tables["BoQInputTable"].ref = f"A1:N{max(2, len(items) + 1)}"

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"BoQ_Revisi_{project_id}.xlsx")
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/projects/<project_id>", methods=["DELETE"])
def delete_project(project_id):
    if "username" not in session: return jsonify({"success": False, "message": "Akses ditolak! Silakan login."}), 403
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            cursor = conn.cursor()
            cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            cursor.execute("DELETE FROM request_items WHERE ticket_id = ?", (project_id,))
            cursor.execute("DELETE FROM requests WHERE ticket_id = ?", (project_id,))
            if cursor.rowcount > 0:
                conn.commit()
                return jsonify({"success": True, "message": "Project berhasil dihapus dari database!"}), 200
            return jsonify({"success": False, "message": "Project tidak ditemukan atau sudah terhapus."}), 404
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

# ============================================================================
# PROJECT REPORT
# ============================================================================
@app.route("/api/download_report", methods=["GET"])
def download_report():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({
            "success": False,
            "message": "Akses ditolak!"
    }), 403

    target_project_id = str(
        request.args.get("project_id") or ""
    ).strip()

    if not target_project_id:
        return jsonify (
            "Project ID wajib diberikan.",
            400,
        )

    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
             conn.row_factory = sqlite3.Row

        projects = get_projects_relational(
        conn.cursor()
    )

        project = next(
            (
                p for p in projects
                if str(p.get("id") or "") == target_project_id
            ),
            None,
        )

        if project is None:
            return jsonify (
                "Project tidak ditemukan.",
                404,
            )

        # ------------------------------------------------------------------
        # COLLECT ITEMS
        # ------------------------------------------------------------------
        items = []

        for sow in project.get("sows") or []:
            for boq in sow.get("boqs") or []:
                for item in boq.get("items") or []:
                    items.append(
                        {
                            "sow": sow.get("name", ""),
                            "boq": boq.get("name", ""),
                            **item,
                        }
                    )

        # ------------------------------------------------------------------
        # SPH CALCULATION
        # ------------------------------------------------------------------
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

            total_sph_awal = (
                total_sph_awal
                if has_awal
                else None
            )

            total_sph_final = (
                total_sph_final
                if has_final and items
                else None
            )

        efficiency = None

        if (
            total_sph_awal is not None
            and total_sph_final is not None
            and float(total_sph_awal) > 0
        ):
            efficiency = (
                (
                    float(total_sph_awal)
                    - float(total_sph_final)
                )
                / float(total_sph_awal)
            )

        # ------------------------------------------------------------------
        # PROJECT METRICS
        # ------------------------------------------------------------------
        total_qty = sum(
            float(item.get("qty") or 0)
            for item in items
        )

        vendors = sorted(
            {
                str(item.get("vendor") or "").strip()
                for item in items
                if str(item.get("vendor") or "").strip()
            }
        )

        pics = sorted(
            {
                str(pic).strip()
                for item in items
                for pic in (item.get("picIds") or [])
                if str(pic).strip()
            }
        )

        lead_id = project.get("leadId") or ""

        if lead_id and lead_id not in pics:
            pics.insert(0, lead_id)

        # ------------------------------------------------------------------
        # WORKBOOK
        # ------------------------------------------------------------------
        wb = Workbook()

        ws = wb.active
        ws.title = "Project Summary"

        detail_ws = wb.create_sheet("BoQ Detail")

        # ------------------------------------------------------------------
        # STYLES
        # ------------------------------------------------------------------
        title_fill = PatternFill(
            "solid",
            fgColor="1F4E78",
        )

        section_fill = PatternFill(
            "solid",
            fgColor="D9EAF7",
        )

        header_fill = PatternFill(
            "solid",
            fgColor="5B9BD5",
        )

        white_font = Font(
            color="FFFFFF",
            bold=True,
            size=14,
        )

        section_font = Font(
            bold=True,
            size=11,
        )

        header_font = Font(
            color="FFFFFF",
            bold=True,
        )

        normal_font = Font(
            size=10,
        )

        thin_side = Side(
            style="thin",
            color="D9E1F2",
        )

        border = Border(
            left=thin_side,
            right=thin_side,
            top=thin_side,
            bottom=thin_side,
        )

        currency_format = (
            '"Rp" #,##0;'
            '"-Rp" #,##0;'
            '-'
        )

        number_format = '#,##0.##'

        percent_format = '0.0%;-0.0%;-'

        # ------------------------------------------------------------------
        # SHEET 1: PROJECT SUMMARY
        # ------------------------------------------------------------------
        ws.merge_cells("A1:F1")
        ws["A1"] = "PROJECT REPORT"
        ws["A1"].fill = title_fill
        ws["A1"].font = white_font
        ws["A1"].alignment = Alignment(
            horizontal="left",
            vertical="center",
        )
        ws.row_dimensions[1].height = 26

        ws.merge_cells("A2:F2")
        ws["A2"] = project.get("name") or "-"
        ws["A2"].font = Font(
            bold=True,
            size=13,
        )
        ws["A2"].alignment = Alignment(
            vertical="center",
        )

        # Project Information
        ws.merge_cells("A4:F4")
        ws["A4"] = "PROJECT INFORMATION"
        ws["A4"].fill = section_fill
        ws["A4"].font = section_font

        project_info = [
            ("Ticket ID", project.get("id")),
            ("Requestor / SA", project.get("requestorName")),
            ("Department", project.get("requestorDept")),
            ("PIC / Lead Presource", project.get("leadId")),
            ("Outcome", project.get("status")),
            ("Pipeline Stage", project.get("pipelineStage")),
            ("Progress", project.get("progressPct")),
            ("Target RFS", project.get("targetRfs")),
            ("Created Date", project.get("createdAt")),
            ("Priority", project.get("priority")),
        ]

        row = 5

        for label, value in project_info:
            ws.cell(row=row, column=1).value = label
            ws.cell(row=row, column=1).font = Font(bold=True)

            ws.cell(row=row, column=2).value = (
                value if value not in (None, "") else "-"
            )

            ws.merge_cells(
                start_row=row,
                start_column=2,
                end_row=row,
                end_column=6,
            )

            if label == "Progress" and value is not None:
                ws.cell(row=row, column=2).value = (
                    float(value) / 100
                )
                ws.cell(row=row, column=2).number_format = (
                    "0%"
                )

            row += 1

        # Commercial Summary
        row += 1

        ws.merge_cells(
            start_row=row,
            start_column=1,
            end_row=row,
            end_column=6,
        )

        ws.cell(row=row, column=1).value = (
            "COMMERCIAL SUMMARY"
        )
        ws.cell(row=row, column=1).fill = section_fill
        ws.cell(row=row, column=1).font = section_font

        row += 1

        commercial = [
            ("Total Item", len(items), None),
            ("Total Qty", total_qty, number_format),
            ("Total SPH Awal", total_sph_awal, currency_format),
            ("Total SPH Final", total_sph_final, currency_format),
            ("Efficiency", efficiency, percent_format),
            (
                "Vendor",
                ", ".join(vendors) if vendors else "-",
                None,
            ),
            (
                "PIC Terlibat",
                ", ".join(pics) if pics else "-",
                None,
            ),
        ]

        for label, value, fmt in commercial:
            ws.cell(row=row, column=1).value = label
            ws.cell(row=row, column=1).font = Font(
                bold=True
            )

            ws.merge_cells(
                start_row=row,
                start_column=2,
                end_row=row,
                end_column=6,
            )

            ws.cell(row=row, column=2).value = (
                value if value not in (None, "") else "-"
            )

            if fmt and value is not None:
                ws.cell(row=row, column=2).number_format = fmt

            row += 1

        # Notes
        row += 1

        ws.merge_cells(
            start_row=row,
            start_column=1,
            end_row=row,
            end_column=6,
        )

        ws.cell(row=row, column=1).value = (
            "REPORT SCOPE"
        )
        ws.cell(row=row, column=1).fill = section_fill
        ws.cell(row=row, column=1).font = section_font

        row += 1

        ws.merge_cells(
            start_row=row,
            start_column=1,
            end_row=row + 1,
            end_column=6,
        )

        ws.cell(row=row, column=1).value = (
            "Report ini berisi informasi project dan detail "
            "BoQ berdasarkan data Presourcing saat report "
            "dibuat."
        )

        ws.cell(row=row, column=1).alignment = Alignment(
            wrap_text=True,
            vertical="top",
        )

        # ------------------------------------------------------------------
        # SHEET 2: BOQ DETAIL
        # ------------------------------------------------------------------
        detail_headers = [
            "SoW",
            "BoQ",
            "Item No",
            "Item ID",
            "Description",
            "Qty",
            "UoM",
            "Preferred Brand",
            "Delivery Time (RFS)",
            "Vendor",
            "SPH Awal / Unit",
            "Total SPH Awal",
            "SPH Final / Unit",
            "Total SPH Final",
            "Efficiency",
            "PIC",
        ]

        for col_idx, header in enumerate(
            detail_headers,
            start=1,
        ):
            cell = detail_ws.cell(
                row=1,
                column=col_idx,
                value=header,
            )
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(
                horizontal="center",
                vertical="center",
                wrap_text=True,
            )
            cell.border = border

        for row_idx, item in enumerate(
            items,
            start=2,
        ):
            awal_unit = item.get("sphAwalUnit")
            awal_total = item.get("sphAwal")

            final_unit = item.get("sphFinalUnit")
            final_total = item.get("sphFinal")

            item_efficiency = None

            if (
                awal_total is not None
                and final_total is not None
                and float(awal_total) > 0
            ):
                item_efficiency = (
                    float(awal_total)
                    - float(final_total)
                ) / float(awal_total)

            row_values = [
                item.get("sow") or "-",
                item.get("boq") or "-",
                item.get("itemNo") or "-",
                item.get("id") or "-",
                item.get("product") or "-",
                item.get("qty")
                if item.get("qty") is not None
                else "-",
                item.get("uom") or "-",
                item.get("preferredBrand") or "-",
                item.get("deliveryTime") or "-",
                item.get("vendor") or "-",
                awal_unit,
                awal_total,
                final_unit,
                final_total,
                item_efficiency,
                ", ".join(
                    item.get("picIds") or []
                ) or lead_id or "-",
            ]

            for col_idx, value in enumerate(
                row_values,
                start=1,
            ):
                cell = detail_ws.cell(
                    row=row_idx,
                    column=col_idx,
                    value=value,
                )
                cell.border = border
                cell.font = normal_font
                cell.alignment = Alignment(
                    vertical="top",
                    wrap_text=True,
                )

            # Number formats
            detail_ws.cell(
                row=row_idx,
                column=6,
            ).number_format = number_format

            for col_idx in (11, 12, 13, 14):
                detail_ws.cell(
                    row=row_idx,
                    column=col_idx,
                ).number_format = currency_format

            detail_ws.cell(
                row=row_idx,
                column=15,
            ).number_format = percent_format

        # ------------------------------------------------------------------
        # DETAIL SHEET FORMATTING
        # ------------------------------------------------------------------
        detail_ws.freeze_panes = "A2"
        detail_ws.auto_filter.ref = detail_ws.dimensions
        detail_ws.row_dimensions[1].height = 30

        detail_widths = {
            "A": 22,
            "B": 24,
            "C": 12,
            "D": 22,
            "E": 34,
            "F": 10,
            "G": 10,
            "H": 22,
            "I": 20,
            "J": 25,
            "K": 20,
            "L": 20,
            "M": 20,
            "N": 20,
            "O": 14,
            "P": 24,
        }

        for column, width in detail_widths.items():
            detail_ws.column_dimensions[column].width = width

        # ------------------------------------------------------------------
        # SUMMARY SHEET FORMATTING
        # ------------------------------------------------------------------
        summary_widths = {
            "A": 25,
            "B": 24,
            "C": 18,
            "D": 18,
            "E": 18,
            "F": 18,
        }

        for column, width in summary_widths.items():
            ws.column_dimensions[column].width = width

        ws.freeze_panes = "A5"

        # Borders for information areas
        for row_cells in ws.iter_rows(
            min_row=5,
            max_row=ws.max_row,
            min_col=1,
            max_col=6,
        ):
            for cell in row_cells:
                cell.border = border

        # ------------------------------------------------------------------
        # OUTPUT
        # ------------------------------------------------------------------
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        safe_project_id = (
            target_project_id
            .replace("/", "_")
            .replace("\\", "_")
            .replace(" ", "_")
        )

        return send_file(
            output,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=(
                f"Project_Report_{safe_project_id}_"
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            ),
        )

    except Exception as exc:
        return jsonify (
            str(exc),
            500,
        )
@app.route("/api/project_import_boq/preview", methods=["POST"])
def preview_project_import_boq():
    if "file" not in request.files: return jsonify({"success": False, "message": "File Excel tidak ditemukan."}), 400
    file = request.files["file"]
    if not file.filename: return jsonify({"success": False, "message": "Nama file tidak valid."}), 400
    try:
        df = _read_boq_excel(file, require_system_id=False)
        rows, issues = _parse_boq_rows(df)
        for item in rows:
            if item["id"]: issues.append({"row": item["excelRow"], "severity": "error", "message": f"'{BOQ_SYSTEM_COLUMN}' harus kosong untuk Project Baru."})

        sows = {}
        for item in rows:
            sows.setdefault(item["sowName"], {}).setdefault(item["boqName"], []).append({
                "id": f"item_{uuid.uuid4().hex[:8]}", "itemNo": item["itemNo"], "product": item["product"], "qty": item["qty"], "uom": item["uom"], "preferredBrand": item["preferredBrand"], "deliveryTime": item["deliveryTime"], "vendor": item["vendor"], "notes": "", "picIds": [], "sphAwalUnit": item["sphAwalUnit"], "sphFinalUnit": item["sphFinalUnit"], "sphAwal": calculate_sph_total(item["qty"], item["sphAwalUnit"]), "sphFinal": calculate_sph_total(item["qty"], item["sphFinalUnit"]),
            })

        result_sows = [{"id": f"sow_{uuid.uuid4().hex[:8]}", "name": s_name, "boqs": [{"id": f"boq_{uuid.uuid4().hex[:8]}", "name": b_name, "items": items} for b_name, items in boq_groups.items()]} for s_name, boq_groups in sows.items()]

        errors = sum(1 for x in issues if x["severity"] == "error")
        return jsonify({"success": True, "data": {"summary": {"rows": len(df), "items": sum(len(b["items"]) for s in result_sows for b in s["boqs"]), "sows": len(result_sows), "boqs": sum(len(s["boqs"]) for s in result_sows), "errors": errors, "warnings": sum(1 for x in issues if x["severity"] == "warning")}, "issues": issues[:50], "has_errors": errors > 0, "sows": result_sows}}), 200
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

def _revision_items_for_project(cursor, ticket_id):
    cursor.execute("SELECT i.*, b.name AS boq_name, s.name AS sow_name FROM items i JOIN boqs b ON i.boq_id = b.id JOIN sows s ON b.sow_id = s.id WHERE s.project_id = ?", (ticket_id,))
    return [dict(row) for row in cursor.fetchall()]

@app.route("/api/revisi_boq/preview", methods=["POST"])
def preview_revisi_boq():
    ticket_id = request.form.get("ticket_id")
    if "file" not in request.files or not ticket_id: return jsonify({"success": False, "message": "Data tidak valid."}), 400
    try:
        df = _read_boq_excel(request.files["file"], require_system_id=True)
        incoming, issues = _parse_boq_rows(df)

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE id = ?", (ticket_id,))
            if not cursor.fetchone(): return jsonify({"success": False, "message": "Project tidak ditemukan."}), 404
            existing_rows = _revision_items_for_project(cursor, ticket_id)

        existing = {str(row["id"]).strip(): row for row in existing_rows if row["id"]}
        incoming_ids = {item["id"] for item in incoming if item["id"]}

        for item in incoming:
            if item["id"] and item["id"] not in existing:
                issues.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID '{item['id']}' tidak ditemukan di project."})

        added, updated, unchanged = [], [], []

        def norm(value, is_number=False):
            if is_number:
                if value is None or value == "": return None
                try: return float(value)
                except (TypeError, ValueError): return None
            return _excel_text(value).lower()

        for item in incoming:
            if not item["id"]:
                added.append({"description": item["product"], "qty": item["qty"], "uom": item["uom"], "vendor": item["vendor"], "sphAwalUnit": item["sphAwalUnit"], "sphFinalUnit": item["sphFinalUnit"]})
                continue

            old = existing.get(item["id"])
            if not old: continue

            changes = {}
            comparisons = [
                ("Item No", old.get("item_no"), item["itemNo"], False), ("Deskripsi Item", old.get("product"), item["product"], False), ("Qty", old.get("qty"), item["qty"], True), ("UoM", old.get("uom"), item["uom"], False), ("Preferred Brand", old.get("preferred_brand"), item["preferredBrand"], False), ("Delivery Time (RFS)", old.get("delivery_time"), item["deliveryTime"], False), ("Scope of Work", old.get("sow_name"), item["sowName"], False), ("Bill of Quantity", old.get("boq_name"), item["boqName"], False), ("Vendor", old.get("vendor"), item["vendor"], False), ("SPH Awal / Unit", old.get("sph_awal_unit"), item["sphAwalUnit"], True), ("SPH Final / Unit", old.get("sph_final_unit"), item["sphFinalUnit"], True),
            ]

            for (label, old_value, new_value, is_number) in comparisons:
                if norm(old_value, is_number) != norm(new_value, is_number): changes[label] = [_excel_text(old_value), _excel_text(new_value)]

            if changes: updated.append({"id": item["id"], "description": item["product"], "qty": item["qty"], "uom": item["uom"], "vendor": item["vendor"], "changes": changes})
            else: unchanged.append({"id": item["id"], "description": item["product"]})

        removed = [{"id": row["id"], "description": row["product"], "itemNo": row.get("item_no", "")} for item_id, row in existing.items() if item_id not in incoming_ids]
        errors = sum(1 for x in issues if x["severity"] == "error")

        return jsonify({"success": True, "data": {"summary": {"added": len(added), "updated": len(updated), "removed": len(removed), "unchanged": len(unchanged), "errors": errors, "warnings": sum(1 for x in issues if x["severity"] == "warning")}, "issues": issues[:50], "has_errors": errors > 0, "added": added, "updated": updated, "removed": removed, "unchanged": unchanged}}), 200
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/revisi_boq", methods=["POST"])
def revisi_boq():
    ticket_id = request.form.get("ticket_id")
    if "file" not in request.files or not ticket_id: return jsonify({"success": False, "message": "Data tidak valid."}), 400
    try:
        df = _read_boq_excel(request.files["file"], require_system_id=True)
        incoming, issues = _parse_boq_rows(df)

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            cursor.execute("SELECT id FROM projects WHERE id = ?", (ticket_id,))
            if not cursor.fetchone(): return jsonify({"success": False, "message": "Project tidak ditemukan."}), 404

            existing = {str(row["id"]).strip(): row for row in _revision_items_for_project(cursor, ticket_id) if row["id"]}
            validation_errors = list(issues)
            seen_ids = set()

            for item in incoming:
                item_id = item["id"]
                if not item_id: continue
                if item_id in seen_ids: validation_errors.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID duplikat: {item_id}."})
                seen_ids.add(item_id)
                if item_id not in existing: validation_errors.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID '{item_id}' tidak ditemukan di project."})

            if any(x["severity"] == "error" for x in validation_errors):
                return jsonify({"success": False, "message": "Excel revisi memiliki error. Perbaiki file lalu upload kembali.", "issues": validation_errors[:50]}), 400

            sow_map, boq_map = {}, {}
            cursor.execute("SELECT id, name FROM sows WHERE project_id = ?", (ticket_id,))
            for s_row in cursor.fetchall():
                sow_map[s_row["name"]] = s_row["id"]
                cursor.execute("SELECT id, name FROM boqs WHERE sow_id = ?", (s_row["id"],))
                for b_row in cursor.fetchall(): boq_map[(s_row["name"], b_row["name"])] = b_row["id"]

            incoming_existing_ids = set()

            for item in incoming:
                s_name, b_name = item["sowName"], item["boqName"]
                if s_name not in sow_map:
                    sow_id = f"sow_{uuid.uuid4().hex[:8]}"
                    cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow_id, ticket_id, s_name))
                    sow_map[s_name] = sow_id
                sow_id = sow_map[s_name]

                boq_key = (s_name, b_name)
                if boq_key not in boq_map:
                    boq_id = f"boq_{uuid.uuid4().hex[:8]}"
                    cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq_id, sow_id, b_name))
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
                    cursor.execute("UPDATE items SET boq_id = ?, product = ?, qty = ?, uom = ?, vendor = ?, item_no = ?, preferred_brand = ?, delivery_time = ?, sph_awal = ?, sph_final = ?, sph_awal_unit = ?, sph_final_unit = ? WHERE id = ?", (boq_id, item["product"], item["qty"], item["uom"], item["vendor"], item["itemNo"], item["preferredBrand"], item["deliveryTime"], sph_awal_total, sph_final_total, sph_awal_unit, sph_final_unit, old["id"]))
                else:
                    cursor.execute("INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time, sph_awal_unit, sph_final_unit) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (f"item_{uuid.uuid4().hex[:8]}", boq_id, item["product"], item["qty"], item["uom"], item["vendor"], sph_awal_total, sph_final_total, "", "[]", item["itemNo"], item["preferredBrand"], item["deliveryTime"], sph_awal_unit, sph_final_unit))

            for item_id in (set(existing) - incoming_existing_ids):
                cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))

            cursor.execute("DELETE FROM boqs WHERE id NOT IN (SELECT DISTINCT boq_id FROM items)")
            cursor.execute("DELETE FROM sows WHERE id NOT IN (SELECT DISTINCT sow_id FROM boqs)")
            conn.commit()

        return jsonify({"success": True, "message": "BoQ berhasil direvisi!"}), 200
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 400

@app.route("/api/download_template_boq", methods=["GET"])
def download_template_boq():
    if "username" not in session: return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    path = os.path.join(app.static_folder, BOQ_TEMPLATE_FILENAME)
    if not os.path.isfile(path): return jsonify({"success": False, "message": f"Template '{BOQ_TEMPLATE_FILENAME}' belum tersedia di folder static."}), 404
    return send_from_directory(app.static_folder, BOQ_TEMPLATE_FILENAME, as_attachment=True, download_name=BOQ_TEMPLATE_FILENAME)

@app.route("/api/upload_comparison", methods=["POST"])
def upload_comparison():
    ticket_id, vendor_name, offered_price = request.form.get("ticket_id"), request.form.get("vendor_name"), request.form.get("offered_price")
    if "file" not in request.files or not ticket_id or not vendor_name or not offered_price: return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    file = request.files["file"]
    if file.filename == "": return jsonify({"success": False, "message": "File tidak valid"}), 400
    try:
        save_dir = os.path.join("secure_data", "comparisons")
        os.makedirs(save_dir, exist_ok=True)
        safe_filename_base = secure_filename(file.filename)
        ext = safe_filename_base.rsplit(".", 1)[1].lower() if "." in safe_filename_base else "bin"
        safe_filename = f"{ticket_id}_{uuid.uuid4().hex[:8]}.{ext}"
        file.save(os.path.join(save_dir, safe_filename))
        web_file_path = f"/api/downloads/comparisons/{safe_filename}"

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.cursor().execute("INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES (?, ?, ?, ?)", (ticket_id, str(vendor_name).strip(), float(offered_price), web_file_path))
            conn.commit()
        return jsonify({"success": True, "message": "Dokumen pembanding berhasil diunggah"}), 200
    except Exception as e: return jsonify({"success": False, "message": str(e)}), 500

@app.route("/api/downloads/comparisons/<filename>")
def download_comparison(filename):
    if "username" not in session: return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    return send_from_directory(os.path.join(app.root_path, "secure_data", "comparisons"), secure_filename(filename))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    app.run(host="0.0.0.0", port=port, debug=True)