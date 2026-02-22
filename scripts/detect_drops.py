"""
Daily script to detect price drops and store them in the
detect_drops table in PostgreSQL.

Usage:
    python scripts/detect_drops.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection, insert_daily_price_drops

def main():
    conn = get_connection()
    try:
        inserted = insert_daily_price_drops(conn)
        conn.commit()
        print(f"✅ detect_drops: inserted {inserted} rows into price_drops")
    finally:
        conn.close()

if __name__ == "__main__":
    main()