from flask import current_app
from psycopg_pool import ConnectionPool


def init_db_pool(app):
    """
    Initialize one PostgreSQL connection pool per Flask application.
    The pool opens asynchronously so application startup does not
    depend on the database being immediately available.
    """

    database_url = app.config.get("DATABASE_URL")

    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")

    pool = ConnectionPool(
        conninfo=database_url,
        min_size=app.config["DB_POOL_MIN_SIZE"],
        max_size=app.config["DB_POOL_MAX_SIZE"],
        timeout=app.config["DB_POOL_TIMEOUT"],
        open=False,
        name="khs-monitoring",
    )

    try:
        pool.open(wait=False)
    except Exception:
        pool.close()
        raise

    app.extensions["khs_db_pool"] = pool

    return pool


def get_db_pool():
    pool = current_app.extensions.get("khs_db_pool")

    if pool is None:
        raise RuntimeError("Database connection pool is not initialized.")

    return pool
