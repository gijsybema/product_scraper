# insert_retailer.py
"""
One off script to store the basic information on retailers 
in the retailers table in PostgreSQL.

Usage:
    python scripts/insert_retailer.py <name> <base_url>

"""

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection

def insert_retailer(name, base_url):
    insert_query = """
        INSERT INTO retailers (name, base_url)
        VALUES (%s, %s)
        ON CONFLICT (name)
        DO UPDATE SET base_url = EXCLUDED.base_url
        RETURNING id;
        """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(insert_query, (name, base_url))
            retailer_id = cur.fetchone()[0]
            conn.commit()
            print(f"✅ Retailer '{name}' has id: {retailer_id}")

    except Exception as e:
        print("Error inserting retailer:", e)

    finally:
        conn.close()

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python scripts/insert_retailer.py <name> <base_url>")
        sys.exit(1)

    retailer_name = sys.argv[1]
    retailer_base_url = sys.argv[2]
    #retailer_name = "Coolblue"
    #retailer_base_url = "https://coolblue.nl"

    insert_retailer(retailer_name, retailer_base_url)


