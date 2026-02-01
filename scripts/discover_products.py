"""
Weekly script to discover all unique Coolblue products, enrich them with product
metadata from the product detail page and store them directly in PostgreSQL.

Usage:
    python scripts/discover_products.py [category_url]
"""

import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.coolblue_discovery import get_all_coolblue_products
from src.coolblue_product_scraping import scrape_product_details
from src.db import get_connection

COOLBLUE_RETAILER_ID = 1  # adjust if needed

def discover_products(category_url = None):
    if category_url is None:
        category_url = "https://www.coolblue.nl/hoofdtelefoons/filter"

    print(f"Discovering products from: {category_url}")
    print("This may take a while...")

    start = time.time()
    products = get_all_coolblue_products(category_url)
    elapsed = time.time() - start

    print(f"Found {len(products)} product URLs")
    print(f"Product URL discovery took {elapsed:.1f} seconds")

    return products


def print_progress(current, total, sku=None, elapsed=None, avg_time=None, est_time_left=None):
    percent = 100 * ((current + 1) / total)
    msg = f"[{current+1}/{total}] ({percent:.1f}%)"
    if sku is not None:
        msg += f" SKU: {sku}"
    if elapsed is not None:
        msg += f" | Elapsed: {elapsed:.1f}s"
    if avg_time is not None and est_time_left is not None:
        eta_minutes = est_time_left / 60
        msg += f" | Avg: {avg_time:.2f}s/item, ETA: {est_time_left:.1f}s ({eta_minutes:.1f} min)"
    print(msg, flush=True)


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

def process_products(conn, products):
    total = len(products)
    success = 0
    failed = 0
    total_iter_time = 0.0

    for idx, product in enumerate(products):
        iter_start = time.time()
        sku = product["sku"]
        product_url = product["product_url"]

        try:
            elapsed = total_iter_time
            avg_time = elapsed / idx if idx > 0 else None
            est_time_left = (total - (idx + 1)) * avg_time if avg_time else None

            print_progress(
                idx,
                total,
                sku=sku,
                elapsed=elapsed,
                avg_time=avg_time,
                est_time_left=est_time_left,
            )

            details = scrape_product_details(product_url)

            upsert_product(
                conn,
                sku=sku,
                product_url=product_url,
                details=details,
            )

            total_iter_time += time.time() - iter_start
            success += 1

        except Exception as e:
            failed += 1
            print(f"⚠️  Failed to process {sku}: {e}")

    return success, failed


def main():
    overall_start = time.time()
    products = discover_products()

    conn = get_connection()
    try:
        success, failed = process_products(conn, products)
        conn.commit()
        print("COMMITTING TRANSACTION")

    except Exception as e:
        conn.rollback()
        print("ERROR during product discovery:", e)
        raise

    finally:
        conn.close()

    total_elapsed = time.time() - overall_start
    print(f"Product discovery + enrichment completed in {total_elapsed:.1f} seconds")
    print(f"Discovery finished: {success} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
