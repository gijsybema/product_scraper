"""
Weekly script to discover all unique Coolblue products, enrich them with product
metadata from the product detail page and store them directly in PostgreSQL.

Usage:
    python scripts/discover_products.py [category] [--limit N]
    python scripts/discover_products.py --all [--limit N]

    category: headphones (default), earbuds, speakers, soundbars
    --all:    run discovery for all categories in sequence
    --limit N: process only the first N products per category (dev/testing only)
"""

import sys
import argparse
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.coolblue_discovery import get_all_coolblue_products
from src.coolblue_product_scraping import scrape_product_details, CoolblueBlockedError
from src.db import get_connection, upsert_product, create_scrape_run, finish_scrape_run
from src.utils import print_progress, validate_product_details, generate_slug

CATEGORY_URLS = {
    "headphones": "https://www.coolblue.nl/hoofdtelefoons/filter",
    "earbuds":    "https://www.coolblue.nl/oordopjes/filter",
    "speakers":   "https://www.coolblue.nl/draadloze-speakers/filter",
    "soundbars":  "https://www.coolblue.nl/soundbars/filter",
}


def _resolve_category_url(category: str) -> str:
    if category not in CATEGORY_URLS:
        known = ", ".join(CATEGORY_URLS)
        raise ValueError(f"Unknown category '{category}'. Known: {known}")
    return CATEGORY_URLS[category]


def discover_products(category="headphones", limit=None):
    category_url = _resolve_category_url(category)
    fallback_category = category

    print(f"Discovering products from: {category_url}")
    print("This may take a while...")

    start = time.time()
    products = get_all_coolblue_products(category_url, max_products=limit)
    elapsed = time.time() - start

    if len(products) == 0:
        print(f"WARNING: 0 products discovered from {category_url} — possible block or page structure change")

    print(f"Found {len(products)} product URLs")
    print(f"Product URL discovery took {elapsed:.1f} seconds")

    return products, fallback_category


def _load_existing_slugs(conn) -> set:
    with conn.cursor() as cur:
        cur.execute("SELECT slug FROM products WHERE slug IS NOT NULL")
        return {row[0] for row in cur.fetchall()}


MAX_CONSECUTIVE_403S = 5


def process_products(conn, products, fallback_category=None):
    total = len(products)
    success = 0
    failed = 0
    skipped = 0
    blocked = 0
    consecutive_403s = 0
    total_iter_time = 0.0
    existing_slugs = _load_existing_slugs(conn)

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
            print(f"  url : {product_url.split('coolblue.nl')[-1]}")

            details = scrape_product_details(product_url)

            if not details.get("category") and fallback_category:
                print(f"[CATEGORY FALLBACK] sku={sku} category=None from page, using fallback '{fallback_category}'")
                details["category"] = fallback_category

            valid, reasons = validate_product_details(details)
            if not valid:
                skipped += 1
                print(f"[VALIDATION SKIP] sku={sku} reasons={reasons}")
                continue

            slug = generate_slug(details["name"], existing_slugs)
            existing_slugs.add(slug)
            details["slug"] = slug

            upsert_product(
                conn,
                sku=sku,
                product_url=product_url,
                details=details,
            )

            total_iter_time += time.time() - iter_start
            success += 1
            consecutive_403s = 0

        except CoolblueBlockedError as e:
            blocked += 1
            consecutive_403s += 1
            print(f"⚠️  Blocked processing {sku}: {e}")
            if consecutive_403s >= MAX_CONSECUTIVE_403S:
                print(f"[BLOCKED] {consecutive_403s} consecutive 403s — aborting run early")
                raise CoolblueBlockedError(f"Aborted after {consecutive_403s} consecutive blocked products")

        except Exception as e:
            failed += 1
            consecutive_403s = 0
            print(f"⚠️  Failed to process {sku}: {e}")

    return success, failed, skipped, blocked


def run_category(conn, category, limit=None):
    """Run full discover + upsert flow for one category. Returns summary dict."""
    start = time.time()
    run_id = None
    success, failed, skipped, blocked = 0, 0, 0, 0
    status = "failed"
    products = []

    try:
        products, fallback_category = discover_products(category, limit=limit)

        if limit is not None:
            products = products[:limit]

        run_id = create_scrape_run(conn, job_name=f"discover_products_{category}", total_products=len(products))
        success, failed, skipped, blocked = process_products(conn, products, fallback_category)
        conn.commit()
        print("COMMITTING TRANSACTION")

        total = len(products)
        status = "success" if failed == 0 and blocked == 0 else ("partial" if success > 0 else "failed")
        finish_scrape_run(conn, run_id=run_id, status=status, success_count=success, failed_count=failed, blocked_count=blocked)

    except CoolblueBlockedError as e:
        conn.rollback()
        print(f"[BLOCKED] Discovery for '{category}' aborted: {e}")
        if run_id is not None:
            try:
                finish_scrape_run(conn, run_id=run_id, status="blocked", success_count=success, failed_count=failed, blocked_count=blocked, last_error=str(e))
            except Exception as log_err:
                print(f"WARNING: could not write blocked run log: {log_err}")
        status = "blocked"

    except Exception as e:
        conn.rollback()
        print(f"ERROR during discovery for '{category}': {e}")
        if run_id is not None:
            try:
                finish_scrape_run(conn, run_id=run_id, status="failed", success_count=success, failed_count=failed, blocked_count=blocked, last_error=str(e))
            except Exception as log_err:
                print(f"WARNING: could not write failed run log: {log_err}")

    finally:
        duration = time.time() - start
        print("=== RUN SUMMARY ===")
        print(f"job       : discover_products_{category}")
        print(f"run_id    : {run_id}")
        print(f"status    : {status}")
        print(f"total     : {len(products)}")
        print(f"success   : {success}")
        print(f"failed    : {failed}")
        print(f"skipped   : {skipped}")
        print(f"blocked   : {blocked}")
        print(f"duration  : {duration:.1f}s")
        print("===================")

    return {"category": category, "total": len(products), "success": success, "failed": failed, "skipped": skipped, "blocked": blocked, "status": status}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("category", nargs="?", default="headphones")
    parser.add_argument("--all", action="store_true", dest="all_categories",
                        help="Run discovery for all categories in sequence")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    overall_start = time.time()
    categories = list(CATEGORY_URLS.keys()) if args.all_categories else [args.category]

    conn = None
    conn = get_connection()
    results = []
    try:
        for category in categories:
            result = run_category(conn, category, limit=args.limit)
            results.append(result)
    finally:
        if conn:
            conn.close()

    if args.all_categories:
        total_duration = time.time() - overall_start
        print("=== ALL CATEGORIES SUMMARY ===")
        for r in results:
            print(f"  {r['category']:<12} status={r['status']} total={r['total']} success={r['success']} failed={r['failed']} skipped={r['skipped']} blocked={r['blocked']}")
        print(f"  total duration : {total_duration:.1f}s")
        print("==============================")


if __name__ == "__main__":
    main()
