"""
One-off script to backfill ai_description for existing products where it is
still NULL. Uses data already stored on the products row (name, brand,
category, description, specs) — no live scraping.

Usage:
    python scripts/backfill_ai_descriptions.py [--limit N]

    --limit N: process only the first N NULL rows (dev/testing only)
"""

import sys
import argparse
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import truststore
    truststore.inject_into_ssl()  # local Windows dev only; not installed/needed on Railway
except ImportError:
    pass

from dotenv import load_dotenv
load_dotenv(".env.local")  # needed here because DATABASE_URL is often set manually
                            # (bypassing src.config's own load_dotenv) for prod runs

from src.db import get_connection, update_ai_description, create_scrape_run, finish_scrape_run
from src.ai_descriptions import generate_product_description, get_total_cost


def get_products_missing_description(conn, limit=None):
    query = """
        SELECT id, name, brand, category, description, specs
        FROM products
        WHERE ai_description IS NULL
        ORDER BY id
    """
    if limit is not None:
        query += " LIMIT %s"
        params = (limit,)
    else:
        params = ()

    with conn.cursor() as cur:
        cur.execute(query, params)
        rows = cur.fetchall()

    return [
        {
            "id": row[0],
            "name": row[1],
            "brand": row[2],
            "category": row[3],
            "description": row[4],
            "specs": row[5],
        }
        for row in rows
    ]


def process_products(conn, products):
    success = 0
    skipped = 0

    for idx, product in enumerate(products):
        product_id = product["id"]
        print(f"[{idx + 1}/{len(products)}] product_id={product_id}")

        try:
            text = generate_product_description(product)
            if text:
                update_ai_description(conn, product_id, text)
                conn.commit()
                success += 1
                print(f"[AI DESCRIPTION] product_id={product_id} generated and stored")
            else:
                skipped += 1
                print(f"[AI DESCRIPTION SKIP] product_id={product_id} generation failed, left NULL")
        except Exception as e:
            conn.rollback()
            skipped += 1
            print(f"WARNING: could not generate/write ai_description for product_id={product_id}: {e}")

        time.sleep(0.5)  # rate limit

    return success, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    conn = get_connection()
    run_id = None
    success, skipped = 0, 0
    status = "failed"
    products = []

    try:
        products = get_products_missing_description(conn, limit=args.limit)
        print(f"Found {len(products)} products with ai_description IS NULL")

        run_id = create_scrape_run(conn, job_name="backfill_ai_descriptions", total_products=len(products))
        success, skipped = process_products(conn, products)

        status = "success" if skipped == 0 else ("partial" if success > 0 else "failed")
        finish_scrape_run(conn, run_id=run_id, status=status, success_count=success, failed_count=skipped)

    except Exception as e:
        conn.rollback()
        print(f"ERROR during backfill: {e}")
        if run_id is not None:
            try:
                finish_scrape_run(conn, run_id=run_id, status="failed", success_count=success, failed_count=skipped, last_error=str(e))
            except Exception as log_err:
                print(f"WARNING: could not write failed run log: {log_err}")

    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM products WHERE ai_description IS NULL")
            remaining_null = cur.fetchone()[0]

        print("=== RUN SUMMARY ===")
        print(f"run_id         : {run_id}")
        print(f"status         : {status}")
        print(f"total          : {len(products)}")
        print(f"success        : {success}")
        print(f"skipped        : {skipped}")
        print(f"remaining NULL : {remaining_null}")
        print("===================")
        print(f"[AI COST TOTAL] this run: ${get_total_cost():.5f}")

        conn.close()


if __name__ == "__main__":
    main()
