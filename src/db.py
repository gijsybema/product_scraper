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

    Returns (product_id, ai_description) so callers can check whether an
    AI description still needs to be generated without a separate lookup.
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
                specs = COALESCE(EXCLUDED.specs, products.specs)
            RETURNING id, ai_description;
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
        return cur.fetchone()


def upsert_price_history(conn, product_id: int, scraped_at: datetime, price: float, availability: bool, rating: float, review_count: int):
    """
    Insert price history if it does not exist yet.
    Update price history if it already exists.

    Returns the most recent price recorded for this product before
    scraped_at (or None if this is the first row), so callers can detect
    a price change without a separate query.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH prev AS (
                SELECT price FROM price_history
                WHERE product_id = %s AND scraped_at < %s
                ORDER BY scraped_at DESC LIMIT 1
            )
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
                review_count = EXCLUDED.review_count
            RETURNING (SELECT price FROM prev);
            """,
            (
                product_id,
                scraped_at,
                product_id,
                scraped_at,
                price,
                availability,
                rating,
                review_count
            ),
        )
        row = cur.fetchone()
        return float(row[0]) if row and row[0] is not None else None


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
                    SELECT p.id, p.product_url, p.name, p.brand, p.category
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
                cur.execute("SELECT id, product_url, name, brand, category FROM products WHERE active = true")
            products = cur.fetchall()
        return [
            {
                "product_id": product[0],
                "product_url": product[1],
                "name": product[2],
                "brand": product[3],
                "category": product[4],
            }
            for product in products
        ]
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
# scrape run logging
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
    deactivated_count: int = 0,
    ip_blocked_count: int = 0,
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
                deactivated_count = %s,
                ip_blocked_count = %s,
                last_error = %s
            WHERE id = %s
            """,
            (status, success_count, failed_count, deactivated_count, ip_blocked_count, last_error, run_id),
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


OOS_DEACTIVATION_THRESHOLD = 30  # consecutive calendar days out of stock before deactivation


def deactivate_if_long_term_oos(conn, product_id: int, threshold: int = OOS_DEACTIVATION_THRESHOLD) -> bool:
    """
    Count the number of consecutive OOS days for a product: all scraped days
    with availability=false since the most recent availability=true day (or
    since ever, if the product has never been in stock).

    Deactivates the product (active=false) if the streak reaches `threshold`.
    Returns True if the product was newly deactivated this call.
    Does not commit — caller owns the transaction.

    Re-activation is handled by discover_products.py: if the product reappears
    on a Coolblue category filter page, upsert_product sets active=true again.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(DISTINCT ph.scraped_at) AS consecutive_oos_days
            FROM price_history ph
            WHERE ph.product_id = %s
              AND ph.availability = false
              AND ph.scraped_at > COALESCE(
                  (SELECT MAX(scraped_at)
                   FROM price_history
                   WHERE product_id = %s AND availability = true),
                  '1900-01-01'::date
              )
            """,
            (product_id, product_id),
        )
        row = cur.fetchone()

    if row is None or row[0] < threshold:
        return False

    # Streak has reached threshold — deactivate
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE products SET active = false WHERE id = %s AND active = true RETURNING id",
            (product_id,),
        )
        return cur.fetchone() is not None


def get_price_context(conn, product_id: int) -> Optional[dict]:
    """
    Assemble price context for the AI deal description prompt.

    current_price_since is the start of the current unbroken price streak
    (found via change-point detection over price_history, not just today's
    date). Returns None if there is no distinct prior price to compare
    against (new product, or price has never changed).
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            WITH h AS (
                SELECT
                    scraped_at,
                    price,
                    CASE WHEN price = LAG(price) OVER (ORDER BY scraped_at)
                         THEN 0 ELSE 1 END AS is_change
                FROM price_history
                WHERE product_id = %s
            ),
            grp AS (
                SELECT scraped_at, price,
                       SUM(is_change) OVER (ORDER BY scraped_at) AS grp_id
                FROM h
            ),
            current_streak AS (
                SELECT price AS current_price,
                       MIN(scraped_at) AS current_price_since,
                       MAX(scraped_at) AS latest_date
                FROM grp
                GROUP BY grp_id, price
                ORDER BY latest_date DESC
                LIMIT 1
            )
            SELECT
                cs.current_price,
                cs.current_price_since,
                (SELECT price FROM price_history
                 WHERE product_id = %s AND scraped_at < cs.current_price_since
                 ORDER BY scraped_at DESC LIMIT 1) AS previous_price,
                (SELECT price FROM price_history
                 WHERE product_id = %s AND scraped_at >= cs.latest_date - INTERVAL '90 days'
                 ORDER BY price ASC, scraped_at ASC LIMIT 1) AS low_90d,
                (SELECT scraped_at FROM price_history
                 WHERE product_id = %s AND scraped_at >= cs.latest_date - INTERVAL '90 days'
                 ORDER BY price ASC, scraped_at ASC LIMIT 1) AS low_90d_date,
                (SELECT price FROM price_history
                 WHERE product_id = %s AND scraped_at >= cs.latest_date - INTERVAL '30 days'
                 ORDER BY price ASC, scraped_at ASC LIMIT 1) AS low_30d,
                (SELECT scraped_at FROM price_history
                 WHERE product_id = %s AND scraped_at >= cs.latest_date - INTERVAL '30 days'
                 ORDER BY price ASC, scraped_at ASC LIMIT 1) AS low_30d_date,
                (SELECT price FROM price_history
                 WHERE product_id = %s AND scraped_at >= cs.latest_date - INTERVAL '30 days'
                 ORDER BY price DESC, scraped_at ASC LIMIT 1) AS high_30d,
                (SELECT scraped_at FROM price_history
                 WHERE product_id = %s AND scraped_at >= cs.latest_date - INTERVAL '30 days'
                 ORDER BY price DESC, scraped_at ASC LIMIT 1) AS high_30d_date
            FROM current_streak cs
            """,
            (product_id,) * 8,
        )
        row = cur.fetchone()

    if row is None or row[2] is None:
        return None

    (current_price, current_price_since, previous_price, low_90d,
     low_90d_date, low_30d, low_30d_date, high_30d, high_30d_date) = row

    current_price = float(current_price)
    previous_price = float(previous_price)
    price_diff = previous_price - current_price  # positive = price dropped
    drop_pct = round((previous_price - current_price) / previous_price * 100, 2) if previous_price else 0.0  # positive = price dropped

    return {
        "current_price": current_price,
        "current_price_since": current_price_since,
        "previous_price": previous_price,
        "price_diff": price_diff,
        "drop_pct": drop_pct,
        "low_90d": float(low_90d),
        "low_90d_date": low_90d_date,
        "low_30d": float(low_30d),
        "low_30d_date": low_30d_date,
        "high_30d": float(high_30d),
        "high_30d_date": high_30d_date,
    }


def update_ai_description(conn, product_id: int, text: str) -> None:
    """Set the static product description generated by generate_product_description."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE products SET ai_description = %s WHERE id = %s",
            (text, product_id),
        )


def update_ai_deal_description(conn, product_id: int, text: str) -> None:
    """Set the dynamic deal description generated by generate_ai_deal_description."""
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE products
            SET ai_deal_description = %s,
                ai_deal_description_updated_at = NOW()
            WHERE id = %s
            """,
            (text, product_id),
        )


def format_embedding_for_pg(embedding: list[float]) -> str:
    """Format an embedding as the `[n1,n2,...]` string literal pgvector expects."""
    return "[" + ",".join(str(x) for x in embedding) + "]"


def store_embedding(conn, product_id: int, embedding: list[float]) -> None:
    """Set products.embedding. Does not commit — caller is responsible."""
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE products SET embedding = %s WHERE id = %s",
            (format_embedding_for_pg(embedding), product_id),
        )


