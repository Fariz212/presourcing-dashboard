from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file, send_from_directory
from flask_cors import CORS
import pandas as pd
import sqlite3
import json
import os
import io
import uuid
from datetime import datetime
import contextlib
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app) 

app.secret_key = 'presourcing_secret_key_123'
DB_NAME = 'presourcing_db.sqlite'

# --- KONFIGURASI TEMPLATE EXCEL ---
BOQ_CORE_COLUMNS = ["Item No", "Deskripsi Item", "Qty", "UoM", "Preferred Brand", "Delivery Time (RFS)"]
BOQ_OPTIONAL_COLUMNS = ["Scope of Work (Opsional)", "Bill of Quantity (Opsional)", "Vendor (Opsional)"]
BOQ_SYSTEM_COLUMN = "Item ID (System)"
BOQ_TEMPLATE_FILENAME = "Template_BoQ_Presourcing_Final.xlsx"

# --- HELPER: EXCEL PARSER ---
def _excel_text(value):
    """Normalisasi cell Excel tanpa NaN dan tanpa trailing .0 yang tidak perlu."""
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
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValueError("Qty harus berupa angka.")
    if number < 0:
        raise ValueError("Qty tidak boleh negatif.")
    return number

def _read_boq_excel(file, require_system_id=False):
    """Membaca SHEET 1 / index 0 saja."""
    file.stream.seek(0)
    df = pd.read_excel(file, sheet_name=0)
    df.columns = [_excel_text(col) for col in df.columns]

    missing = [col for col in BOQ_CORE_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError("Format template tidak sesuai. Kolom wajib tidak ditemukan: " + ", ".join(missing))

    if require_system_id and BOQ_SYSTEM_COLUMN not in df.columns:
        raise ValueError(f"Kolom '{BOQ_SYSTEM_COLUMN}' wajib ada untuk file revisi.")
    if BOQ_SYSTEM_COLUMN not in df.columns:
        df[BOQ_SYSTEM_COLUMN] = ""

    for col in BOQ_OPTIONAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df.fillna("")

def _parse_boq_rows(df):
    rows, issues, seen_ids = [], [], {}
    for excel_idx, row in df.iterrows():
        excel_row = excel_idx + 2
        description = _excel_text(row.get("Deskripsi Item"))
        
        # Baris kosong dianggap padding template.
        if not description: continue

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
        if not uom: issues.append({"row": excel_row, "severity": "warning", "message": "UoM kosong."})

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
            "vendor": _excel_text(row.get("Vendor (Opsional)"))
        })

    # Auto-number hanya kalau Item No memang kosong.
    for idx, item in enumerate(rows, start=1):
        if not item["itemNo"]: item["itemNo"] = str(idx)
    return rows, issues

# --- ROUTING HALAMAN HTML ---
@app.route('/')
def index():
    if 'username' not in session or session.get('role') != 'admin': return redirect(url_for('login_page'))
    return render_template('presourcing-dashboard.html')

@app.route('/login')
def login_page():
    if 'username' in session: return redirect(url_for('index') if session.get('role') == 'admin' else url_for('sa_portal'))
    return render_template('login.html')

@app.route('/portal')
def sa_portal():
    if 'username' not in session: return redirect(url_for('login_page'))
    return render_template('sa-portal.html')

# --- INISIALISASI DATABASE ---
def init_db():
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''CREATE TABLE IF NOT EXISTS dashboard_state (id INTEGER PRIMARY KEY, data_type TEXT UNIQUE, json_data TEXT)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, full_name TEXT NOT NULL, department TEXT, role TEXT NOT NULL)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS requests (id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT UNIQUE NOT NULL, title TEXT NOT NULL, client_name TEXT, competitor_info TEXT, sla_date TEXT NOT NULL, notes TEXT, status TEXT DEFAULT 'unassigned', requester_username TEXT NOT NULL, pic_username TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS request_items (id INTEGER PRIMARY KEY AUTOINCREMENT, ticket_id TEXT NOT NULL, sow_name TEXT DEFAULT 'General Scope', boq_section TEXT DEFAULT 'General Items', item_no TEXT, description TEXT NOT NULL, preferred_brand TEXT, quantity INTEGER, uom TEXT, delivery_time TEXT, vendor TEXT, FOREIGN KEY (ticket_id) REFERENCES requests(ticket_id) ON DELETE CASCADE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS notifications (id INTEGER PRIMARY KEY AUTOINCREMENT, target_user TEXT NOT NULL, message TEXT NOT NULL, is_read INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS projects (id TEXT PRIMARY KEY, name TEXT, requestor_name TEXT, requestor_dept TEXT, priority TEXT, status TEXT, lead_id TEXT, sph_mode TEXT, project_sph_awal REAL, project_sph_final REAL, created_at TEXT, closed_at TEXT, target_rfs TEXT, pipeline_stage TEXT, progress_pct INTEGER)''')
        
        # MIGRATION: Projects Table
        for col, dtype in [('target_rfs', 'TEXT'), ('pipeline_stage', 'TEXT'), ('progress_pct', 'INTEGER')]:
            try: cursor.execute(f"ALTER TABLE projects ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError: pass 

        cursor.execute('''CREATE TABLE IF NOT EXISTS sows (id TEXT PRIMARY KEY, project_id TEXT, name TEXT, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS boqs (id TEXT PRIMARY KEY, sow_id TEXT, name TEXT, FOREIGN KEY(sow_id) REFERENCES sows(id) ON DELETE CASCADE)''')
        cursor.execute('''CREATE TABLE IF NOT EXISTS items (id TEXT PRIMARY KEY, boq_id TEXT, product TEXT, qty REAL, uom TEXT, vendor TEXT, sph_awal REAL, sph_final REAL, notes TEXT, pic_ids TEXT, item_no TEXT, preferred_brand TEXT, delivery_time TEXT, FOREIGN KEY(boq_id) REFERENCES boqs(id) ON DELETE CASCADE)''')
        
        # MIGRATION: Items Table
        for col, dtype in [('item_no', 'TEXT'), ('preferred_brand', 'TEXT'), ('delivery_time', 'TEXT')]:
            try: cursor.execute(f"ALTER TABLE items ADD COLUMN {col} {dtype}")
            except sqlite3.OperationalError: pass
            
        cursor.execute('''CREATE TABLE IF NOT EXISTS comparison_docs (id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT, vendor_name TEXT, offered_price REAL, file_path TEXT, FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)''')
        
        for user_data in [
            ('admin', 'admin123', 'Admin Presourcing', 'Presourcing Control', 'admin'),
            ('master', 'master123', 'Master Admin', 'System Control', 'admin'),
            ('tester', 'tester123', 'QA Tester', 'Testing Team', 'sa')
        ]:
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (user_data[0],))
            if cursor.fetchone()[0] == 0:
                cursor.execute('''INSERT INTO users (username, password, full_name, department, role) VALUES (?, ?, ?, ?, ?)''', user_data)
        conn.commit()

init_db()

# --- HELPER: AMBIL DATA RELASIONAL ---
def get_projects_relational(cursor):
    cursor.execute("SELECT * FROM projects")
    projects_data = []
    for p_row in cursor.fetchall():
        p = dict(p_row)
        
        cursor.execute("SELECT vendor_name, offered_price, file_path FROM comparison_docs WHERE project_id = ?", (p['id'],))
        p['comparison_docs'] = [dict(d) for d in cursor.fetchall()]
        
        cursor.execute("SELECT id, name FROM sows WHERE project_id = ?", (p['id'],))
        sows = []
        for s_row in cursor.fetchall():
            s = dict(s_row)
            cursor.execute("SELECT id, name FROM boqs WHERE sow_id = ?", (s['id'],))
            boqs = []
            for b_row in cursor.fetchall():
                b = dict(b_row)
                cursor.execute("SELECT * FROM items WHERE boq_id = ?", (b['id'],))
                items = []
                for i_row in cursor.fetchall():
                    i = dict(i_row)
                    i['picIds'] = json.loads(i['pic_ids']) if i['pic_ids'] else []
                    i['sphAwal'] = i.pop('sph_awal')
                    i['sphFinal'] = i.pop('sph_final')
                    i['itemNo'] = i.pop('item_no', '')
                    i['preferredBrand'] = i.pop('preferred_brand', '')
                    i['deliveryTime'] = i.pop('delivery_time', '')
                    items.append(i)
                b['items'] = items
                boqs.append(b)
            s['boqs'] = boqs
            sows.append(s)
        p['sows'] = sows
        
        p['requestorName'] = p.pop('requestor_name')
        p['requestorDept'] = p.pop('requestor_dept')
        p['leadId'] = p.pop('lead_id')
        p['sphMode'] = p.pop('sph_mode')
        p['projectSphAwal'] = p.pop('project_sph_awal')
        p['projectSphFinal'] = p.pop('project_sph_final')
        p['createdAt'] = p.pop('created_at')
        p['closedAt'] = p.pop('closed_at')
        p['targetRfs'] = p.pop('target_rfs', None)
        p['pipelineStage'] = p.pop('pipeline_stage', None)
        p['progressPct'] = p.pop('progress_pct', None)

        projects_data.append(p)
    return projects_data

# --- API ENDPOINTS ---
@app.route('/api/register', methods=['POST'])
def register():
    payload = request.json
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO users (username, password, full_name, department, role) VALUES (?, ?, ?, ?, ?)', 
                           (payload.get('username'), payload.get('password'), payload.get('full_name'), payload.get('department', ''), payload.get('role', 'sa')))
            conn.commit()
            return jsonify({"success": True, "message": "Registrasi berhasil!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Username sudah terdaftar!"}), 400

@app.route('/api/login', methods=['POST'])
def login():
    payload = request.json
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT username, full_name, department, role FROM users WHERE username = ? AND password = ?", 
                       (payload.get('username'), payload.get('password')))
        user = cursor.fetchone()
        if user:
            session.update({'username': user[0], 'full_name': user[1], 'department': user[2], 'role': user[3]})
            return jsonify({"success": True, "user": {"username": user[0], "full_name": user[1], "department": user[2], "role": user[3]}}), 200
        return jsonify({"success": False, "message": "Username atau Password salah!"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear() 
    return jsonify({"success": True, "message": "Berhasil logout"})

@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    target = request.args.get('username')
    if not target: return jsonify({"success": False, "message": "Target user diperlukan"}), 400
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            if target == 'admin':
                cursor.execute("SELECT id, name, target_rfs FROM projects WHERE status = 'ongoing' AND target_rfs IS NOT NULL AND target_rfs != ''")
                ongoing_projects = cursor.fetchall()
                for p in ongoing_projects:
                    try:
                        rfs_date = datetime.strptime(p['target_rfs'], '%Y-%m-%d').date()
                        today = datetime.now().date()
                        days_left = (rfs_date - today).days
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
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
def mark_notification_read(notif_id):
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.cursor().execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (notif_id,))
        conn.commit()
        return jsonify({"success": True})

@app.route('/api/requests', methods=['POST'])
def create_request():
    payload = request.json
    ticket_id = f"REQ-{datetime.now().strftime('%y%m')}-{uuid.uuid4().hex[:4].upper()}"
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute('''INSERT INTO requests (ticket_id, title, client_name, competitor_info, sla_date, notes, requester_username, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'unassigned')''', (ticket_id, payload.get('title'), payload.get('client_name'), payload.get('competitor_info'), payload.get('sla_date'), payload.get('notes'), payload.get('requester_username')))
            cursor.execute("INSERT INTO notifications (target_user, message) VALUES ('admin', ?)", (f"Request Baru: {ticket_id} dari @{payload.get('requester_username')}",))
            conn.commit()
            return jsonify({"success": True, "message": "Request berhasil dibuat", "ticket_id": ticket_id}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/requests', methods=['GET'])
def get_requests():
    username, role = request.args.get('username'), request.args.get('role')
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = """
                SELECT r.*, u.full_name, u.department, p.pipeline_stage, p.progress_pct, p.target_rfs 
                FROM requests r LEFT JOIN users u ON r.requester_username = u.username LEFT JOIN projects p ON r.ticket_id = p.id
            """
            if role != 'admin':
                query += " WHERE r.requester_username = ? ORDER BY r.created_at DESC"
                cursor.execute(query, (username,))
            else:
                query += " ORDER BY r.created_at DESC"
                cursor.execute(query)
            return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/upload_boq', methods=['POST'])
def upload_boq():
    ticket_id = request.form.get('ticket_id')
    if not ticket_id or 'file' not in request.files: return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    file = request.files['file']
    if not file.filename: return jsonify({"success": False, "message": "Nama file tidak valid."}), 400

    try:
        df = _read_boq_excel(file, require_system_id=False)
        rows, issues = _parse_boq_rows(df)

        for item in rows:
            if item["id"]:
                issues.append({"row": item["excelRow"], "severity": "error", "message": f"'{BOQ_SYSTEM_COLUMN}' harus kosong untuk Initial Request."})

        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            return jsonify({"success": False, "message": "Excel memiliki error. Perbaiki file terlebih dahulu.", "issues": issues[:50]}), 400

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM request_items WHERE ticket_id = ?", (ticket_id,))
            for item in rows:
                cursor.execute('''
                    INSERT INTO request_items (ticket_id, sow_name, boq_section, item_no, description, preferred_brand, quantity, uom, delivery_time, vendor)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ticket_id, item["sowName"], item["boqName"], item["itemNo"], item["product"], item["preferredBrand"], item["qty"], item["uom"], item["deliveryTime"], item["vendor"] or None))
            conn.commit()
        return jsonify({"success": True, "message": "File BoQ berhasil diunggah.", "summary": {"items": len(rows), "warnings": sum(1 for issue in issues if issue["severity"] == "warning")}}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400
    
@app.route('/api/request_items/<ticket_id>', methods=['GET'])
def get_request_items(ticket_id):
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
        return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]}), 200

@app.route('/api/requests/assign', methods=['POST'])
def assign_ticket():
    payload = request.json
    ticket_id, pic_username = payload.get('ticket_id'), payload.get('pic_username')
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
                    req_name = req['full_name'] or req['requester_username']
                    req_dept = req['department'] or "Presales Team"
                    title = f"{req['title']} ({req['client_name'] or 'Klien Umum'})"
                    created = req['created_at'][:10] if req['created_at'] else datetime.now().strftime('%Y-%m-%d')
                    sla_date = req['sla_date'] if req['sla_date'] else ""
                    
                    cursor.execute('''INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, created_at, target_rfs, pipeline_stage, progress_pct) 
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                                      (ticket_id, title, req_name, req_dept, 'High', 'ongoing', pic_username, 'item', created, sla_date, '1 - Project Identification', 0))
                    
                    cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
                    req_items = cursor.fetchall()
                    
                    grouped_data = {}
                    for it in req_items:
                        s_name = it['sow_name'] if it['sow_name'] else "General Scope of Work"
                        b_name = it['boq_section'] if it['boq_section'] else "General Items"
                        if s_name not in grouped_data: grouped_data[s_name] = {}
                        if b_name not in grouped_data[s_name]: grouped_data[s_name][b_name] = []
                        grouped_data[s_name][b_name].append(it)
                        
                    for s_name, boqs in grouped_data.items():
                        sow_id = f"sow_{uuid.uuid4().hex[:8]}"
                        cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow_id, ticket_id, s_name))
                        for b_name, items_list in boqs.items():
                            boq_id = f"boq_{uuid.uuid4().hex[:8]}"
                            cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq_id, sow_id, b_name))
                            for it in items_list:
                                cursor.execute('''
                                    INSERT INTO items (
                                        id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                ''', (
                                    f"item_{uuid.uuid4().hex[:8]}", boq_id, it['description'], it['quantity'], it['uom'], it['vendor'] or "",
                                    None, None, "", json.dumps([pic_username]), it['item_no'] or "", it['preferred_brand'] or "", it['delivery_time'] or ""
                                ))

                cursor.execute("INSERT INTO notifications (target_user, message) VALUES (?, ?)", (req['requester_username'], f"Tiket {ticket_id} sudah di-assign ke PIC: {pic_username}"))
            conn.commit()
            return jsonify({"success": True, "message": "Tiket berhasil di-assign!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/presourcing', methods=['GET', 'POST'])
def api_presourcing():
    if request.method == 'GET':
        try:
            with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'team'")
                team_row = cursor.fetchone()
                team = json.loads(team_row['json_data']) if team_row and team_row['json_data'] else []
                projects_data = get_projects_relational(cursor)
                return jsonify({"projects": projects_data, "team": team}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

    if request.method == 'POST':
        data = request.json
        projects, team = data.get('projects', []), data.get('team', [])
        try:
            with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
                conn.execute("PRAGMA foreign_keys = ON")
                cursor = conn.cursor()
                cursor.execute("REPLACE INTO dashboard_state (data_type, json_data) VALUES ('team', ?)", (json.dumps(team),))

                cursor.execute("SELECT id FROM projects")
                existing_db_ids = {row[0] for row in cursor.fetchall()}
                incoming_ids = {p['id'] for p in projects}
                for del_id in (existing_db_ids - incoming_ids):
                    cursor.execute("DELETE FROM projects WHERE id = ?", (del_id,))
                    cursor.execute("DELETE FROM request_items WHERE ticket_id = ?", (del_id,))
                    cursor.execute("DELETE FROM requests WHERE ticket_id = ?", (del_id,))

                for p in projects:
                    cursor.execute("DELETE FROM projects WHERE id = ?", (p['id'],)) 
                    cursor.execute('''INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, project_sph_awal, project_sph_final, created_at, closed_at, target_rfs, pipeline_stage, progress_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (p['id'], p.get('name'), p.get('requestorName'), p.get('requestorDept'), p.get('priority'), p.get('status'), p.get('leadId'), p.get('sphMode'), p.get('projectSphAwal'), p.get('projectSphFinal'), p.get('createdAt'), p.get('closedAt'), p.get('targetRfs'), p.get('pipelineStage'), p.get('progressPct')))

                    for sow in p.get('sows', []):
                        cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow['id'], p['id'], sow.get('name')))
                        for boq in sow.get('boqs', []):
                            cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq['id'], sow['id'], boq.get('name')))
                            for it in boq.get('items', []):
                                cursor.execute('''INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (it['id'], boq['id'], it.get('product'), it.get('qty'), it.get('uom'), it.get('vendor'), it.get('sphAwal'), it.get('sphFinal'), it.get('notes'), json.dumps(it.get('picIds', [])), it.get('itemNo', ''), it.get('preferredBrand', ''), it.get('deliveryTime', '')))

                    for doc in p.get('comparison_docs', []):
                        cursor.execute("INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES (?, ?, ?, ?)", (p['id'], doc.get('vendor_name'), doc.get('offered_price'), doc.get('file_path')))
                conn.commit()
            return jsonify({"success": True}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route('/api/projects/<project_id>/download_boq_template', methods=['GET'])
def download_project_boq_template(project_id):
    if 'username' not in session: return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    try:
        from openpyxl import load_workbook
        from copy import copy
        template_path = os.path.join(app.static_folder, BOQ_TEMPLATE_FILENAME)
        if not os.path.isfile(template_path): return jsonify({"success": False, "message": "Template BoQ tidak ditemukan."}), 404

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT i.item_no, i.product, i.qty, i.uom, i.preferred_brand, i.delivery_time, i.vendor, i.id AS item_id, s.name AS sow_name, b.name AS boq_name
                FROM items i JOIN boqs b ON i.boq_id = b.id JOIN sows s ON b.sow_id = s.id
                WHERE s.project_id = ? ORDER BY s.name, b.name, i.item_no, i.rowid
            """, (project_id,))
            items = [dict(row) for row in cursor.fetchall()]

        wb = load_workbook(template_path)
        ws = wb["BoQ Request"]

        # Clear existing blank/template rows
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, max_col=10):
            for cell in row: cell.value = None

        style_row = min(51, ws.max_row)
        for excel_row, item in enumerate(items, start=2):
            values = [
                item.get("item_no", ""), item.get("product", ""), item.get("qty", 0), item.get("uom", ""),
                item.get("preferred_brand", ""), item.get("delivery_time", ""), item.get("sow_name", ""),
                item.get("boq_name", ""), item.get("vendor", ""), item.get("item_id", "")
            ]

            if excel_row > style_row:
                for col in range(1, 11):
                    source = ws.cell(style_row, col)
                    target = ws.cell(excel_row, col)
                    if source.has_style: target._style = copy(source._style)
                    if source.number_format: target.number_format = source.number_format

            for col, value in enumerate(values, start=1):
                cell = ws.cell(excel_row, col)
                if col == 6 and value:
                    try:
                        cell.value = datetime.strptime(str(value), "%Y-%m-%d").date()
                        cell.number_format = "yyyy-mm-dd"
                    except ValueError: cell.value = value
                else: cell.value = value

        if "BoQInputTable" in ws.tables:
            table_last_row = max(2, len(items) + 1)
            ws.tables["BoQInputTable"].ref = f"A1:J{table_last_row}"

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        return send_file(output, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", as_attachment=True, download_name=f"BoQ_Revisi_{project_id}.xlsx")
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/projects/<project_id>', methods=['DELETE'])
def delete_project(project_id):
    if 'username' not in session: return jsonify({"success": False, "message": "Akses ditolak! Silakan login."}), 403
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
            else:
                return jsonify({"success": False, "message": "Project tidak ditemukan atau sudah terhapus."}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/download_report', methods=['GET'])
def download_report():
    if 'username' not in session or session.get('role') != 'admin': return jsonify({"success": False, "message": "Akses ditolak!"}), 403
    target_project_id = request.args.get('project_id')
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        projects = get_projects_relational(conn.cursor())
    
    if target_project_id: projects = [p for p in projects if p.get('id') == target_project_id]
    report_data = []
    for p in projects:
        for sow in p.get('sows', []):
            for boq in sow.get('boqs', []):
                for item in boq.get('items', []):
                    report_data.append({
                        "Ticket ID": p.get('id', ''), "Nama Project": p.get('name', ''), "Requestor": p.get('requestorName', ''), "PIC Assigned": p.get('leadId', ''), "Status": p.get('status', ''), "Tanggal Dibuat": p.get('createdAt', ''), "Target RFS": p.get('targetRfs', ''), "Pipeline Stage": p.get('pipelineStage', ''), "Item ID": item.get('id', ''), "Item No": item.get('itemNo', ''), "Scope of Work": sow.get('name', ''), "BoQ Section": boq.get('name', ''), "Deskripsi Item": item.get('product', ''), "Qty": item.get('qty', 0), "UoM": item.get('uom', ''), "Preferred Brand": item.get('preferredBrand', ''), "Delivery Time (RFS)": item.get('deliveryTime', ''), "Vendor": item.get('vendor', ''), "SPH Awal": item.get('sphAwal', ''), "SPH Final": item.get('sphFinal', '')
                    })
    if not report_data: report_data.append({"Ticket ID": target_project_id or "-", "Nama Project": "Data tidak ditemukan"})
        
    df = pd.DataFrame(report_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False, sheet_name='Detail Project')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f"Report_{target_project_id or 'All_Projects'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

@app.route('/api/project_import_boq/preview', methods=['POST'])
def preview_project_import_boq():
    if 'file' not in request.files: return jsonify({"success": False, "message": "File Excel tidak ditemukan."}), 400
    file = request.files['file']
    if not file.filename: return jsonify({"success": False, "message": "Nama file tidak valid."}), 400

    try:
        df = _read_boq_excel(file)
        rows, issues = _parse_boq_rows(df)

        for item in rows:
            if item["id"]:
                issues.append({"row": item["excelRow"], "severity": "error", "message": f"'{BOQ_SYSTEM_COLUMN}' harus kosong untuk Project Baru."})

        sows = {}
        for item in rows:
            sow_name = item["sowName"]
            boq_name = item["boqName"]
            if sow_name not in sows: sows[sow_name] = {}
            if boq_name not in sows[sow_name]: sows[sow_name][boq_name] = []
            sows[sow_name][boq_name].append({
                "id": f"item_{uuid.uuid4().hex[:8]}", "itemNo": item["itemNo"], "product": item["product"], "qty": item["qty"], "uom": item["uom"],
                "preferredBrand": item["preferredBrand"], "deliveryTime": item["deliveryTime"], "vendor": item["vendor"], "notes": "", "picIds": [], "sphAwal": None, "sphFinal": None
            })

        result_sows = []
        for sow_name, boq_groups in sows.items():
            sow_obj = {"id": f"sow_{uuid.uuid4().hex[:8]}", "name": sow_name, "boqs": []}
            for boq_name, items in boq_groups.items():
                sow_obj["boqs"].append({"id": f"boq_{uuid.uuid4().hex[:8]}", "name": boq_name, "items": items})
            result_sows.append(sow_obj)

        errors = sum(1 for issue in issues if issue["severity"] == "error")
        warnings = sum(1 for issue in issues if issue["severity"] == "warning")
        total_items = sum(len(boq["items"]) for sow in result_sows for boq in sow["boqs"])
        total_boqs = sum(len(sow["boqs"]) for sow in result_sows)

        return jsonify({
            "success": True,
            "data": {
                "summary": {"rows": len(df), "items": total_items, "sows": len(result_sows), "boqs": total_boqs, "errors": errors, "warnings": warnings},
                "issues": issues[:50], "has_errors": errors > 0, "sows": result_sows
            }
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

def _revision_items_for_project(cursor, ticket_id):
    cursor.execute("""
        SELECT i.*, b.name AS boq_name, s.name AS sow_name FROM items i
        JOIN boqs b ON i.boq_id = b.id JOIN sows s ON b.sow_id = s.id
        WHERE s.project_id = ?
    """, (ticket_id,))
    return [dict(row) for row in cursor.fetchall()]

@app.route('/api/revisi_boq/preview', methods=['POST'])
def preview_revisi_boq():
    ticket_id = request.form.get('ticket_id')
    if 'file' not in request.files or not ticket_id: return jsonify({"success": False, "message": "Data tidak valid."}), 400

    try:
        df = _read_boq_excel(request.files['file'], require_system_id=True)
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
        def norm(value, is_qty=False):
            if is_qty: return None if value is None or value == "" else float(value)
            return _excel_text(value).lower()

        for item in incoming:
            if not item["id"]:
                added.append({"description": item["product"], "qty": item["qty"], "uom": item["uom"], "vendor": item["vendor"]})
                continue

            old = existing.get(item["id"])
            if not old: continue

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
                ("Vendor", old.get("vendor"), item["vendor"], False)
            ]

            for label, old_value, new_value, is_qty in comparisons:
                if norm(old_value, is_qty) != norm(new_value, is_qty):
                    changes[label] = [_excel_text(old_value), _excel_text(new_value)]

            if changes: updated.append({"id": item["id"], "description": item["product"], "qty": item["qty"], "uom": item["uom"], "vendor": item["vendor"], "changes": changes})
            else: unchanged.append({"id": item["id"], "description": item["product"]})

        removed = [{"id": row["id"], "description": row["product"], "itemNo": row.get("item_no", "")} for item_id, row in existing.items() if item_id not in incoming_ids]
        errors = sum(1 for issue in issues if issue["severity"] == "error")
        warnings = sum(1 for issue in issues if issue["severity"] == "warning")

        return jsonify({"success": True, "data": {"summary": {"added": len(added), "updated": len(updated), "removed": len(removed), "unchanged": len(unchanged), "errors": errors, "warnings": warnings}, "issues": issues[:50], "has_errors": errors > 0, "added": added, "updated": updated, "removed": removed, "unchanged": unchanged}}), 200

    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400
     
@app.route('/api/revisi_boq', methods=['POST'])
def revisi_boq():
    ticket_id = request.form.get('ticket_id')
    if 'file' not in request.files or not ticket_id: return jsonify({"success": False, "message": "Data tidak valid."}), 400

    try:
        df = _read_boq_excel(request.files['file'], require_system_id=True)
        incoming, issues = _parse_boq_rows(df)

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM projects WHERE id = ?", (ticket_id,))
            if not cursor.fetchone(): return jsonify({"success": False, "message": "Project tidak ditemukan."}), 404

            existing_rows = _revision_items_for_project(cursor, ticket_id)
            existing = {str(row["id"]).strip(): row for row in existing_rows if row["id"]}

            validation_errors = list(issues)
            seen_ids = set()

            for item in incoming:
                item_id = item["id"]
                if not item_id: continue
                if item_id in seen_ids: validation_errors.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID duplikat: {item_id}."})
                seen_ids.add(item_id)
                if item_id not in existing: validation_errors.append({"row": item["excelRow"], "severity": "error", "message": f"Item ID '{item_id}' tidak ditemukan di project."})

            if any(issue["severity"] == "error" for issue in validation_errors):
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
                if item_id:
                    old = existing[item_id]
                    incoming_existing_ids.add(item_id)
                    cursor.execute("""
                        UPDATE items SET boq_id = ?, product = ?, qty = ?, uom = ?, vendor = ?, item_no = ?, preferred_brand = ?, delivery_time = ? WHERE id = ?
                    """, (boq_id, item["product"], item["qty"], item["uom"], item["vendor"], item["itemNo"], item["preferredBrand"], item["deliveryTime"], old["id"]))
                else:
                    new_item_id = f"item_{uuid.uuid4().hex[:8]}"
                    cursor.execute("""
                        INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids, item_no, preferred_brand, delivery_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (new_item_id, boq_id, item["product"], item["qty"], item["uom"], item["vendor"], None, None, "", "[]", item["itemNo"], item["preferredBrand"], item["deliveryTime"]))

            for item_id in (set(existing) - incoming_existing_ids):
                cursor.execute("DELETE FROM items WHERE id = ?", (item_id,))

            cursor.execute("DELETE FROM boqs WHERE id NOT IN (SELECT DISTINCT boq_id FROM items)")
            cursor.execute("DELETE FROM sows WHERE id NOT IN (SELECT DISTINCT sow_id FROM boqs)")
            conn.commit()

        return jsonify({"success": True, "message": "BoQ berhasil direvisi!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400

@app.route('/api/download_template_boq', methods=['GET'])
def download_template_boq():
    if 'username' not in session: return jsonify({"success": False, "message": "Akses ditolak. Silakan login."}), 403
    path = os.path.join(app.static_folder, BOQ_TEMPLATE_FILENAME)
    if not os.path.isfile(path): return jsonify({"success": False, "message": f"Template '{BOQ_TEMPLATE_FILENAME}' belum tersedia di folder static."}), 404
    return send_from_directory(app.static_folder, BOQ_TEMPLATE_FILENAME, as_attachment=True, download_name=BOQ_TEMPLATE_FILENAME)
    
@app.route('/api/upload_comparison', methods=['POST'])
def upload_comparison():
    ticket_id, vendor_name, offered_price = request.form.get('ticket_id'), request.form.get('vendor_name'), request.form.get('offered_price')
    if 'file' not in request.files or not ticket_id or not vendor_name or not offered_price: return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"success": False, "message": "File tidak valid"}), 400
    try:
        save_dir = os.path.join('secure_data', 'comparisons')
        os.makedirs(save_dir, exist_ok=True)
        safe_filename_base = secure_filename(file.filename)
        ext = safe_filename_base.rsplit('.', 1)[1].lower() if '.' in safe_filename_base else 'bin'
        safe_filename = f"{ticket_id}_{uuid.uuid4().hex[:8]}.{ext}"
        file.save(os.path.join(save_dir, safe_filename))
        
        web_file_path = f"/api/downloads/comparisons/{safe_filename}"
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.cursor().execute("INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES (?, ?, ?, ?)", (ticket_id, str(vendor_name).strip(), float(offered_price), web_file_path))
            conn.commit()
            return jsonify({"success": True, "message": "Dokumen pembanding berhasil diunggah"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/downloads/comparisons/<filename>')
def download_comparison(filename):
    if 'username' not in session: return jsonify({"success": False, "message": "Akses ditolak! Silakan login."}), 403
    return send_from_directory(os.path.join(app.root_path, 'secure_data', 'comparisons'), secure_filename(filename))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)