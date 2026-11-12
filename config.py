import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY")
    DATABASE_URL = os.getenv("DATABASE_URL")

    UPLOAD_DIR = Path(
        os.getenv("UPLOAD_DIR", str(BASE_DIR / "uploads"))
    ).resolve()

    MAX_CONTENT_LENGTH = int(
        os.getenv("MAX_CONTENT_LENGTH", "16777216")
    )

    DB_POOL_MIN_SIZE = 1
    DB_POOL_MAX_SIZE = 5
    DB_POOL_TIMEOUT = 10

    JSON_SORT_KEYS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
