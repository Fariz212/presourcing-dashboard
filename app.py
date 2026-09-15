from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json

app = Flask(__name__)
# CORS ini wajib agar file HTML (frontend) diizinkan mengambil data dari Backend Python ini
CORS(app) 

# ==== MASUKKAN KREDENSIAL MYSQL KAMU DI SINI ====
DB_HOST = 'localhost'         # <-- Ubah jadi localhost karena DB ada di server yang sama
DB_USER = 'admin_presourcing'             # <-- Sesuai user yang kita buat tadi
DB_PASS = 'Presourcing@123^'  # <-- Sesuai password yang kita buat tadi
DB_NAME = 'presourcing_db'    # <-- Sesuai nama database tadi
# ===================================================

# Fungsi untuk menyiapkan tabel SQL
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Kita membuat 1 tabel SQL sederhana bernama `dashboard_state`.
    # Struktur JSON akan disimpan utuh di kolom text/json agar frontend tetap bisa berjalan tanpa rombak total.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_state (
            id INTEGER PRIMARY KEY,
            data_type TEXT UNIQUE,
            json_data TEXT
        )
    ''')
    conn.commit()
    conn.close()

# Jalankan inisialisasi tabel SQL saat aplikasi nyala
init_db()

# API Endpoint untuk Mengambil Data (GET)
@app.route('/api/presourcing', methods=['GET'])
def get_data():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'projects'")
    row_proj = cursor.fetchone()
    
    cursor.execute("SELECT json_data FROM dashboard_state WHERE data_type = 'team'")
    row_team = cursor.fetchone()
    
    conn.close()

    # Jika database kosong, kembalikan array kosong agar JS Frontend memakai SeedData
    projects_data = json.loads(row_proj[0]) if row_proj else []
    team_data = json.loads(row_team[0]) if row_team else []
    
    return jsonify({
        "projects": projects_data,
        "team": team_data
    }), 200

# API Endpoint untuk Menyimpan Data (POST)
@app.route('/api/presourcing', methods=['POST'])
def save_data():
    payload = request.json
    projects_data = payload.get('projects', [])
    team_data = payload.get('team', [])
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Gunakan metode UPSERT (Update/Insert) SQL
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
    # Jalankan server di port 5000
    app.run(debug=True, host='0.0.0.1', port=5000)