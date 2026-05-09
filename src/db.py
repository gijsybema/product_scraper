import psycopg2
import os
from datetime import date, datetime
from psycopg2 import OperationalError
from typing import Optional
import json

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
                category,
                product_url,
                image_url,
                all_image_urls,
                slug,
                description,
                specs,
                active
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true)
            ON CONFLICT (retailer_id, sku)
            DO UPDATE SET
                name = EXCLUDED.name,
                category = COALESCE(EXCLUDED.category, products.category),
                product_url = EXCLUDED.product_url,
                image_url = COALESCE(EXCLUDED.image_url, products.image_url),
                all_image_urls = CASE
                    WHEN EXCLUDED.all_image_urls IS NOT NULL
                        AND EXCLUDED.all_image_urls <> '[]'::jsonb
                    THEN EXCLUDED.all_image_urls
                    ELSE products.all_image_urls
                END,
                active = true,
                brand = COALESCE(products.brand, EXCLUDED.brand),
                slug = COALESCE(products.slug, EXCLUDED.slug),
                description = COALESCE(EXCLUDED.description, products.description),
                specs = COALESCE(EXCLUDED.specs, products.specs);
            """,
            (
                COOLBLUE_RETAILER_ID,
                sku,
                details["name"],
                details.get("brand"),
                details.get("category"),
                product_url,
                details.get("image_url"),
                json.dumps(details.get("all_image_urls", [])),
                details.get("slug"),
                details.get("description"),
                json.dumps(details.get("specs")) if details.get("specs") is not None else None,
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


def get_products_to_scrape(missed_only: bool = False):
    """
    Get active products to scrape.
    missed_only=True: only products with no price_history row for today (recovery run).
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            if missed_only:
                cur.execute(
                    """
                    SELECT p.id, p.product_url
                    FROM products p
                    WHERE p.active = true
                      AND NOT EXISTS (
                          SELECT 1 FROM price_history ph
                          WHERE ph.product_id = p.id
                            AND ph.scraped_at = CURRENT_DATE
                      )
                    """
                )
            else:
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
                last_error = %s
            WHERE id = %s
            """,
            (status, success_count, failed_count, blocked_count, last_error, run_id),
        )
    conn.commit()

# With two daily runs (morning + 12:00 recovery), a product that 404s in both
# runs on the same day accumulates 2 hits, so deactivation can occur within
# 2 calendar days instead of 3.
CONSECUTIVE_404_THRESHOLD = 3

def handle_product_404(conn, product_id: int) -> bool:
    """
    Increment consecutive_404s for a product.
    Deactivates it (active=false) when the threshold is reached.
    Returns True if the product was deactivated this call.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE products
            SET consecutive_404s = consecutive_404s + 1,
                active = CASE
                    WHEN consecutive_404s + 1 >= %s THEN false
                    ELSE active
                END
            WHERE id = %s
            RETURNING consecutive_404s, active
            """,
            (CONSECUTIVE_404_THRESHOLD, product_id),
        )
        row = cur.fetchone()
    if row is None:
        return False
    count, active = row
    return not active and count >= CONSECUTIVE_404_THRESHOLD


def reset_404_count(conn, product_id: int) -> None:
    """Reset consecutive_404s to 0 after a successful scrape."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE products SET consecutive_404s = 0 WHERE id = %s AND consecutive_404s > 0",
            (product_id,),
        )


