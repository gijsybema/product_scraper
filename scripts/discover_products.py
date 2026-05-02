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
from src.db import get_connection, upsert_product, create_scrape_run, finish_scrape_run
from src.utils import print_progress, validate_product_details


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
    skipped = 0
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

            valid, reasons = validate_product_details(details)
            if not valid:
                skipped += 1
                print(f"[VALIDATION SKIP] sku={sku} reasons={reasons}")
                continue

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

    return success, failed, skipped


def main():
    overall_start = time.time()
    products = discover_products()

    if len(products) == 0:
        print("WARNING: 0 products discovered — possible block or page structure change")

    conn = None
    conn = get_connection()
    run_id = None
    success, failed, skipped = 0, 0, 0
    status = "failed"
    try:
        run_id = create_scrape_run(conn, job_name="discover_products", total_products=len(products))
        success, failed, skipped = process_products(conn, products)
        conn.commit()
        print("COMMITTING TRANSACTION")

        total = len(products)
        status = "success" if failed == 0 else ("partial" if failed < total else "failed")
        finish_scrape_run(conn, run_id=run_id, status=status, success_count=success, failed_count=failed)

    except Exception as e:
        conn.rollback()
        print("ERROR during product discovery:", e)
        if run_id is not None:
            try:
                finish_scrape_run(conn, run_id=run_id, status="failed", success_count=success, failed_count=failed, last_error=str(e))
            except Exception as log_err:
                print(f"WARNING: could not write failed run log: {log_err}")
        raise

    finally:
        duration = time.time() - overall_start
        print("=== RUN SUMMARY ===")
        print(f"job       : discover_products")
        print(f"run_id    : {run_id}")
        print(f"status    : {status}")
        print(f"total     : {len(products)}")
        print(f"success   : {success}")
        print(f"failed    : {failed}")
        print(f"skipped   : {skipped}")
        print(f"duration  : {duration:.1f}s")
        print("===================")
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
