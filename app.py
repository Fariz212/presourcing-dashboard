from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import sqlite3
import json

app = Flask(__name__)
CORS(app) 

# --- KONFIGURASI DATABASE ---
DB_NAME = 'presourcing_db'

@app.route('/')
def index():
    return render_template('presourcing-dashboard.html')

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dashboard_state (
            id INTEGER PRIMARY KEY,
            data_type TEXT UNIQUE,
            json_data TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

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
    app.run(host='0.0.0.0', port=5000, debug=True)