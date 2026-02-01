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
from src.db import get_connection, upsert_product
from src.utils import print_progress


def discover_products(category_url=None):
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
                identifier=sku,
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
