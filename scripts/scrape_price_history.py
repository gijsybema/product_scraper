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
import random
import traceback
from typing import Optional, Tuple

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection, upsert_price_history, get_products_to_scrape
from src.coolblue_product_scraping import scrape_product_facts
from src.utils import print_progress

def process_single_product(conn, product_id: int, product_url: str, scraped_at) -> Tuple[bool, Optional[Exception]]:
    """
    Scrape + upsert for a single product.
    Retries transient failures and returns (success, error).
    """
    max_attempts = 2
    last_err: Optional[Exception] = None

    for attempt in range(1, max_attempts + 1):
        try:
            facts = scrape_product_facts(product_url)
            # Defensive: Ensure fields exist, fallback to None if missing
            price = facts.get("price")
            in_stock = facts.get("in_stock")
            rating = facts.get("rating")
            review_count = facts.get("review_count")

            upsert_price_history(
                conn,
                product_id=product_id,
                scraped_at=scraped_at,
                price=price,
                availability=in_stock,
                rating=rating,
                review_count=review_count,
            )

            return True, None  # ✅ success

        except Exception as e:
            last_err = e

            if attempt < max_attempts:
                sleep_s = (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                print(
                    f"🔁 Retry {attempt}/{max_attempts-1} "
                    f"product_id={product_id} url={product_url} "
                    f"err={type(e).__name__}: {e} sleeping {sleep_s:.1f}s"
                )
                time.sleep(sleep_s)

    # ❌ failed after retries
    return False, last_err      

def process_products(conn, products):
    total = len(products)
    success = 0
    failed = 0

    total_iter_time = 0.0
    scraped_at = datetime.now().date()

    for idx, product in enumerate(products):
        iter_start = time.time()
        # Defensive: Use .get for dict, fallback to None if missing (less prone to KeyError)
        product_id = product.get("product_id")
        product_url = product.get("product_url")

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

            ok, err = process_single_product(
                conn,
                product_id=product_id,
                product_url=product_url,
                scraped_at=scraped_at,
            )

            if ok:
                conn.commit()
                total_iter_time += time.time() - iter_start
                success += 1
            else:
                conn.rollback()
                failed += 1
                print("--------------------------------------------------")
                print("❌ SCRAPE FAILED (after retries)")
                print(f"product_id={product_id}")
                print(f"url={product_url}")
                if err:
                    print(f"error_type={type(err).__name__}")
                    print(f"error_message={err}")
                print("--------------------------------------------------")

        except Exception as e:
            # Safety net for unexpected failures (db cursor issues, bugs, etc.)
            conn.rollback()
            failed += 1
            print("--------------------------------------------------")
            print("❌ UNEXPECTED ERROR (process_products)")
            print(f"product_id={product_id}")
            print(f"url={product_url}")
            print(f"error_type={type(e).__name__}")
            print(f"error_message={e}")
            print(traceback.format_exc())
            print("--------------------------------------------------")

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

    except Exception as e:
        try:
            conn.rollback()
        except Exception as ex:
            print("ERROR rolling back connection:", ex)
        print("ERROR during price history scraping:", e)
        print(traceback.format_exc())
        raise

    finally:
        conn.close()

    total_elapsed = time.time() - overall_start
    print(f"Price history scraping completed in {total_elapsed:.1f} seconds")
    print(f"Finished: {success} succeeded, {failed} failed")

if __name__ == "__main__":
    main()