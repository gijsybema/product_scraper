"""
Retry runner: checks DB for due retry and runs scrape again.

Usage:
    python scripts/retry_scrape_price_history.py
"""

import sys
import time
from pathlib import Path
from datetime import datetime, timedelta
import traceback
import random

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection, get_products_to_scrape, get_due_retry_run, clear_next_retry, create_scrape_run, finish_scrape_run
from scripts.scrape_price_history import process_products  # reuse your function

RETRY_DELAYS_HOURS = [1, 2, 4, 4]  # attempt 1..4

def next_retry_time(now, next_attempt: int):
    """
    next_attempt: 1..4 -> schedule based on RETRY_DELAYS_HOURS
    returns datetime or None if no more retries
    """
    if 1 <= next_attempt <= len(RETRY_DELAYS_HOURS):
        return now + timedelta(hours=RETRY_DELAYS_HOURS[next_attempt - 1])
    return None

def main():
    conn = get_connection()
    try:
        due = get_due_retry_run(conn, job_name="price_history_daily")
        if not due:
            print("[RETRY] No retry due. Exiting.")
            return

        # prevent multiple retry workers from doing the same retry:
        # clear the next_retry_at immediately (simple lock against double run)
        clear_next_retry(conn, due["id"])
        print(f"[RETRY] Claimed retry for run_id={due['id']}")

        current_attempt = due["retry_attempt"]          # 0..4 (stored on the prior rim row)
        this_attempt = current_attempt + 1              # 1..5 (this retry run)

        # If we already did 4 retries, stop
        if this_attempt > 4:
            print(f"[RETRY] Max retries reached (current_attempt={current_attempt}). Not retrying.")
            return

        # small jitter so retries don’t stack on the quarter-hour
        jitter_seconds = random.uniform(0, 5 * 60)
        print(f"[RETRY] Jitter sleeping {jitter_seconds:.0f}s")
        time.sleep(jitter_seconds)

        products = get_products_to_scrape()
        print(f"[RETRY] Found {len(products)} products")

        retry_run_id = create_scrape_run(conn, job_name="price_history_daily", total_products=len(products), retry_attempt=this_attempt)
        print(f"[RETRY] retry_run_id={retry_run_id}")

        success, failed = process_products(conn, products)

        total = success + failed
        fail_ratio = (failed / total) if total > 0 else 1.0

        next_retry_at = None
        status = "success"
        if failed > 0:
            if fail_ratio >= 0.20:
                status = "failed"
                # backoff more on repeated failure
                next_retry_at = next_retry_time(datetime.now(), next_attempt=this_attempt + 1)
            else:
                status = "partial"

        finish_scrape_run(
            conn,
            run_id=retry_run_id,
            status=status,
            success_count=success,
            failed_count=failed,
            blocked_count=0,
            next_retry_at=next_retry_at,
            last_error=None,
        )

        if next_retry_at:
            print(f"[RETRY] Still failing, scheduled next retry at {next_retry_at}")
        else:
            print("[RETRY] Completed without scheduling another retry.")

    except Exception as e:
        try:
            conn.rollback()
        except Exception:
            pass
        print("[RETRY] ERROR:", e)
        print(traceback.format_exc())
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    main()