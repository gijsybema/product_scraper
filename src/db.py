import psycopg2
from config import DB_CONFIG
from datetime import date

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def insert_retailer(name, base_url):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO retailers (name, base_url)
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
            RETURNING id;
            """,
            (name, base_url)
        )

        result = cur.fetchone()
        conn.commit()
        return result[0] if result else None

    except Exception as e:
        if conn:
            conn.rollback()
        raise e

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def insert_product(retailer_id, sku, brand, name, product_url):
    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO products (retailer_id, sku, brand, name, product_url)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (retailer_id, sku) DO NOTHING
            RETURNING id;
            """,
            (retailer_id, sku, brand, name, product_url)
        )

        result = cur.fetchone()
        conn.commit()
        return result[0] if result else None

    except Exception as e:
        if conn:
            conn.rollback()
        raise e

    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

def insert_price(product_id, price, availability, scraped_at=None):
    if scraped_at is None:
        scraped_at = date.today()

    conn = None
    cur = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO price_history (product_id, price, availability, scraped_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (product_id, scraped_at) DO NOTHING;
            """,
            (product_id, price, availability, scraped_at)
        )
        conn.commit()

    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()