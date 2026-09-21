from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime

app = Flask(__name__)
CORS(app) 

app.secret_key = 'presourcing_secret_key_123'
DB_NAME = 'presourcing_db.sqlite'

# --- ROUTING HALAMAN HTML ---
@app.route('/')
def index():
    return render_template('presourcing-dashboard.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/portal')
def sa_portal():
    return render_template('sa-portal.html')

# --- INISIALISASI DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Tabel state dashboard lama (JSON)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_state (
            id INTEGER PRIMARY KEY,
            data_type TEXT UNIQUE,
            json_data TEXT
        )
    ''')
    
    # 2. Tabel Users (Sistem Login)
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
    
    # 3. Tabel Requests (Diperbarui: Tambah client_name & competitor_info)
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

    # 4. Tabel BARU: Request Items (Untuk detail BoQ Excel)
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
    
    # Inject user admin default
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO users (username, password, full_name, department, role) 
            VALUES ('admin', 'admin123', 'Admin Presourcing', 'Presourcing Control', 'admin')
        ''')
        
    conn.commit()
    conn.close()

init_db()

# --- API ENDPOINTS (AUTENTIKASI) ---
@app.route('/api/register', methods=['POST'])
def register():
    payload = request.json
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password, full_name, department, role) 
            VALUES (?, ?, ?, ?, ?)
        ''', (payload.get('username'), payload.get('password'), payload.get('full_name'), payload.get('department', ''), payload.get('role', 'sa')))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Registrasi berhasil!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Username sudah terdaftar!"}), 400

@app.route('/api/login', methods=['POST'])
def login():
    payload = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT username, full_name, department, role FROM users WHERE username = ? AND password = ?", 
                   (payload.get('username'), payload.get('password')))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        return jsonify({"success": True, "user": {"username": user[0], "full_name": user[1], "department": user[2], "role": user[3]}}), 200
    return jsonify({"success": False, "message": "Username atau Password salah!"}), 401


# --- API ENDPOINTS (REQUEST & TICKETING) ---

# 1. SA Membuat Request Baru (Diperbarui untuk client_name & competitor_info)
@app.route('/api/requests', methods=['POST'])
def create_request():
    payload = request.json
    timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
    ticket_id = f"REQ-{timestamp_str}" 
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO requests (
            ticket_id, title, client_name, competitor_info, 
            sla_date, notes, requester_username, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 'unassigned')
    ''', (
        ticket_id, 
        payload.get('title'), 
        payload.get('client_name'),      
        payload.get('competitor_info'),  
        payload.get('sla_date'), 
        payload.get('notes'), 
        payload.get('requester_username')
    ))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Request berhasil dibuat", "ticket_id": ticket_id}), 201

# 2. Mengambil Data Request
@app.route('/api/requests', methods=['GET'])
def get_requests():
    username = request.args.get('username')
    role = request.args.get('role')
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row 
    cursor = conn.cursor()
    
    if role == 'admin':
        cursor.execute("SELECT * FROM requests ORDER BY created_at DESC")
    else:
        cursor.execute("SELECT * FROM requests WHERE requester_username = ? ORDER BY created_at DESC", (username,))
        
    rows = cursor.fetchall()
    conn.close()
    
    requests_list = [dict(row) for row in rows]
    return jsonify({"success": True, "data": requests_list}), 200

# 3. SA Mengunggah File BoQ Excel (Dengan Smart Fallback)
@app.route('/api/upload_boq', methods=['POST'])
def upload_boq():
    ticket_id = request.form.get('ticket_id')
    if not ticket_id:
        return jsonify({"success": False, "message": "Ticket ID tidak ditemukan"}), 400

    if 'file' not in request.files:
        return jsonify({"success": False, "message": "Tidak ada file yang diunggah"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"success": False, "message": "Nama file kosong"}), 400

    try:
        df = pd.read_excel(file).fillna("")

        required_columns = ["Item No", "Deskripsi Item", "Qty"]
        for col in required_columns:
            if col not in df.columns:
                 return jsonify({"success": False, "message": f"Kolom wajib '{col}' tidak ditemukan di Excel"}), 400

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()

        for index, row in df.iterrows():
            item_no = str(row.get("Item No", ""))
            description = row.get("Deskripsi Item", "")
            quantity = row.get("Qty", 0)
            uom = row.get("UoM", "")
            preferred_brand = row.get("Preferred Brand", "")
            delivery_time = row.get("Delivery Time (RFS)", "")
            
            sow_name_raw = str(row.get("Scope of Work (Opsional)", "")).strip()
            sow_name = sow_name_raw if sow_name_raw != "" else "General Scope"

            boq_section_raw = str(row.get("Bill of Quantity (Opsional)", "")).strip()
            boq_section = boq_section_raw if boq_section_raw != "" else "General Items"

            vendor_raw = str(row.get("Vendor (Opsional)", "")).strip()
            vendor = vendor_raw if vendor_raw != "" and vendor_raw != "-" else None

            cursor.execute('''
                INSERT INTO request_items (
                    ticket_id, sow_name, boq_section, item_no, description, 
                    preferred_brand, quantity, uom, delivery_time, vendor
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                ticket_id, sow_name, boq_section, item_no, description, 
                preferred_brand, quantity, uom, delivery_time, vendor
            ))
        
        conn.commit()
        return jsonify({"success": True, "message": "File BoQ berhasil diunggah dan disimpan ke database!"}), 200

    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        return jsonify({"success": False, "message": f"Terjadi kesalahan saat memproses file: {str(e)}"}), 500
    finally:
        if 'conn' in locals():
            conn.close()

# API untuk SA melihat daftar item BoQ yang sudah di-upload berdasarkan ticket_id
@app.route('/api/request_items/<ticket_id>', methods=['GET'])
def get_request_items(ticket_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items_list = [dict(row) for row in rows]
    return jsonify({"success": True, "data": items_list}), 200

# API untuk Master Assign
# 1. API untuk Admin Mengambil Detail Item BoQ berdasarkan ticket_id
@app.route('/api/request_items/<ticket_id>', methods=['GET'])
def get_request_items_admin(ticket_id):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
    rows = cursor.fetchall()
    conn.close()
    
    items_list = [dict(row) for row in rows]
    return jsonify({"success": True, "data": items_list}), 200

# 2. API untuk Admin Assign PIC & Update Status Tiketexit
# 2. API untuk Admin Assign PIC & Update Status Tiket
@app.route('/api/requests/assign', methods=['POST'])
def assign_ticket():
    payload = request.json
    ticket_id = payload.get('ticket_id')
    pic_username = payload.get('pic_username')
    
    if not ticket_id or not pic_username:
        return jsonify({"success": False, "message": "Ticket ID dan PIC harus diisi!"}), 400
        
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # 1. Update status di tabel requests
    cursor.execute('''
        UPDATE requests 
        SET pic_username = ?, status = 'ongoing' 
        WHERE ticket_id = ?
    ''', (pic_username, ticket_id))
    
    # Ambil detail request yang baru di-assign
    cursor.execute("SELECT * FROM requests WHERE ticket_id = ?", (ticket_id,))
    req = cursor.fetchone()
    
    # Ambil item BoQ terkait
    cursor.execute("SELECT * FROM request_items WHERE ticket_id = ?", (ticket_id,))
    items = cursor.fetchall()
    
    conn.commit()
    conn.close()
    
    # 2. Sinkronkan juga ke dashboard_state (projects) agar langsung terbaca oleh script.js
    if req:
        conn2 = sqlite3.connect(DB_NAME)
        cursor2 = conn2.cursor()
        cursor2.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
        row = cursor2.fetchone()
        
        projects_list = json.loads(row[0]) if row and row[0] else []
        
        # Konversi item BoQ ke format yang dibaca script.js
        formatted_items = []
        for it in items:
            formatted_items.append({
                "id": f"item_{it['id']}",
                "product": it['description'],
                "qty": it['quantity'],
                "vendor": it['vendor'] or "",
                "picIds": [pic_username],
                "sphAwal": None,
                "sphFinal": None
            })
            
        # Menggunakan datetime Python standar untuk tanggal hari ini
        current_date = datetime.now().strftime('%Y-%m-%d')
        
        new_project_entry = {
            "id": req['ticket_id'],
            "name": f"{req['title']} ({req['client_name'] or 'Klien Umum'})",
            "requestorName": req['requester_username'],
            "requestorDept": "Presales Team",
            "priority": "High", 
            "status": "ongoing",
            "leadId": pic_username,
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
        
        # Masukkan ke list projects jika belum ada
        if not any(p['id'] == req['ticket_id'] for p in projects_list):
            projects_list.insert(0, new_project_entry)
            
        cursor2.execute('''
            INSERT INTO dashboard_state (data_type, json_data) VALUES ('projects', ?)
            ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data
        ''', (json.dumps(projects_list),))
        
        conn2.commit()
        conn2.close()

    return jsonify({"success": True, "message": "Tiket berhasil di-assign dan disinkronkan ke dashboard!"}), 200

# --- API ENDPOINTS (DASHBOARD LAMA) ---
@app.route('/api/presourcing', methods=['GET'])
def get_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
    row_proj = cursor.fetchone()
    cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'team'")
    row_team = cursor.fetchone()
    conn.close()
    return jsonify({"projects": json.loads(row_proj[0]) if row_proj else [], "team": json.loads(row_team[0]) if row_team else []}), 200

@app.route('/api/presourcing', methods=['POST'])
def save_data():
    payload = request.json
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''INSERT INTO dashboard_state (data_type, json_data) VALUES ('projects', ?)
                      ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data''', (json.dumps(payload.get('projects', [])),))
    cursor.execute('''INSERT INTO dashboard_state (data_type, json_data) VALUES ('team', ?)
                      ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data''', (json.dumps(payload.get('team', [])),))
    conn.commit()
    conn.close()
    return jsonify({"message": "Data saved successfully"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5001))
    app.run(host='0.0.0.0', port=port, debug=True)