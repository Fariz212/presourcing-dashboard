import sqlite3
import shutil
import os

# Nama database sudah disesuaikan
DB_FILE = 'presourcing_db.sqlite' 
BACKUP_FILE = 'presourcing_db_backup.sqlite'

def migrate_database():
    # 1. PROSES BACKUP
    if os.path.exists(DB_FILE):
        shutil.copy2(DB_FILE, BACKUP_FILE)
        print(f"✅ Backup berhasil: '{DB_FILE}' disalin ke '{BACKUP_FILE}'")
    else:
        print(f"❌ File database '{DB_FILE}' tidak ditemukan! Pastikan nama file benar dan script berada di folder yang sama.")
        return

    # 2. PROSES MIGRASI (Penambahan Kolom & Tabel)
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    try:
        print("Memeriksa tabel 'requests'...")
        
        # Tambah kolom client_name (Pakai try-except agar tidak error jika dijalankan 2x)
        try:
            cursor.execute("ALTER TABLE requests ADD COLUMN client_name TEXT;")
            print("✅ Kolom 'client_name' berhasil ditambahkan.")
        except sqlite3.OperationalError:
            print("⚡ Kolom 'client_name' sudah ada, dilewati.")

        # Tambah kolom competitor_info
        try:
            cursor.execute("ALTER TABLE requests ADD COLUMN competitor_info TEXT;")
            print("✅ Kolom 'competitor_info' berhasil ditambahkan.")
        except sqlite3.OperationalError:
            print("⚡ Kolom 'competitor_info' sudah ada, dilewati.")

        print("Memeriksa tabel 'request_items'...")
        # Buat tabel BoQ baru dengan konsep Smart Fallback
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS request_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id TEXT NOT NULL,
                sow_name TEXT DEFAULT 'General Scope',
                boq_section TEXT DEFAULT 'General Items',
                item_no INTEGER,
                description TEXT NOT NULL,
                preferred_brand TEXT,
                quantity INTEGER,
                uom TEXT,
                delivery_time TEXT,
                vendor TEXT,
                FOREIGN KEY (ticket_id) REFERENCES requests(ticket_id)
            )
        ''')
        print("✅ Tabel 'request_items' berhasil disiapkan.")
        
        conn.commit()
        print("🎉 Migrasi database selesai dengan aman tanpa kehilangan data!")

    except Exception as e:
        print(f"❌ Terjadi kesalahan saat migrasi: {e}")
        conn.rollback() # Batalkan perubahan jika terjadi error di tengah jalan
    finally:
        conn.close()

if __name__ == '__main__':
    migrate_database()