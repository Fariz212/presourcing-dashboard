from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify

from app.db import get_db_pool


health_bp = Blueprint("health", __name__)


@health_bp.get("/live")
def liveness():
    """
    Process-level health check.
    Does not require a database connection.
    """

    return jsonify({
        "status": "alive",
        "service": "khs-monitoring",
    }), 200


@health_bp.get("/ready")
def readiness():
    """
    Application readiness check.
    Confirms that the application can query its own database.
    """

    try:
        pool = get_db_pool()

        with pool.connection(
            timeout=current_app.config["DB_POOL_TIMEOUT"]
        ) as conn:
            row = conn.execute(
                """
                SELECT
                    current_database(),
                    CURRENT_TIMESTAMP
                """
            ).fetchone()

        database_name, checked_at = row

        if database_name != "khs_monitoring":
            raise RuntimeError("Unexpected database identity.")

        return jsonify({
            "status": "ready",
            "service": "khs-monitoring",
            "database": {
                "status": "connected",
                "name": database_name,
                "checked_at": checked_at.isoformat(),
            },
        }), 200

    except Exception:
        current_app.logger.exception(
            "KHS database readiness check failed."
        )

        return jsonify({
            "status": "not_ready",
            "service": "khs-monitoring",
            "database": {
                "status": "unavailable",
            },
        }), 503
