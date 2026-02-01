"""
Daily script to store the prices and availability of all Coolblue products 
from the product detail page in the price_history table in PostgreSQL.

Usage:
    python scripts/scrape_price_history.py
"""

import sys
import time
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection, upsert_price_history, get_products_to_scrape
from src.coolblue_product_scraping import scrape_product_facts
from src.utils import print_progress


def process_single_product(conn, product_id: int, product_url: str, scraped_at: datetime):
    """Scrape and store price history for a single product."""
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
                identifier=product_id,
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