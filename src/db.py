import psycopg2
from datetime import date
from psycopg2 import OperationalError

from src.config import DB_CONFIG

def get_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except OperationalError as e:
        raise RuntimeError(f"Database connection failed: {e}")
