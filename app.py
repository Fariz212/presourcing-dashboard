from flask import Flask, request, jsonify, render_template, session, redirect, url_for, send_file, send_from_directory
from flask_cors import CORS
import pandas as pd
import sqlite3
import json
import os
import io
import uuid
from datetime import datetime
import contextlib # Tambahan untuk auto-close koneksi database

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
CORS(app) 

app.secret_key = 'presourcing_secret_key_123'
DB_NAME = 'presourcing_db.sqlite'

# --- ROUTING HALAMAN HTML ---
@app.route('/')
def index():
    if 'username' not in session or session.get('role') != 'admin':
        return redirect(url_for('login_page'))
    return render_template('presourcing-dashboard.html')

@app.route('/login')
def login_page():
    if 'username' in session:
        return redirect(url_for('index') if session.get('role') == 'admin' else url_for('sa_portal'))
    return render_template('login.html')

@app.route('/portal')
def sa_portal():
    if 'username' not in session:
        return redirect(url_for('login_page'))
    return render_template('sa-portal.html')

# --- INISIALISASI DATABASE ---
def migrate_existing_requests():
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute("SELECT * FROM requests WHERE status != 'unassigned'")
        ongoing_requests = cursor.fetchall()
        
        if not ongoing_requests:
            return

        cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
        row = cursor.fetchone()
        projects_list = json.loads(row[0]) if row and row[0] else []
        
        existing_ids = {p['id'] for p in projects_list}
        updated = False
        
        for req in ongoing_requests:
            if req['ticket_id'] not in existing_ids:
                cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (req['ticket_id'],))
                items = cursor.fetchall()
                
                formatted_items = []
                for it in items:
                    formatted_items.append({
                        "id": f"item_{it['id']}",
                        "product": it['description'],
                        "qty": it['quantity'],
                        "vendor": it['vendor'] or "",
                        "picIds": [req['pic_username'] or "Admin"],
                        "sphAwal": None,
                        "sphFinal": None
                    })
                    
                current_date = datetime.now().strftime('%Y-%m-%d')
                new_entry = {
                    "id": req['ticket_id'],
                    "name": f"{req['title']} ({req['client_name'] or 'Klien Umum'})",
                    "requestorName": req['requester_username'],
                    "requestorDept": "Presales Team",
                    "priority": "High",
                    "status": req['status'],
                    "leadId": req['pic_username'] or "Admin",
                    "sphMode": "item",
                    "projectSphAwal": None,
                    "projectSphFinal": None,
                    "createdAt": req['created_at'][:10] if req['created_at'] else current_date,
                    "closedAt": None,
                    "sows": [{
                        "id": f"sow_{req['ticket_id']}",
                        "name": "General Scope of Work",
                        "boqs": [{
                            "id": f"boq_{req['ticket_id']}",
                            "name": "BoQ Lampiran SA",
                            "items": formatted_items
                        }]
                    }]
                }
                projects_list.insert(0, new_entry)
                updated = True
                
        if updated:
            cursor.execute('''
                INSERT INTO dashboard_state (data_type, json_data) VALUES ('projects', ?)
                ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data
            ''', (json.dumps(projects_list),))
            conn.commit()
    
def init_db():
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_state (
                id INTEGER PRIMARY KEY,
                data_type TEXT UNIQUE,
                json_data TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                full_name TEXT NOT NULL,
                department TEXT,
                role TEXT NOT NULL
            )
        ''')
        
        cursor.execute('''
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
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS request_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                sow_name TEXT DEFAULT 'General Scope',
                boq_section TEXT DEFAULT 'General Items',
                item_no TEXT,
                description TEXT NOT NULL,
                preferred_brand TEXT,
                quantity INTEGER,
                uom TEXT,
                delivery_time TEXT,
                vendor TEXT,
                FOREIGN KEY (ticket_id) REFERENCES requests(ticket_id)
            )
        ''')

        cursor.execute('''
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_user TEXT NOT NULL,
            message TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
        
        # Inject default users
        for user_data in [
            ('admin', 'admin123', 'Admin Presourcing', 'Presourcing Control', 'admin'),
            ('master', 'master123', 'Master Admin', 'System Control', 'admin'),
            ('tester', 'tester123', 'QA Tester', 'Testing Team', 'sa')
        ]:
            cursor.execute("SELECT COUNT(*) FROM users WHERE username = ?", (user_data[0],))
            if cursor.fetchone()[0] == 0:
                cursor.execute('''
                    INSERT INTO users (username, password, full_name, department, role) 
                    VALUES (?, ?, ?, ?, ?)
                ''', user_data)
                
        conn.commit()
    migrate_existing_requests()

init_db()

# --- API ENDPOINTS (AUTENTIKASI) ---
@app.route('/api/register', methods=['POST'])
def register():
    payload = request.json
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (username, password, full_name, department, role) 
                VALUES (?, ?, ?, ?, ?)
            ''', (payload.get('username'), payload.get('password'), payload.get('full_name'), payload.get('department', ''), payload.get('role', 'sa')))
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
            session['username'] = user[0]
            session['full_name'] = user[1]
            session['department'] = user[2]
            session['role'] = user[3]
            return jsonify({"success": True, "user": {"username": user[0], "full_name": user[1], "department": user[2], "role": user[3]}}), 200
        
        return jsonify({"success": False, "message": "Username atau Password salah!"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear() 
    return jsonify({"success": True, "message": "Berhasil logout"})

# --- API ENDPOINTS (NOTIFIKASI) ---

# 1. Ambil daftar notifikasi berdasarkan target user (admin atau username SA)
@app.route('/api/notifications', methods=['GET'])
def get_notifications():
    target_user = request.args.get('username')
    if not target_user:
        return jsonify({"success": False, "message": "Target user diperlukan"}), 400

    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Ambil 20 notifikasi terbaru untuk user tersebut (atau untuk admin)
            cursor.execute('''
                SELECT * FROM notifications 
                WHERE target_user = ? OR target_user = 'broadcast'
                ORDER BY created_at DESC LIMIT 20
            ''', (target_user,))
            
            notifs = [dict(row) for row in cursor.fetchall()]
            return jsonify({"success": True, "data": notifs}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# 2. Tandai notifikasi sudah dibaca
@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
def mark_notification_read(notif_id):
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE notifications SET is_read = 1 WHERE id = ?
            ''', (notif_id,))
            conn.commit()
            return jsonify({"success": True, "message": "Notifikasi ditandai dibaca"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- API ENDPOINTS (REQUEST & TICKETING) ---
@app.route('/api/requests', methods=['POST'])
def create_request():
    payload = request.json
    ticket_id = f"REQ-{datetime.now().strftime('%y%m')}-{uuid.uuid4().hex[:4].upper()}"
    
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO requests (
                    ticket_id, title, client_name, competitor_info, 
                    sla_date, notes, requester_username, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, 'unassigned')
            ''', (
                ticket_id, payload.get('title'), payload.get('client_name'),      
                payload.get('competitor_info'), payload.get('sla_date'), 
                payload.get('notes'), payload.get('requester_username')
            ))
            # --- TRIGGER NOTIFIKASI KE ADMIN ---
            cursor.execute('''
                INSERT INTO notifications (target_user, message) 
                VALUES ('admin', ?)
            ''', (f"Request Baru: {ticket_id} dari @{payload.get('requester_username')}",))
            conn.commit()
            return jsonify({"success": True, "message": "Request berhasil dibuat", "ticket_id": ticket_id}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/requests', methods=['GET'])
def get_requests():
    username = request.args.get('username')
    role = request.args.get('role')
    
    if role != 'admin' and not username:
        return jsonify({"success": False, "message": "Username diperlukan"}), 400

    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            if role == 'admin':
                cursor.execute('''
                    SELECT r.*, u.full_name, u.department 
                    FROM requests r 
                    LEFT JOIN users u ON r.requester_username = u.username 
                    ORDER BY r.created_at DESC
                ''')
            else:
                cursor.execute('''
                    SELECT r.*, u.full_name, u.department 
                    FROM requests r 
                    LEFT JOIN users u ON r.requester_username = u.username 
                    WHERE r.requester_username = ?
                ''', (username,))
                
            requests_data = [dict(row) for row in cursor.fetchall()]
            
            cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
            json_row = cursor.fetchone()
            
            if json_row and json_row['json_data']:
                admin_projects = json.loads(json_row['json_data'])
                admin_map = {p['id']: p for p in admin_projects}
                
                for req in requests_data:
                    ticket_id = req['ticket_id']
                    if ticket_id in admin_map:
                        req['status'] = admin_map[ticket_id].get('status', req['status'])
                        req['leadId'] = admin_map[ticket_id].get('leadId', '')
                    else:
                        req['leadId'] = ''
            else:
                for req in requests_data:
                    req['leadId'] = ''

            return jsonify({"success": True, "data": requests_data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/upload_boq', methods=['POST'])
def upload_boq():
    ticket_id = request.form.get('ticket_id')
    if not ticket_id or 'file' not in request.files:
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "Nama file kosong"}), 400

    try:
        df = pd.read_excel(file).fillna("")
        required_columns = ["Item No", "Deskripsi Item", "Qty"]
        for col in required_columns:
            if col not in df.columns:
                 return jsonify({"success": False, "message": f"Kolom wajib '{col}' tidak ditemukan"}), 400

        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            for index, row in df.iterrows():
                sow_name = str(row.get("Scope of Work (Opsional)", "")).strip() or "General Scope"
                boq_section = str(row.get("Bill of Quantity (Opsional)", "")).strip() or "General Items"
                vendor = str(row.get("Vendor (Opsional)", "")).strip()
                vendor = vendor if vendor and vendor != "-" else None

                cursor.execute('''
                    INSERT INTO request_items (
                        ticket_id, sow_name, boq_section, item_no, description, 
                        preferred_brand, quantity, uom, delivery_time, vendor
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    ticket_id, sow_name, boq_section, str(row.get("Item No", "")), 
                    row.get("Deskripsi Item", ""), row.get("Preferred Brand", ""), 
                    row.get("Qty", 0), row.get("UoM", ""), row.get("Delivery Time (RFS)", ""), vendor
                ))
            conn.commit()
            return jsonify({"success": True, "message": "File BoQ berhasil diunggah!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# Endpoint ini melayani SA maupun Admin (Duplikat sebelumnya sudah dihapus)
@app.route('/api/request_items/<ticket_id>', methods=['GET'])
def get_request_items(ticket_id):
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
            items_list = [dict(row) for row in cursor.fetchall()]
            return jsonify({"success": True, "data": items_list}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/requests/assign', methods=['POST'])
def assign_ticket():
    payload = request.json
    ticket_id = payload.get('ticket_id')
    pic_username = payload.get('pic_username')
    
    if not ticket_id or not pic_username:
        return jsonify({"success": False, "message": "Ticket ID dan PIC harus diisi!"}), 400
        
    try:
        # PERBAIKAN: Menggunakan 1 koneksi saja (atomic transaction) alih-alih conn dan conn2
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE requests SET pic_username = ?, status = 'ongoing' WHERE ticket_id = ?
            ''', (pic_username, ticket_id))
            
            cursor.execute('''
                SELECT r.*, u.full_name, u.department 
                FROM requests r 
                LEFT JOIN users u ON r.requester_username = u.username 
                WHERE r.ticket_id = ?
            ''', (ticket_id,))
            req = cursor.fetchone()
            
            cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
            items = cursor.fetchall()
            
            if req:
                cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
                row = cursor.fetchone()
                projects_list = json.loads(row[0]) if row and row[0] else []
                
                formatted_items = [{"id": f"item_{it['id']}", "product": it['description'], "qty": it['quantity'], "vendor": it['vendor'] or "", "picIds": [pic_username], "sphAwal": None, "sphFinal": None} for it in items]
                
                requestor_display_name = req['full_name'] if req['full_name'] else req['requester_username']
                requestor_dept = req['department'] if req['department'] else "Presales Team"
                
                new_project_entry = {
                    "id": req['ticket_id'], "name": f"{req['title']} ({req['client_name'] or 'Klien Umum'})",
                    "requestorName": requestor_display_name, "requestorDept": requestor_dept,
                    "priority": "High", "status": "ongoing", "leadId": pic_username, "sphMode": "item",
                    "projectSphAwal": None, "projectSphFinal": None,
                    "createdAt": req['created_at'][:10] if req['created_at'] else datetime.now().strftime('%Y-%m-%d'),
                    "closedAt": None,
                    "sows": [{"id": f"sow_{req['ticket_id']}", "name": "General Scope of Work", "boqs": [{"id": f"boq_{req['ticket_id']}", "name": "BoQ Lampiran SA", "items": formatted_items}]}]
                }
                
                existing_idx = next((i for i, p in enumerate(projects_list) if p['id'] == req['ticket_id']), -1)
                if existing_idx >= 0:
                    projects_list[existing_idx]['requestorName'] = requestor_display_name
                    projects_list[existing_idx]['requestorDept'] = requestor_dept
                else:
                    projects_list.insert(0, new_project_entry)
                    
                cursor.execute('''
                    INSERT INTO dashboard_state (data_type, json_data) VALUES ('projects', ?)
                    ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data
                ''', (json.dumps(projects_list),))
                # --- TRIGGER NOTIFIKASI KE SA ---
                cursor.execute('''
                    INSERT INTO notifications (target_user, message) 
                    VALUES (?, ?)
                ''', (req['requester_username'], f"Tiket {ticket_id} sudah di-assign ke PIC: {pic_username}"))
                
            conn.commit()
            return jsonify({"success": True, "message": "Tiket berhasil di-assign!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/presourcing', methods=['GET'])
def get_data():
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
            row_proj = cursor.fetchone()
            cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'team'")
            row_team = cursor.fetchone()
            return jsonify({"projects": json.loads(row_proj[0]) if row_proj else [], "team": json.loads(row_team[0]) if row_team else []}), 200
    except Exception:
        return jsonify({"projects": [], "team": []}), 500

@app.route('/api/presourcing', methods=['POST'])
def save_data():
    payload = request.json
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO dashboard_state (data_type, json_data) VALUES ('projects', ?) ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data", (json.dumps(payload.get('projects', [])),))
            cursor.execute("INSERT INTO dashboard_state (data_type, json_data) VALUES ('team', ?) ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data", (json.dumps(payload.get('team', [])),))
            conn.commit()
            return jsonify({"message": "Data saved successfully"}), 200
    except Exception as e:
        return jsonify({"message": str(e)}), 500

@app.route('/api/download_report', methods=['GET'])
def download_report():
    if 'username' not in session or session.get('role') != 'admin':
        return jsonify({"success": False, "message": "Akses ditolak!"}), 403
        
    target_project_id = request.args.get('project_id') 
    
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
        row = cursor.fetchone()
        projects = json.loads(row[0]) if row and row[0] else []
    
    if target_project_id:
        projects = [p for p in projects if p.get('id') == target_project_id]
    
    report_data = []
    for p in projects:
        for sow in p.get('sows', []):
            for boq in sow.get('boqs', []):
                for item in boq.get('items', []):
                    report_data.append({
                        "Ticket ID": p.get('id', ''), "Nama Project": p.get('name', ''),
                        "Requestor": p.get('requestorName', ''), "PIC Assigned": p.get('leadId', ''),
                        "Status": p.get('status', ''), "Tanggal Dibuat": p.get('createdAt', ''),
                        "Scope of Work": sow.get('name', ''), "BoQ Section": boq.get('name', ''),
                        "Deskripsi Item": item.get('product', ''), "Qty": item.get('qty', 0),
                        "Vendor": item.get('vendor', ''), "SPH Awal": item.get('sphAwal', ''), "SPH Final": item.get('sphFinal', '')
                    })
    
    if not report_data:
        report_data.append({"Ticket ID": target_project_id or "-", "Nama Project": "Data tidak ditemukan"})
        
    df = pd.DataFrame(report_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Detail Project')
    output.seek(0)
    
    filename = f"Report_{target_project_id if target_project_id else 'All_Projects'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=filename)

@app.route('/api/revisi_boq', methods=['POST'])
def revisi_boq():
    ticket_id = request.form.get('ticket_id')
    if 'file' not in request.files or not ticket_id:
        return jsonify({"success": False, "message": "File atau Ticket ID tidak valid"}), 400
        
    file = request.files['file']
    try:
        df = pd.read_excel(file).fillna("")
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
            old_items = {row['description'].strip().lower(): dict(row) for row in cursor.fetchall()}
            descriptions_in_new_excel = set()
            
            for index, row in df.iterrows():
                desc_raw = str(row.get("Deskripsi Item", "")).strip()
                if not desc_raw: continue
                    
                desc_key = desc_raw.lower()
                descriptions_in_new_excel.add(desc_key)
                qty, uom, vendor, item_no = row.get("Qty", 0), row.get("UoM", ""), row.get("Vendor (Opsional)", ""), str(row.get("Item No", ""))
                
                if desc_key in old_items:
                    cursor.execute("UPDATE request_items SET quantity = ?, uom = ?, vendor = ?, item_no = ? WHERE id = ?", (qty, uom, vendor, item_no, old_items[desc_key]['id']))
                else:
                    cursor.execute("INSERT INTO request_items (ticket_id, description, quantity, uom, vendor, item_no) VALUES (?, ?, ?, ?, ?, ?)", (ticket_id, desc_raw, qty, uom, vendor, item_no))
                    
            for old_desc_key, old_data in old_items.items():
                if old_desc_key not in descriptions_in_new_excel:
                    cursor.execute("DELETE FROM request_items WHERE id = ?", (old_data['id'],))
                    
            cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
            json_row = cursor.fetchone()
            if json_row and json_row['json_data']:
                projects = json.loads(json_row['json_data'])
                for p in projects:
                    if p['id'] == ticket_id:
                        if not p.get('sows'): p['sows'] = [{'id': f"sow_{uuid.uuid4().hex[:6]}", 'name': 'SoW Utama', 'boqs': [{'id': f"boq_{uuid.uuid4().hex[:6]}", 'name': 'BoQ Utama', 'items': []}]}]
                        json_old_items_map = {str(it.get('product', '')).strip().lower(): it for it in p['sows'][0]['boqs'][0]['items']}
                        updated_json_items = []
                        
                        for index, row in df.iterrows():
                            desc_raw = str(row.get("Deskripsi Item", "")).strip()
                            if not desc_raw: continue
                            desc_key = desc_raw.lower()
                            qty, vendor = row.get("Qty", 0), row.get("Vendor (Opsional)", "")
                            
                            if desc_key in json_old_items_map:
                                existing_item = json_old_items_map[desc_key]
                                existing_item.update({"qty": qty, "uom": str(row.get("UoM", "")), "vendor": vendor})
                                updated_json_items.append(existing_item)
                            else:
                                updated_json_items.append({"id": f"item_{uuid.uuid4().hex[:8]}", "product": desc_raw, "qty": qty, "uom": str(row.get("UoM", "")), "vendor": vendor, "picIds": [], "sphAwal": None, "sphFinal": None, "notes": ""})
                        
                        p['sows'][0]['boqs'][0]['items'] = updated_json_items
                        cursor.execute("UPDATE dashboard_state SET json_data = ? WHERE data_type = 'projects'", (json.dumps(projects),))
                        break
            conn.commit()
            return jsonify({"success": True, "message": "BoQ berhasil direvisi!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- API ENDPOINTS (DOKUMEN PEMBANDING / AUDIT TRAIL) ---
@app.route('/api/upload_comparison', methods=['POST'])
def upload_comparison():
    ticket_id = request.form.get('ticket_id')
    vendor_name = request.form.get('vendor_name')
    offered_price = request.form.get('offered_price')
    
    # Validasi input
    if 'file' not in request.files or not ticket_id or not vendor_name or not offered_price:
        return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
        
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "File tidak valid"}), 400
        
    try:
        # 1. Simpan di luar folder static agar tidak bisa diakses publik
        save_dir = os.path.join('secure_data', 'comparisons')
        os.makedirs(save_dir, exist_ok=True)
        
        # 2. Update URL path untuk frontend
        ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'bin'
        safe_filename = f"{ticket_id}_{uuid.uuid4().hex[:8]}.{ext}"
        file_path = os.path.join(save_dir, safe_filename)
        file.save(file_path)
        
        web_file_path = f"/api/downloads/comparisons/{safe_filename}"
        
        # 3. Simpan file ke sistem
        file.save(file_path)
        
        # Path yang akan disimpan di database untuk diakses via web
        web_file_path = f"/static/uploads/comparisons/{safe_filename}"
        
        # 4. Update JSON dashboard_state di database
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
            row = cursor.fetchone()
            
            if row and row['json_data']:
                projects = json.loads(row['json_data'])
                updated = False
                
                # Cari project berdasarkan ticket_id dan injeksi data pembanding
                for p in projects:
                    if p['id'] == ticket_id:
                        # Pastikan array comparison_docs ada
                        if 'comparison_docs' not in p:
                            p['comparison_docs'] = []
                        
                        p['comparison_docs'].append({
                            "vendor_name": vendor_name.strip(),
                            "offered_price": float(offered_price),
                            "file_path": web_file_path
                        })
                        updated = True
                        break
                        
                if updated:
                    cursor.execute('''
                        UPDATE dashboard_state 
                        SET json_data = ? 
                        WHERE data_type = 'projects'
                    ''', (json.dumps(projects),))
                    conn.commit()
                    return jsonify({"success": True, "message": "Dokumen pembanding berhasil diunggah"}), 200
                else:
                    return jsonify({"success": False, "message": "Project tidak ditemukan di dashboard"}), 404
            else:
                return jsonify({"success": False, "message": "Data project kosong"}), 404
                
    except Exception as e:
        return jsonify({"success": False, "message": f"Terjadi kesalahan server: {str(e)}"}), 500

# --- ENDPOINT DOWNLOAD SPH PEMBANDING (SECURE) ---
@app.route('/api/downloads/comparisons/<filename>')
def download_comparison(filename):
    if 'username' not in session:
        return jsonify({"success": False, "message": "Akses ditolak! Silakan login."}), 403
        
    secure_dir = os.path.join(app.root_path, 'secure_data', 'comparisons')
    return send_from_directory(secure_dir, filename)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)