"""
Daily script to store the prices and availability of all Coolblue products 
from the product detail page in the price_history table in PostgreSQL.

Usage:
    python scripts/scrape_price_history_sql.py
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection
from src.coolblue_product_scraping import scrape_product_facts

def get_products_to_scrape():
    """
    Get all products to scrape from the products table.
    """
    conn = get_connection()
    with conn.cursor() as cur:
        cur.execute("SELECT id, product_url FROM products WHERE active = true")
        products = cur.fetchall()
    conn.close()
    return [{"product_id": product[0], "product_url": product[1]} for product in products]

def upsert_price_history(conn, product_id: int, scraped_at:datetime, price: float, availability: bool, rating: float, review_count: int):
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

def process_single_product(conn, product_id: int, product_url: str, scraped_at):
    facts = scrape_product_facts(product_url)

    upsert_price_history(
        conn,
        product_id=product_id,
        scraped_at=scraped_at,
        price=facts["price"],
        availability=facts["in_stock"],
        rating=facts["rating"],
        review_count=facts["review_count"],
    )

def print_progress(current, total, product_id=None, elapsed=None, avg_time=None, est_time_left=None):
    percent = 100 * ((current + 1) / total)
    msg = f"[{current+1}/{total}] ({percent:.1f}%)"
    if product_id is not None:
        msg += f" Product ID: {product_id}"
    if elapsed is not None:
        msg += f" | Elapsed: {elapsed:.1f}s"
    if avg_time is not None and est_time_left is not None:
        eta_minutes = est_time_left / 60
        msg += f" | Avg: {avg_time:.2f}s/item, ETA: {est_time_left:.1f}s ({eta_minutes:.1f} min)"
    print(msg, flush=True)

def process_products(conn, products):
    total = len(products)
    success = 0
    failed = 0

    total_iter_time = 0.0
    scraped_at = datetime.now().date()

    for idx, product in enumerate(products):
        iter_start = time.time()
        product_id = product["product_id"]
        product_url = product["product_url"]

        try:
            elapsed = total_iter_time
            avg_time = elapsed / idx if idx > 0 else None
            est_time_left = (total - (idx + 1)) * avg_time if avg_time else None

            print_progress(
                idx,
                total,
                product_id=product_id,
                elapsed=elapsed,
                avg_time=avg_time,
                est_time_left=est_time_left,
            )

            process_single_product(
                conn,
                product_id=product_id,
                product_url=product_url,
                scraped_at=scraped_at,
            )

            total_iter_time += time.time() - iter_start
            success += 1

        except Exception as e:
            failed += 1
            print(f"⚠️  Failed to process {product_id}: {e}")

    return success, failed


def main():
    overall_start = time.time()

    start = time.time()
    products = get_products_to_scrape()
    print(f"Found {len(products)} products to scrape")
    print(f"Product lookup took {time.time() - start:.1f} seconds")

    conn = get_connection()
    try:
        success, failed = process_products(conn, products)
        conn.commit()
        print("COMMITTING TRANSACTION")

    except Exception as e:
        conn.rollback()
        print("ERROR during price history scraping:", e)
        raise

    finally:
        conn.close()

    total_elapsed = time.time() - overall_start
    print(f"Price history scraping completed in {total_elapsed:.1f} seconds")
    print(f"Finished: {success} succeeded, {failed} failed")

if __name__ == "__main__":
    main()