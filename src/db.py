import psycopg2
from config import DB_CONFIG
from datetime import date
from psycopg2 import OperationalError

def get_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except OperationalError as e:
        raise RuntimeError(f"Database connection failed: {e}")

def insert_retailer(conn, name, base_url):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO retailers (name, base_url)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
            RETURNING id;
            """,
            (name, base_url)
        )

        row = cur.fetchone()
        if row:
            return row[0]

        # already existed → fetch id (get or create principle)
        cur.execute(
            "SELECT id FROM retailers WHERE name = %s;",
            (name,)
        )
        return cur.fetchone()[0]

def insert_product(conn, retailer_id, sku, brand, name, product_url):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO products (retailer_id, sku, brand, name, product_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (retailer_id, sku) DO NOTHING
            RETURNING id;
            """,
            (retailer_id, sku, brand, name, product_url)
        )
        row = cur.fetchone()

        if row:
            return row[0]

        # already existed → fetch id  (get or create principle)
        cur.execute(
            """
            SELECT id FROM products
            WHERE retailer_id = %s AND sku = %s;
            """,
            (retailer_id, sku)
        )
        return cur.fetchone()[0]

def insert_price(conn, product_id, price, availability, scraped_at=None):
    scraped_at = scraped_at or date.today()

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO price_history (product_id, price, availability, scraped_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (product_id, scraped_at) DO NOTHING;
            """,
            (product_id, price, availability, scraped_at)
        )

