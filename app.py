from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
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
    
    # 3. Tabel BARU: Requests (Untuk Ticketing/Inbox System)
    # Sangat fleksibel: Menyimpan detail tiket, status, requester, dan PIC.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE NOT NULL,
            title TEXT NOT NULL,
            sla_date TEXT NOT NULL,
            notes TEXT,
            status TEXT DEFAULT 'unassigned', 
            requester_username TEXT NOT NULL,
            pic_username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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

# 1. SA Membuat Request Baru
@app.route('/api/requests', methods=['POST'])
def create_request():
    payload = request.json
    # Bikin ID Tiket otomatis, contoh: REQ-202609-001
    timestamp_str = datetime.now().strftime("%Y%m%d%H%M%S")
    ticket_id = f"REQ-{timestamp_str}" 
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO requests (ticket_id, title, sla_date, notes, requester_username, status)
        VALUES (?, ?, ?, ?, ?, 'unassigned')
    ''', (ticket_id, payload.get('title'), payload.get('sla_date'), payload.get('notes'), payload.get('requester_username')))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Request berhasil dibuat", "ticket_id": ticket_id}), 201

# 2. Mengambil Data Request (Untuk Portal SA dan Inbox Admin)
@app.route('/api/requests', methods=['GET'])
def get_requests():
    username = request.args.get('username')
    role = request.args.get('role')
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Biar hasilnya berbentuk dictionary (JSON-friendly)
    cursor = conn.cursor()
    
    if role == 'admin':
        # Admin bisa melihat semua tiket
        cursor.execute("SELECT * FROM requests ORDER BY created_at DESC")
    else:
        # SA cuma bisa melihat tiket yang dia buat sendiri
        cursor.execute("SELECT * FROM requests WHERE requester_username = ? ORDER BY created_at DESC", (username,))
        
    rows = cursor.fetchall()
    conn.close()
    
    requests_list = [dict(row) for row in rows]
    return jsonify({"success": True, "data": requests_list}), 200


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