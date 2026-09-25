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

app = Flask(__name__)
# Proteksi memori server: Batasi maksimal upload file 16MB
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

# --- INISIALISASI DATABASE (VERSI RELASIONAL) ---
def init_db():
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        cursor = conn.cursor()
        
        # Tabel legacy (tetap digunakan untuk fallback tim)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS dashboard_state (
                id INTEGER PRIMARY KEY,
                data_type TEXT UNIQUE,
                json_data TEXT
            )
        ''')
        
        # Tabel sistem dan user
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

        # --- STRUKTUR TABEL RELASIONAL PRESOURCING V2 ---
        cursor.execute('''
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
                closed_at TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sows (
                id TEXT PRIMARY KEY,
                project_id TEXT,
                name TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS boqs (
                id TEXT PRIMARY KEY,
                sow_id TEXT,
                name TEXT,
                FOREIGN KEY(sow_id) REFERENCES sows(id) ON DELETE CASCADE
            )
        ''')
        
        cursor.execute('''
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
                FOREIGN KEY(boq_id) REFERENCES boqs(id) ON DELETE CASCADE
            )
        ''')

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS comparison_docs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id TEXT,
                vendor_name TEXT,
                offered_price REAL,
                file_path TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
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

    def migrate_json_to_relational():
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Cek apakah tabel projects sudah ada isinya
        cursor.execute("SELECT COUNT(*) FROM projects")
        if cursor.fetchone()[0] > 0:
            return # Sudah ada data, abaikan migrasi agar tidak duplikat
            
        # Ambil data JSON lama dari dashboard_state
        cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
        row = cursor.fetchone()
        if not row or not row['json_data']:
            return
            
        projects_list = json.loads(row['json_data'])
        
        # Masukkan data JSON tersebut ke tabel relasional baru secara otomatis
        for p in projects_list:
            cursor.execute('''
                INSERT OR IGNORE INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, project_sph_awal, project_sph_final, created_at, closed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                p.get('id'), p.get('name'), p.get('requestorName'), p.get('requestorDept'), 
                p.get('priority'), p.get('status'), p.get('leadId'), p.get('sphMode'), 
                p.get('projectSphAwal'), p.get('projectSphFinal'), p.get('createdAt'), p.get('closedAt')
            ))

            for sow in p.get('sows', []):
                cursor.execute("INSERT OR IGNORE INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow.get('id'), p.get('id'), sow.get('name')))
                for boq in sow.get('boqs', []):
                    cursor.execute("INSERT OR IGNORE INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq.get('id'), sow.get('id'), boq.get('name')))
                    for it in boq.get('items', []):
                        cursor.execute('''
                            INSERT OR IGNORE INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            it.get('id'), boq.get('id'), it.get('product'), it.get('qty'), it.get('uom'), 
                            it.get('vendor'), it.get('sphAwal'), it.get('sphFinal'), it.get('notes'), json.dumps(it.get('picIds', []))
                        ))

            for doc in p.get('comparison_docs', []):
                cursor.execute('''
                    INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path)
                    VALUES (?, ?, ?, ?)
                ''', (p.get('id'), doc.get('vendor_name'), doc.get('offered_price'), doc.get('file_path')))
                
        conn.commit()
        print("Migrasi data JSON lama ke tabel relasional berhasil!")

init_db()

# --- HELPER: AMBIL DATA RELASIONAL MENJADI JSON ---
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
        projects_data.append(p)
    return projects_data

# --- API ENDPOINTS (AUTENTIKASI & NOTIFIKASI) ---
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
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM notifications WHERE target_user = ? OR target_user = 'broadcast' ORDER BY created_at DESC LIMIT 20", (target,))
        return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]}), 200

@app.route('/api/notifications/<int:notif_id>/read', methods=['POST'])
def mark_notification_read(notif_id):
    with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
        conn.cursor().execute('UPDATE notifications SET is_read = 1 WHERE id = ?', (notif_id,))
        conn.commit()
        return jsonify({"success": True})

# --- API ENDPOINTS (REQUEST & TICKETING) ---
@app.route('/api/requests', methods=['POST'])
def create_request():
    payload = request.json
    # ID Tiket disederhanakan: REQ-YYMM-XXXX
    ticket_id = f"REQ-{datetime.now().strftime('%y%m')}-{uuid.uuid4().hex[:4].upper()}"
    try:
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO requests (ticket_id, title, client_name, competitor_info, sla_date, notes, requester_username, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'unassigned')
            ''', (ticket_id, payload.get('title'), payload.get('client_name'), payload.get('competitor_info'), payload.get('sla_date'), payload.get('notes'), payload.get('requester_username')))
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
            query = "SELECT r.*, u.full_name, u.department FROM requests r LEFT JOIN users u ON r.requester_username = u.username "
            query += "ORDER BY r.created_at DESC" if role == 'admin' else "WHERE r.requester_username = ?"
            cursor.execute(query, () if role == 'admin' else (username,))
            return jsonify({"success": True, "data": [dict(r) for r in cursor.fetchall()]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/upload_boq', methods=['POST'])
def upload_boq():
    ticket_id = request.form.get('ticket_id')
    if not ticket_id or 'file' not in request.files: return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    file = request.files['file']
    try:
        df = pd.read_excel(file).fillna("")
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            cursor = conn.cursor()
            for _, row in df.iterrows():
                cursor.execute('''
                    INSERT INTO request_items (ticket_id, sow_name, boq_section, item_no, description, preferred_brand, quantity, uom, delivery_time, vendor) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (ticket_id, str(row.get("Scope of Work (Opsional)", "")).strip() or "General Scope", 
                      str(row.get("Bill of Quantity (Opsional)", "")).strip() or "General Items", str(row.get("Item No", "")), 
                      row.get("Deskripsi Item", ""), row.get("Preferred Brand", ""), row.get("Qty", 0), 
                      row.get("UoM", ""), row.get("Delivery Time (RFS)", ""), str(row.get("Vendor (Opsional)", "")).strip() or None))
            conn.commit()
            return jsonify({"success": True, "message": "File BoQ berhasil diunggah!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

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
                    
                    cursor.execute('''INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, created_at)
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', 
                                   (ticket_id, title, req_name, req_dept, 'High', 'ongoing', pic_username, 'item', created))
                    
                    sow_id = f"sow_{ticket_id}"
                    cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow_id, ticket_id, "General Scope of Work"))
                    
                    boq_id = f"boq_{ticket_id}"
                    cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq_id, sow_id, "BoQ Lampiran SA"))
                    
                    cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
                    for it in cursor.fetchall():
                        cursor.execute("INSERT INTO items (id, boq_id, product, qty, uom, vendor, pic_ids) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                       (f"item_{it['id']}", boq_id, it['description'], it['quantity'], it['uom'], it['vendor'] or "", json.dumps([pic_username])))

                cursor.execute("INSERT INTO notifications (target_user, message) VALUES (?, ?)", (req['requester_username'], f"Tiket {ticket_id} sudah di-assign ke PIC: {pic_username}"))
            conn.commit()
            return jsonify({"success": True, "message": "Tiket berhasil di-assign!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- API ENDPOINTS (PRESOURCING CORE V2 RELATIONAL) ---
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
                conn.execute("PRAGMA foreign_keys = ON") # Wajib untuk CASCADE DELETE
                cursor = conn.cursor()
                cursor.execute("REPLACE INTO dashboard_state (data_type, json_data) VALUES ('team', ?)", (json.dumps(team),))

                for p in projects:
                    cursor.execute("DELETE FROM projects WHERE id = ?", (p['id'],)) # Cascade membersihkan SOW, BOQ, dll
                    cursor.execute('''INSERT INTO projects (id, name, requestor_name, requestor_dept, priority, status, lead_id, sph_mode, project_sph_awal, project_sph_final, created_at, closed_at)
                                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                   (p['id'], p.get('name'), p.get('requestorName'), p.get('requestorDept'), p.get('priority'), p.get('status'), p.get('leadId'), p.get('sphMode'), p.get('projectSphAwal'), p.get('projectSphFinal'), p.get('createdAt'), p.get('closedAt')))

                    for sow in p.get('sows', []):
                        cursor.execute("INSERT INTO sows (id, project_id, name) VALUES (?, ?, ?)", (sow['id'], p['id'], sow.get('name')))
                        for boq in sow.get('boqs', []):
                            cursor.execute("INSERT INTO boqs (id, sow_id, name) VALUES (?, ?, ?)", (boq['id'], sow['id'], boq.get('name')))
                            for it in boq.get('items', []):
                                cursor.execute('''INSERT INTO items (id, boq_id, product, qty, uom, vendor, sph_awal, sph_final, notes, pic_ids)
                                                  VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                                               (it['id'], boq['id'], it.get('product'), it.get('qty'), it.get('uom'), it.get('vendor'), it.get('sphAwal'), it.get('sphFinal'), it.get('notes'), json.dumps(it.get('picIds', []))))

                    for doc in p.get('comparison_docs', []):
                        cursor.execute("INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES (?, ?, ?, ?)", 
                                       (p['id'], doc.get('vendor_name'), doc.get('offered_price'), doc.get('file_path')))
                conn.commit()
            return jsonify({"success": True}), 200
        except Exception as e:
            return jsonify({"error": str(e)}), 500

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
                        "Ticket ID": p.get('id', ''), "Nama Project": p.get('name', ''),
                        "Requestor": p.get('requestorName', ''), "PIC Assigned": p.get('leadId', ''),
                        "Status": p.get('status', ''), "Tanggal Dibuat": p.get('createdAt', ''),
                        "Scope of Work": sow.get('name', ''), "BoQ Section": boq.get('name', ''),
                        "Deskripsi Item": item.get('product', ''), "Qty": item.get('qty', 0),
                        "Vendor": item.get('vendor', ''), "SPH Awal": item.get('sphAwal', ''), "SPH Final": item.get('sphFinal', '')
                    })
    if not report_data: report_data.append({"Ticket ID": target_project_id or "-", "Nama Project": "Data tidak ditemukan"})
        
    df = pd.DataFrame(report_data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer: df.to_excel(writer, index=False, sheet_name='Detail Project')
    output.seek(0)
    return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', as_attachment=True, download_name=f"Report_{target_project_id or 'All_Projects'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx")

@app.route('/api/revisi_boq', methods=['POST'])
def revisi_boq():
    ticket_id = request.form.get('ticket_id')
    if 'file' not in request.files or not ticket_id: return jsonify({"success": False, "message": "Data tidak valid"}), 400
    try:
        df = pd.read_excel(request.files['file']).fillna("")
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Revisi tabel presales (request_items)
            cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
            old_req_items = {str(r['description']).strip().lower(): dict(r) for r in cursor.fetchall()}
            new_descs = set()
            for _, row in df.iterrows():
                desc_raw = str(row.get("Deskripsi Item", "")).strip()
                if not desc_raw: continue
                desc_key = desc_raw.lower()
                new_descs.add(desc_key)
                qty, uom, vendor = row.get("Qty", 0), row.get("UoM", ""), row.get("Vendor (Opsional)", "")
                if desc_key in old_req_items:
                    cursor.execute("UPDATE request_items SET quantity=?, uom=?, vendor=? WHERE id=?", (qty, uom, vendor, old_req_items[desc_key]['id']))
                else:
                    cursor.execute("INSERT INTO request_items (ticket_id, description, quantity, uom, vendor) VALUES (?, ?, ?, ?, ?)", (ticket_id, desc_raw, qty, uom, vendor))
            for old_key, old_data in old_req_items.items():
                if old_key not in new_descs: cursor.execute("DELETE FROM request_items WHERE id = ?", (old_data['id'],))
            
            # Revisi tabel presourcing (items) secara relasional
            cursor.execute("SELECT i.* FROM items i JOIN boqs b ON i.boq_id = b.id JOIN sows s ON b.sow_id = s.id WHERE s.project_id = ?", (ticket_id,))
            old_items = {str(r['product']).strip().lower(): dict(r) for r in cursor.fetchall()}
            
            cursor.execute("SELECT b.id FROM boqs b JOIN sows s ON b.sow_id = s.id WHERE s.project_id = ? LIMIT 1", (ticket_id,))
            boq_row = cursor.fetchone()
            if boq_row:
                boq_id = boq_row[0]
                for _, row in df.iterrows():
                    desc_raw = str(row.get("Deskripsi Item", "")).strip()
                    if not desc_raw: continue
                    desc_key = desc_raw.lower()
                    qty, uom, vendor = row.get("Qty", 0), str(row.get("UoM", "")), str(row.get("Vendor (Opsional)", ""))
                    if desc_key in old_items:
                        cursor.execute("UPDATE items SET qty=?, uom=?, vendor=? WHERE id=?", (qty, uom, vendor, old_items[desc_key]['id']))
                    else:
                        cursor.execute("INSERT INTO items (id, boq_id, product, qty, uom, vendor, pic_ids) VALUES (?, ?, ?, ?, ?, ?, ?)", 
                                       (f"item_{uuid.uuid4().hex[:8]}", boq_id, desc_raw, qty, uom, vendor, "[]"))
                for old_key, old_data in old_items.items():
                    if old_key not in new_descs: cursor.execute("DELETE FROM items WHERE id = ?", (old_data['id'],))
            conn.commit()
            return jsonify({"success": True, "message": "BoQ berhasil direvisi!"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

# --- API ENDPOINTS (DOKUMEN PEMBANDING SECURE) ---
@app.route('/api/upload_comparison', methods=['POST'])
def upload_comparison():
    ticket_id, vendor_name, offered_price = request.form.get('ticket_id'), request.form.get('vendor_name'), request.form.get('offered_price')
    if 'file' not in request.files or not ticket_id or not vendor_name or not offered_price: return jsonify({"success": False, "message": "Data tidak lengkap"}), 400
    file = request.files['file']
    if file.filename == '': return jsonify({"success": False, "message": "File tidak valid"}), 400
    try:
        # 1. Simpan di folder secure
        save_dir = os.path.join('secure_data', 'comparisons')
        os.makedirs(save_dir, exist_ok=True)
        safe_filename = f"{ticket_id}_{uuid.uuid4().hex[:8]}.{(file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else 'bin')}"
        file.save(os.path.join(save_dir, safe_filename))
        
        # 2. Catat URL path ke database relasional
        web_file_path = f"/api/downloads/comparisons/{safe_filename}"
        with contextlib.closing(sqlite3.connect(DB_NAME)) as conn:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.cursor().execute("INSERT INTO comparison_docs (project_id, vendor_name, offered_price, file_path) VALUES (?, ?, ?, ?)", 
                                  (ticket_id, vendor_name.strip(), float(offered_price), web_file_path))
            conn.commit()
            return jsonify({"success": True, "message": "Dokumen pembanding berhasil diunggah"}), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/downloads/comparisons/<filename>')
def download_comparison(filename):
    if 'username' not in session: return jsonify({"success": False, "message": "Akses ditolak! Silakan login."}), 403
    return send_from_directory(os.path.join(app.root_path, 'secure_data', 'comparisons'), filename)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)