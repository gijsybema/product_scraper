import psycopg2
from datetime import date, datetime
from psycopg2 import OperationalError

from src.config import DB_CONFIG

COOLBLUE_RETAILER_ID = 1  # adjust if needed

def get_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except OperationalError as e:
        raise RuntimeError(f"Database connection failed: {e}")


def upsert_product(conn, sku: str, product_url: str, details: dict):
    """
    Insert product if it does not exist yet.
    Update name / url if it already exists.

    ON CONFLICT DO UPDATE is used because product metadata (such as name or product URL) 
    can change over time.
    If a product already exists, its name, URL, and active status are
    updated to reflect the latest scraped data, keeping the table idempotent
    and up to date.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO products (
                retailer_id,
                sku,
                name,
                brand,
                product_url,
                active
            )
            VALUES (%s, %s, %s, %s, %s, true)
            ON CONFLICT (retailer_id, sku)
            DO UPDATE SET
                name = EXCLUDED.name,
                product_url = EXCLUDED.product_url,
                active = true,
                brand = COALESCE(products.brand, EXCLUDED.brand);
            """,
            (
                COOLBLUE_RETAILER_ID,
                sku,
                details["name"],
                details.get("brand"),
                product_url,
            ),
        )


def upsert_price_history(conn, product_id: int, scraped_at: datetime, price: float, availability: bool, rating: float, review_count: int):
    """
    Insert price history if it does not exist yet.
    Update price history if it already exists.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO price_history (
                product_id,
                scraped_at,
                price,
                availability,
                rating,
                review_count
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (product_id, scraped_at) DO NOTHING;
            """,
            (
                product_id,
                scraped_at,
                price,
                availability,
                rating,
                review_count
            ),
        )


def get_products_to_scrape():
    """
    Get all active products to scrape from the products table.
    Returns a list of dicts with 'product_id' and 'product_url'.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, product_url FROM products WHERE active = true")
            products = cur.fetchall()
        return [{"product_id": product[0], "product_url": product[1]} for product in products]
    finally:
        conn.close()
