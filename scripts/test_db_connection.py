import sys
from pathlib import Path
# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection

def main():
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1;")
            print("✅ DB connection OK, SELECT 1 returned:", cur.fetchone())
    finally:
        conn.close()

if __name__ == "__main__":
    main()