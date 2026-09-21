from flask import Flask, request, jsonify, render_template, session
from flask_cors import CORS
import sqlite3
import json
import os

app = Flask(__name__)
CORS(app) 

# Kunci rahasia untuk session (wajib untuk sistem login)
app.secret_key = 'presourcing_secret_key_123'

# --- KONFIGURASI DATABASE ---
DB_NAME = 'presourcing_db.sqlite'

@app.route('/')
def index():
    return render_template('presourcing-dashboard.html')

@app.route('/login')
def login_page():
    return render_template('login.html')

@app.route('/portal')
def sa_portal():
    return render_template('sa-portal.html')

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Tabel state dashboard (yang sudah ada)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_state (
            id INTEGER PRIMARY KEY,
            data_type TEXT UNIQUE,
            json_data TEXT
        )
    ''')
    
    # Tabel BARU: users (untuk sistem Login & Profil Lengkap)
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
    
    # Inject user default (Admin) jika belum ada, untuk jaga-jaga saat testing pertama kali
    cursor.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
    if cursor.fetchone()[0] == 0:
        cursor.execute('''
            INSERT INTO users (username, password, full_name, department, role) 
            VALUES ('admin', 'admin123', 'Admin Presourcing', 'Presourcing Control', 'admin')
        ''')
        
    conn.commit()
    conn.close()

init_db()

# --- API ENDPOINTS UNTUK AUTENTIKASI ---

@app.route('/api/register', methods=['POST'])
def register():
    payload = request.json
    username = payload.get('username')
    password = payload.get('password')
    full_name = payload.get('full_name')
    department = payload.get('department', '')
    role = payload.get('role', 'sa') # Default role adalah SA
    
    if not username or not password or not full_name:
        return jsonify({"success": False, "message": "Username, Password, dan Nama Lengkap wajib diisi!"}), 400
        
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (username, password, full_name, department, role) 
            VALUES (?, ?, ?, ?, ?)
        ''', (username, password, full_name, department, role))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Registrasi berhasil!"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"success": False, "message": "Username sudah terdaftar!"}), 400

@app.route('/api/login', methods=['POST'])
def login():
    payload = request.json
    username = payload.get('username')
    password = payload.get('password')
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, full_name, department, role FROM users WHERE username = ? AND password = ?", (username, password))
    user = cursor.fetchone()
    conn.close()
    
    if user:
        # Jika login berhasil, kembalikan profil user untuk disimpan di browser (frontend)
        user_data = {
            "username": username,
            "full_name": user[1],
            "department": user[2],
            "role": user[3]
        }
        return jsonify({"success": True, "user": user_data}), 200
    else:
        return jsonify({"success": False, "message": "Username atau Password salah!"}), 401


# --- API ENDPOINTS UNTUK DATA DASHBOARD (Tetap Dipertahankan) ---

@app.route('/api/presourcing', methods=['GET'])
def get_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
    row_proj = cursor.fetchone()
    
    cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'team'")
    row_team = cursor.fetchone()
    
    conn.close()

    projects_data = json.loads(row_proj[0]) if row_proj else []
    team_data = json.loads(row_team[0]) if row_team else []
    
    return jsonify({
        "projects": projects_data,
        "team": team_data
    }), 200

@app.route('/api/presourcing', methods=['POST'])
def save_data():
    payload = request.json
    projects_data = payload.get('projects', [])
    team_data = payload.get('team', [])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO dashboard_state (data_type, json_data) 
        VALUES ('projects', ?)
        ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data
    ''', (json.dumps(projects_data),))
    
    cursor.execute('''
        INSERT INTO dashboard_state (data_type, json_data) 
        VALUES ('team', ?)
        ON CONFLICT(data_type) DO UPDATE SET json_data=excluded.json_data
    ''', (json.dumps(team_data),))
    
    conn.commit()
    conn.close()
    
    return jsonify({"message": "Data saved successfully"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)