from atexit import register
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import RequestEntityTooLarge


BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env", override=False)

from config import Config
from app.db import init_db_pool
from app.routes.health import health_bp
from app.routes.imports import imports_bp
from app.routes.dashboard import dashboard_bp


def create_app(test_config=None):
    app = Flask(__name__)

    app.config.from_object(Config)

    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY is not configured.")

    if not app.config.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL is not configured.")

    upload_dir = Path(app.config["UPLOAD_DIR"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    app.config["UPLOAD_DIR"] = upload_dir

    pool = init_db_pool(app)
    register(pool.close)

    app.register_blueprint(
        health_bp,
        url_prefix="/health",
    )

    app.register_blueprint(
        imports_bp,
        url_prefix="/api/imports",
    )
    app.register_blueprint(
        dashboard_bp,
        url_prefix="/api/dashboard",
    )

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(_error):
        return jsonify({
            "success": False,
            "message": "Uploaded file exceeds the permitted size.",
        }), 413

    @app.get("/")
    def index():
        # Preserve the original JSON root contract for API clients.
        # Browsers requesting HTML receive the dashboard.
        if request.accept_mimetypes.best == "text/html":
            return render_template("dashboard.html")

        return jsonify({
            "service": "KHS Creation Monitoring",
            "status": "running",
            "health": "/health/live",
            "readiness": "/health/ready",
            "import_preview": "/api/imports/preview",
            "dashboard_summary": "/api/dashboard/summary",
        }), 200

    @app.get("/dashboard")
    def dashboard_page():
        return render_template("dashboard.html")

    return app
