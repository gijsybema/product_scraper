"""
One-off script to backfill ai_deal_description for existing products where it
is still NULL. Uses get_price_context (change-point detection over existing
price_history) to find products with a genuine price change already on
record — products with no real price change are skipped, not written.

Usage:
    python scripts/backfill_ai_deal_descriptions.py [--limit N]

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

from src.db import get_connection, get_price_context, update_ai_deal_description, create_scrape_run, finish_scrape_run
from src.ai_descriptions import generate_ai_deal_description, get_total_cost


def get_products_missing_deal_description(conn, limit=None):
    query = """
        SELECT id, name, brand
        FROM products
        WHERE ai_deal_description IS NULL
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

    return [{"id": row[0], "name": row[1], "brand": row[2]} for row in rows]


def process_products(conn, products):
    generated = 0
    skipped_no_context = 0
    skipped_generation_failed = 0

    for idx, product in enumerate(products):
        product_id = product["id"]
        print(f"[{idx + 1}/{len(products)}] product_id={product_id}")

        try:
            ctx = get_price_context(conn, product_id)
            if not ctx:
                skipped_no_context += 1
                print(f"[AI DEAL DESCRIPTION SKIP] product_id={product_id} no price context available")
                continue

            text = generate_ai_deal_description(product, ctx)
            if text:
                update_ai_deal_description(conn, product_id, text)
                conn.commit()
                generated += 1
                print(f"[AI DEAL DESCRIPTION] product_id={product_id} generated and stored")
            else:
                skipped_generation_failed += 1
                print(f"[AI DEAL DESCRIPTION SKIP] product_id={product_id} generation failed, left NULL")
        except Exception as e:
            conn.rollback()
            skipped_generation_failed += 1
            print(f"WARNING: could not generate/write ai_deal_description for product_id={product_id}: {e}")

        time.sleep(0.5)  # rate limit

    return generated, skipped_no_context, skipped_generation_failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    conn = get_connection()
    run_id = None
    generated, skipped_no_context, skipped_generation_failed = 0, 0, 0
    status = "failed"
    products = []

    try:
        products = get_products_missing_deal_description(conn, limit=args.limit)
        print(f"Found {len(products)} products with ai_deal_description IS NULL")

        run_id = create_scrape_run(conn, job_name="backfill_ai_deal_descriptions", total_products=len(products))
        generated, skipped_no_context, skipped_generation_failed = process_products(conn, products)

        failed_count = skipped_generation_failed
        status = "success" if failed_count == 0 else ("partial" if generated > 0 else "failed")
        finish_scrape_run(conn, run_id=run_id, status=status, success_count=generated, failed_count=failed_count)

    except Exception as e:
        conn.rollback()
        print(f"ERROR during backfill: {e}")
        if run_id is not None:
            try:
                finish_scrape_run(conn, run_id=run_id, status="failed", success_count=generated, failed_count=skipped_generation_failed, last_error=str(e))
            except Exception as log_err:
                print(f"WARNING: could not write failed run log: {log_err}")

    finally:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM products WHERE ai_deal_description IS NULL")
            remaining_null = cur.fetchone()[0]

        print("=== RUN SUMMARY ===")
        print(f"run_id                    : {run_id}")
        print(f"status                    : {status}")
        print(f"total                     : {len(products)}")
        print(f"generated                 : {generated}")
        print(f"skipped (no context)      : {skipped_no_context}")
        print(f"skipped (generation fail) : {skipped_generation_failed}")
        print(f"remaining NULL            : {remaining_null}")
        print("===================")
        print(f"[AI COST TOTAL] this run: ${get_total_cost():.5f}")

        conn.close()


if __name__ == "__main__":
    main()
