# src/config.py
import os
from dotenv import load_dotenv
load_dotenv(".env.local")

def _env(name: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(name, default)
    if required and (val is None or val == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val

# If Railway provides DATABASE_URL, we don't need individual DB_* vars
DATABASE_URL = os.getenv("DATABASE_URL")

# Only create DB_CONFIG for LOCAL development
if not DATABASE_URL:
    DB_CONFIG = {
        # psycopg2 accepts dbname or database; "dbname" is the canonical keyword
        "host": _env("DB_HOST", "localhost"),
        "port": int(_env("DB_PORT", "5432")),
        "dbname": _env("DB_NAME", "pricetracker"),
        "user": _env("DB_USER", "postgres"),
        "password": _env("DB_PASSWORD", "", required=True),  # require for safety
    }
else:
    DB_CONFIG = None