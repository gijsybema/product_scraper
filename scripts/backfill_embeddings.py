"""
One-off script to backfill embeddings for existing products where
products.embedding is still NULL. Uses build_embedding_text/generate_embedding
(src/embeddings.py) and store_embedding (src/db.py).

Usage:
    python scripts/backfill_embeddings.py [--limit N] [--dry-run]

    --limit N:   process only the first N NULL rows (dev/testing only)
    --dry-run:   print the embedding text for each product without calling
                 the OpenAI API or writing to the DB
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

try:
    # default Windows console encoding (cp1252) can't print accented characters
    # (e.g. product names/specs) or emoji reliably
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except AttributeError:
    pass

from dotenv import load_dotenv
load_dotenv(".env.local")  # needed here because DATABASE_URL is often set manually
                            # (bypassing src.config's own load_dotenv) for prod runs

from src.db import get_connection, store_embedding, create_scrape_run, finish_scrape_run
from src.embeddings import build_embedding_text, generate_embedding, get_total_cost


def get_products_missing_embedding(conn, limit=None):
    query = """
        SELECT id, name, brand, category, specs, ai_description
        FROM products
        WHERE embedding IS NULL AND active = true
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
            "specs": row[4],
            "ai_description": row[5],
        }
        for row in rows
    ]


def process_products(conn, products, dry_run=False):
    success = 0
    skipped = 0

    for idx, product in enumerate(products):
        product_id = product["id"]
        print(f"[{idx + 1}/{len(products)}] product_id={product_id}")

        text = build_embedding_text(product)

        if dry_run:
            print(text)
            print("[DRY RUN] no API call, no DB write")
            continue

        try:
            embedding = generate_embedding(text)
            if embedding:
                store_embedding(conn, product_id, embedding)
                conn.commit()  # per-row commit: store_embedding itself does not commit (see spec R-8)
                success += 1
                print(f"[OK] product_id={product_id} embedding stored ({len(embedding)} dims)")
            else:
                skipped += 1
                print(f"[SKIP] product_id={product_id} generation failed, left NULL")
        except Exception as e:
            conn.rollback()
            skipped += 1
            print(f"WARNING: could not generate/store embedding for product_id={product_id}: {e}")

        time.sleep(0.1)  # rate limit

    return success, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true",
                         help="print embedding text only; no API call, no DB write")
    args = parser.parse_args()

    conn = get_connection()
    run_id = None
    success, skipped = 0, 0
    status = "failed"
    products = []

    try:
        products = get_products_missing_embedding(conn, limit=args.limit)
        print(f"Found {len(products)} products with embedding IS NULL")

        if not args.dry_run:
            run_id = create_scrape_run(conn, job_name="backfill_embeddings", total_products=len(products))

        success, skipped = process_products(conn, products, dry_run=args.dry_run)

        if not args.dry_run:
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
        if not args.dry_run:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM products WHERE embedding IS NULL AND active = true")
                remaining_null = cur.fetchone()[0]
        else:
            remaining_null = "n/a (dry run)"

        print("=== RUN SUMMARY ===")
        print(f"run_id         : {run_id}")
        print(f"status         : {'dry-run' if args.dry_run else status}")
        print(f"total          : {len(products)}")
        print(f"success        : {success}")
        print(f"skipped        : {skipped}")
        print(f"remaining NULL : {remaining_null}")
        print("===================")
        if not args.dry_run:
            print(f"[EMBEDDING COST TOTAL] this run: ${get_total_cost():.5f}")

        conn.close()


if __name__ == "__main__":
    main()
