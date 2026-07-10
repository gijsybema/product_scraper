"""
Daily script to store the prices and availability of all Coolblue products
from the product detail page in the price_history table in PostgreSQL.
Regenerates ai_deal_description when a product's price changes.

Usage:
    python scripts/scrape_price_history.py [--limit N]
    python scripts/scrape_price_history.py --missed-only [--limit N]

    --missed-only: recovery run — only scrapes products with no price_history
                   row for today (job_name: price_history_recovery)
    --limit N:     process only the first N products (dev/testing only)
"""

import sys
import argparse
import time
from pathlib import Path
from datetime import datetime
import random
import traceback
from typing import Optional, Tuple
import requests

FAIL_RATIO_THRESHOLD = 0.20

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import truststore
    truststore.inject_into_ssl()  # local Windows dev only; not installed/needed on Railway
except ImportError:
    pass

from src.db import get_connection, upsert_price_history, get_products_to_scrape, get_price_context, update_ai_deal_description
from src.db import create_scrape_run, finish_scrape_run, handle_product_404, reset_404_count, deactivate_if_long_term_oos, OOS_DEACTIVATION_THRESHOLD
from src.coolblue_product_scraping import scrape_product_facts
from src.ai_descriptions import generate_ai_deal_description
from src.utils import print_progress, validate_price_facts
from scripts.detect_drops import run_detect_drops

def process_single_product(conn, product_id: int, product_url: str, scraped_at, product: dict) -> Tuple[bool, bool, Optional[bool], Optional[Exception]]:
    """
    Scrape + upsert for a single product.
    Returns (success, is_404, in_stock, error).
    - success=True: price history written; in_stock holds the scraped availability
    - is_404=True: product returned 404, should be deactivated (no retry); in_stock=None
    - otherwise: transient failure, retried up to max_attempts; in_stock=None

    On success, if today's price differs from the previous price on record,
    regenerates ai_deal_description via get_price_context + generate_ai_deal_description.
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

            valid, reasons = validate_price_facts({"price": price, "in_stock": in_stock})
            if not valid:
                return False, False, None, ValueError(f"[VALIDATION] product_id={product_id} reasons={reasons}")

            previous_price = upsert_price_history(
                conn,
                product_id=product_id,
                scraped_at=scraped_at,
                price=price,
                availability=in_stock,
                rating=rating,
                review_count=review_count,
            )

            if previous_price is not None and float(price) != previous_price:
                try:
                    ctx = get_price_context(conn, product_id)
                    if ctx:
                        text = generate_ai_deal_description(product, ctx)
                        if text:
                            update_ai_deal_description(conn, product_id, text)
                            print(f"[AI DEAL DESCRIPTION] product_id={product_id} generated and stored")
                        else:
                            print(f"[AI DEAL DESCRIPTION SKIP] product_id={product_id} generation failed, left stale")
                    else:
                        print(f"[AI DEAL DESCRIPTION SKIP] product_id={product_id} price changed but no price context available")
                except Exception as ai_err:
                    print(f"WARNING: could not generate/write ai_deal_description for product_id={product_id}: {ai_err}")

            return True, False, in_stock, None  # ✅ success

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return False, True, None, e  # product gone — deactivate, don't retry
            last_err = e
            if attempt < max_attempts:
                sleep_s = (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                print(
                    f"🔁 Retry {attempt}/{max_attempts-1} "
                    f"product_id={product_id} url={product_url} "
                    f"err={type(e).__name__}: {e} sleeping {sleep_s:.1f}s"
                )
                time.sleep(sleep_s)

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
    return False, False, None, last_err

def process_products(conn, products):
    total = len(products)
    success = 0
    failed = 0
    deactivated = 0

    total_iter_time = 0.0
    scraped_at = datetime.now().date()

    # pacing knobs (tune later)
    PER_PRODUCT_SLEEP_RANGE = (2.0, 4.0)   # seconds
    BATCH_EVERY = 25
    BATCH_SLEEP_RANGE = (5.0, 15.0)       # seconds

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

            ok, is_404, in_stock, err = process_single_product(
                conn,
                product_id=product_id,
                product_url=product_url,
                scraped_at=scraped_at,
                product=product,
            )

            if ok:
                try:
                    reset_404_count(conn, product_id)
                except Exception as reset_err:
                    print(f"[WARN] Failed to reset 404 count for product_id={product_id}: {reset_err}")
                if in_stock is False:
                    try:
                        newly_deactivated = deactivate_if_long_term_oos(conn, product_id)
                        if newly_deactivated:
                            deactivated += 1
                            print(f"🚫 OOS deactivated product_id={product_id} (>{OOS_DEACTIVATION_THRESHOLD} consecutive days out of stock)")
                    except Exception as oos_err:
                        print(f"[WARN] Failed OOS deactivation check for product_id={product_id}: {oos_err}")
                conn.commit()
                total_iter_time += time.time() - iter_start
                success += 1
            elif is_404:
                conn.rollback()
                print("--------------------------------------------------")
                print(f"🚫 PRODUCT NOT FOUND (404) product_id={product_id} url={product_url}")
                try:
                    newly_deactivated = handle_product_404(conn, product_id)
                    conn.commit()
                    if newly_deactivated:
                        deactivated += 1
                        print(f"   → deactivated after reaching threshold")
                    else:
                        failed += 1
                        print(f"   → 404 count incremented, not yet at threshold")
                except Exception as deact_err:
                    failed += 1
                    print(f"[WARN] Failed to update 404 count for product_id={product_id}: {deact_err}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                print("--------------------------------------------------")
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

        # Add sleep (runs after every product, success or fail)
        sleep_s = random.uniform(*PER_PRODUCT_SLEEP_RANGE)
        print(f"[PACE] Sleeping {sleep_s:.2f}s")
        time.sleep(sleep_s)

        # Longer pause every N products
        if (idx + 1) % BATCH_EVERY == 0:
            batch_sleep_s = random.uniform(*BATCH_SLEEP_RANGE)
            print(f"[PACE] Batch pause after {idx+1} products: sleeping {batch_sleep_s:.2f}s")
            time.sleep(batch_sleep_s)

    return success, failed, deactivated

# ----------------------------
# main
# ----------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--missed-only", action="store_true", dest="missed_only",
                        help="Only scrape products with no price_history row for today (recovery run)")
    args = parser.parse_args()

    if args.limit is None:
        # Add jitter to avoid the 09:00 / 12:00 spike
        jitter_seconds = random.uniform(0, 10 * 60)  # 0-10 minutes
        print(f"[RUN] Start jitter sleeping {jitter_seconds:.0f}s")
        time.sleep(jitter_seconds)

    overall_start = time.time()
    job_name = "price_history_recovery" if args.missed_only else "price_history_daily"

    start = time.time()
    products = get_products_to_scrape(missed_only=args.missed_only)
    print(f"Found {len(products)} products to scrape")

    if args.limit is not None:
        print(f"[DEV] --limit {args.limit}: capping at {min(args.limit, len(products))} products")
        products = products[: args.limit]
    print(f"Product lookup took {time.time() - start:.1f} seconds")

    conn = get_connection()
    run_id = None
    run_id = create_scrape_run(
        conn,
        job_name=job_name,
        total_products=len(products),
        retry_attempt=0,
    )
    print(f"[RUN] run_id={run_id}")

    success = 0
    failed = 0
    deactivated = 0
    status = "success"
    last_error = None

    try:
        success, failed, deactivated = process_products(conn, products)

        total_elapsed = time.time() - overall_start
        print(f"Price history scraping completed in {total_elapsed:.1f} seconds")
        print(f"Finished: {success} succeeded, {failed} failed, {deactivated} deactivated")

        total = success + failed + deactivated
        fail_ratio = (failed / (success + failed)) if (success + failed) > 0 else 0.0

        if failed > 0:
            if total > 0 and fail_ratio > FAIL_RATIO_THRESHOLD:
                print("⚠️  High failure ratio — possible temporary block")
                status = "failed"
            else:
                status = "partial"

        print(f"[RUN] success={success} failed={failed} deactivated={deactivated} fail_ratio={fail_ratio:.1%} status={status}")

        # Run drop detection if fail ratio is below threshold
        if total > 0 and fail_ratio <= FAIL_RATIO_THRESHOLD:
            print(f"[DROPS] Running detect_drops (fail_ratio={fail_ratio:.1%})")
            try:
                inserted = run_detect_drops(conn)
                print(f"[DROPS] inserted {inserted} rows into price_drops")
            except Exception as e:
                print("[DROPS] ERROR:", e)
                print(traceback.format_exc())
        else:
            print(f"[DROPS] Skip detect_drops (fail_ratio={fail_ratio:.1%} > {FAIL_RATIO_THRESHOLD:.0%})")

    except Exception as e:
        # If the whole run crashes, mark as failed
        try:
            conn.rollback()
        except Exception:
            pass
        last_error = f"{type(e).__name__}: {e}"
        print("ERROR during price history scraping:", last_error)
        print(traceback.format_exc())

        status = "failed"

    finally:
        try:
            finish_scrape_run(
                conn,
                run_id=run_id,
                status=status,
                success_count=success,
                failed_count=failed,
                blocked_count=deactivated,
                last_error=last_error,
            )
        except Exception as e:
            print("ERROR finishing scrape run:", e)
            print(traceback.format_exc())

        duration = time.time() - overall_start
        print("=== RUN SUMMARY ===")
        print(f"job         : {job_name}")
        print(f"run_id      : {run_id}")
        print(f"status      : {status}")
        print(f"total       : {success + failed + deactivated}")
        print(f"success     : {success}")
        print(f"failed      : {failed}")
        print(f"deactivated : {deactivated}")
        print(f"duration    : {duration:.1f}s")
        print("===================")

        if not args.missed_only:
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM products p
                        WHERE p.active = true
                          AND NOT EXISTS (
                              SELECT 1 FROM price_history ph
                              WHERE ph.product_id = p.id
                                AND ph.scraped_at = CURRENT_DATE
                          )
                        """
                    )
                    missed = cur.fetchone()[0]
                if missed > 0:
                    print(f"[RECOVERY] {missed} products have no price_history row today — recovery run will pick these up")
                else:
                    print("[RECOVERY] All products scraped — no recovery run needed")
            except Exception as e:
                print(f"[RECOVERY] Could not count missed products: {e}")

        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()