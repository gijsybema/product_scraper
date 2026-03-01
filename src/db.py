import psycopg2
import os
from datetime import date, datetime
from psycopg2 import OperationalError
from typing import Optional, Dict, Any

COOLBLUE_RETAILER_ID = 1  # adjust if needed

def get_connection():
    """
    Connect to Postgres.

    - On Railway: uses DATABASE_URL provided by the platform
    - Locally: falls back to DB_CONFIG (existing config dict)
    """
    database_url = os.getenv("DATABASE_URL")

    try:
        if database_url:
            # 'require' is a safe default for managed Postgres providers
            return psycopg2.connect(database_url, sslmode="require")

        # Only import DB_CONFIG if we actually need it
        from src.config import DB_CONFIG
        
        if not DB_CONFIG:
            raise RuntimeError("Local DB_CONFIG is not set. Set DB_* env vars for local dev.")
        
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
            ON CONFLICT (product_id, scraped_at) 
            DO UPDATE SET
                price = EXCLUDED.price,
                availability = EXCLUDED.availability,
                rating = EXCLUDED.rating,
                review_count = EXCLUDED.review_count;
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


def insert_daily_price_drops(conn) -> int:
    """
    Insert all daily price drops (today vs previous measurement)
    into price_drops table.
    Returns number of inserted rows.
    """

    sql = """
    WITH ranked AS (
      SELECT
        ph.product_id,
        ph.scraped_at,
        ph.price,
        LAG(ph.price) OVER (PARTITION BY ph.product_id ORDER BY ph.scraped_at) AS prev_price,
        LAG(ph.scraped_at) OVER (PARTITION BY ph.product_id ORDER BY ph.scraped_at) AS prev_date
      FROM price_history ph
    ),
    latest AS (
      SELECT *
      FROM ranked
      WHERE scraped_at = CURRENT_DATE
    )
    INSERT INTO price_drops (
      product_id,
      new_scraped_at,
      old_scraped_at,
      old_price,
      new_price,
      price_diff,
      drop_percentage,
      rule
    )
    SELECT
      l.product_id,
      l.scraped_at AS new_scraped_at,
      l.prev_date AS old_scraped_at,
      l.prev_price AS old_price,
      l.price AS new_price,
      (l.prev_price - l.price) AS price_diff,
      ROUND(((l.prev_price - l.price) / l.prev_price) * 100, 2) AS drop_percentage,
      'daily_drop'
    FROM latest l
    JOIN products p ON p.id = l.product_id
    WHERE p.active = TRUE
      AND l.prev_price IS NOT NULL
      AND l.prev_price > 0 AND l.price > 0
      AND l.price < l.prev_price
    ON CONFLICT (product_id, new_scraped_at, rule) DO NOTHING;
    """

    with conn.cursor() as cur:
        cur.execute(sql)
        return cur.rowcount

# ----------------------------
# retry logic
# ----------------------------
def create_scrape_run(conn, job_name: str, total_products: int, retry_attempt: int=0) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO scrape_runs (job_name, total_products, status, retry_attempt)
            VALUES (%s, %s, 'running', %s)
            RETURNING id
            """,
            (job_name, total_products, retry_attempt),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id

def finish_scrape_run(
    conn,
    run_id: int,
    status: str,
    success_count: int,
    failed_count: int,
    blocked_count: int = 0,
    next_retry_at: Optional[datetime] = None,
    last_error: Optional[str] = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE scrape_runs
            SET finished_at = NOW(),
                status = %s,
                success_count = %s,
                failed_count = %s,
                blocked_count = %s,
                next_retry_at = %s,
                last_error = %s
            WHERE id = %s
            """,
            (status, success_count, failed_count, blocked_count, next_retry_at, last_error, run_id),
        )
    conn.commit()

def get_due_retry_run(conn, job_name: str) -> Optional[Dict[str, Any]]:
    """
    Returns the most recent run that has next_retry_at due, else None.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, retry_attempt
            FROM scrape_runs
            WHERE job_name = %s
            AND next_retry_at IS NOT NULL
            AND next_retry_at <= NOW()
            AND status IN ('failed','blocked','partial')
            AND DATE(started_at) = DATE(NOW())   -- 👈 same-day guard
            AND finished_at IS NOT NULL
            ORDER BY next_retry_at ASC
            LIMIT 1
            """,
            (job_name,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0],
            "retry_attempt": row[1],
        }

def clear_next_retry(conn, run_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE scrape_runs SET next_retry_at = NULL WHERE id = %s",
            (run_id,),
        )
    conn.commit()
