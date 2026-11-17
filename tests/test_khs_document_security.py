from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO

from flask import Flask

from app.routes import dashboard as dashboard_module
from app.routes.dashboard import dashboard_bp


class DocumentCursor:
    def __init__(self, connection, row=None):
        self.connection = connection
        self.row = row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, query, params=None):
        params = params or ()
        if "FROM khs_documents WHERE id=%s" in query:
            self.row = deepcopy(self.connection.documents.get(params[0]))
        else:
            self.row = None

    def fetchone(self):
        return deepcopy(self.row)


class DocumentConnection:
    def __init__(self, *, khs_exists=True):
        self.khs_exists = khs_exists
        self.documents = {}
        self.audit_entries = []
        self.next_id = 1

    @contextmanager
    def transaction(self):
        yield self

    def cursor(self, row_factory=None):
        return DocumentCursor(self)

    def execute(self, query, params=None):
        params = params or ()
        cursor = DocumentCursor(self)
        if query.startswith("SELECT 1 FROM khs_items"):
            cursor.row = (1,) if self.khs_exists else None
        elif query.startswith("INSERT INTO khs_documents"):
            document_id = self.next_id
            self.next_id += 1
            self.documents[document_id] = {
                "id": document_id,
                "khs_id": params[0],
                "document_type": params[1],
                "original_file_name": params[2],
                "storage_key": params[3],
                "mime_type": params[4],
                "file_sha256": params[5],
            }
            cursor.row = (
                document_id,
                params[1],
                params[2],
                params[4],
                datetime(2026, 11, 17, 9, 0, tzinfo=timezone.utc),
            )
        elif query.startswith("INSERT INTO khs_activity_logs"):
            self.audit_entries.append(params)
        return cursor


class DocumentPool:
    def __init__(self, *, khs_exists=True):
        self.connection_object = DocumentConnection(khs_exists=khs_exists)

    @contextmanager
    def connection(self):
        yield self.connection_object


def make_document_client(monkeypatch, tmp_path, *, khs_exists=True, max_content_length=2 * 1024 * 1024):
    pool = DocumentPool(khs_exists=khs_exists)
    pool.audit_records = []

    def capture_audit(_connection, entity_type, entity_id, action, before, after):
        pool.audit_records.append({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,
            "before": before,
            "after": after,
        })

    monkeypatch.setattr(dashboard_module, "get_db_pool", lambda: pool)
    monkeypatch.setattr(dashboard_module, "_audit", capture_audit)
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        UPLOAD_DIR=tmp_path,
        MAX_CONTENT_LENGTH=max_content_length,
    )
    app.register_blueprint(dashboard_bp, url_prefix="/api/dashboard")
    return app.test_client(), pool


def upload_document(client, payload=b"%PDF-1.7\nverified evidence", filename="evidence.pdf"):
    return client.post(
        "/api/dashboard/khs/KHS-DOC-001/documents",
        data={"document_type": "LP Evidence", "file": (BytesIO(payload), filename)},
        content_type="multipart/form-data",
    )


def test_document_upload_and_download_round_trip_verifies_checksum(monkeypatch, tmp_path):
    client, pool = make_document_client(monkeypatch, tmp_path)
    original = b"%PDF-1.7\nverified evidence"

    uploaded = upload_document(client, original)
    assert uploaded.status_code == 201
    data = uploaded.get_json()["data"]
    stored = pool.connection_object.documents[data["id"]]
    stored_path = tmp_path / stored["storage_key"]

    assert stored_path.is_file()
    assert stored_path.read_bytes() == original
    assert stored["file_sha256"] == sha256(original).hexdigest()
    assert len(pool.audit_records) == 1
    audit_record = pool.audit_records[0]
    assert audit_record["action"] == "DOCUMENT_UPLOADED"
    assert audit_record["after"]["file_sha256"] == sha256(original).hexdigest()
    assert audit_record["after"]["file_size_bytes"] == len(original)

    downloaded = client.get(data["download_url"])
    assert downloaded.status_code == 200
    assert downloaded.data == original
    assert downloaded.headers["X-Document-Integrity"] == "verified"
    assert downloaded.headers["Cache-Control"] == "private, no-store"
    assert downloaded.headers["X-Content-Type-Options"] == "nosniff"
    assert "attachment" in downloaded.headers["Content-Disposition"]


def test_document_download_refuses_tampered_file(monkeypatch, tmp_path):
    client, pool = make_document_client(monkeypatch, tmp_path)
    uploaded = upload_document(client)
    data = uploaded.get_json()["data"]
    stored = pool.connection_object.documents[data["id"]]
    (tmp_path / stored["storage_key"]).write_bytes(b"%PDF-1.7\nchanged after upload")

    downloaded = client.get(data["download_url"])
    assert downloaded.status_code == 409
    assert downloaded.get_json()["code"] == "DOCUMENT_INTEGRITY_MISMATCH"
    assert downloaded.data != b"%PDF-1.7\nchanged after upload"


def test_document_download_fails_closed_when_checksum_is_missing(monkeypatch, tmp_path):
    client, pool = make_document_client(monkeypatch, tmp_path)
    uploaded = upload_document(client)
    data = uploaded.get_json()["data"]
    stored = pool.connection_object.documents[data["id"]]
    stored["file_sha256"] = None

    downloaded = client.get(data["download_url"])
    assert downloaded.status_code == 409
    assert downloaded.get_json()["code"] == "DOCUMENT_INTEGRITY_UNAVAILABLE"


def test_document_download_rejects_storage_path_outside_upload_root(monkeypatch, tmp_path):
    client, pool = make_document_client(monkeypatch, tmp_path)
    uploaded = upload_document(client)
    data = uploaded.get_json()["data"]
    stored = pool.connection_object.documents[data["id"]]
    stored["storage_key"] = "../outside.pdf"

    downloaded = client.get(data["download_url"])
    assert downloaded.status_code == 404
    assert downloaded.get_json()["code"] == "DOCUMENT_UNAVAILABLE"


def test_document_upload_does_not_write_file_for_unknown_khs(monkeypatch, tmp_path):
    client, _pool = make_document_client(monkeypatch, tmp_path, khs_exists=False)
    uploaded = upload_document(client)
    assert uploaded.status_code == 404
    assert not (tmp_path / "khs-documents").exists()
