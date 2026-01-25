"""
Test script: discover + enrich 5 known Coolblue products
"""

import sys
from pathlib import Path
import time

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection
from src.coolblue_product_scraping import scrape_product_details


COOLBLUE_RETAILER_ID = 1

TEST_PRODUCTS = [
    {
        "sku": "936045",
        "product_url": "https://www.coolblue.nl/product/936045/bose-quietcomfort-ultra-headphones-zwart.html",
    },
    {
        "sku": "962722",
        "product_url": "https://www.coolblue.nl/product/962722/sony-wh-1000xm6-zwart.html",
    },
    {
        "sku": "934400",
        "product_url": "https://www.coolblue.nl/product/934400/jbl-live-770nc-zwart.html",
    },
    {
        "sku": "936048",
        "product_url": "https://www.coolblue.nl/product/936048/bose-quietcomfort-headphones-zwart.html",
    },
    {
        "sku": "962724",
        "product_url": "https://www.coolblue.nl/product/962724/sony-wh-1000xm6-blauw.html",
    },
    {
        "sku": "123456",
        "product_url": "https://www.coolblue.nl/product/123456/THIS-DOES-NOT-EXIST.html",
    }
]


def upsert_product(conn, sku, product_url, details):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO products (
                retailer_id,
                sku,
                name,
                brand,
                product_url,
                active
            )
            VALUES (%s, %s, %s, %s, %s, true)
            ON CONFLICT (retailer_id, sku)
            DO UPDATE SET
                name = EXCLUDED.name,
                product_url = EXCLUDED.product_url,
                active = true,
                brand = COALESCE(products.brand, EXCLUDED.brand);
            """,
            (
                COOLBLUE_RETAILER_ID,
                sku,
                details["name"],
                details.get("brand"),
                product_url,
            ),
        )

def print_progress(current, total, sku=None, elapsed=None, avg_time=None, est_time_left=None):
    percent = 100 * ((current + 1) / total)
    msg = f"[{current+1}/{total}] ({percent:.1f}%)"
    if sku is not None:
        msg += f" SKU: {sku}"
    if elapsed is not None:
        msg += f" | Elapsed: {elapsed:.1f}s"
    if avg_time is not None and est_time_left is not None:
        eta_minutes = est_time_left / 60
        msg += f" | Avg: {avg_time:.2f}s/item, ETA: {est_time_left:.1f}s ({eta_minutes:.1f} min)"
    print(msg, flush=True)

def main():
    conn = get_connection()

    try:
        for p in TEST_PRODUCTS:
            print(f"Scraping {p['sku']}")

            details = scrape_product_details(p["product_url"])
            print(" →", details)

            upsert_product(
                conn,
                sku=p["sku"],
                product_url=p["product_url"],
                details=details,
            )

        conn.commit()
        print("\n✅ Test run completed successfully")

    except Exception as e:
        conn.rollback()
        print("❌ ERROR during test run:", e)
        raise

    finally:
        conn.close()



def main():
    overall_start_time = time.time()

    conn = get_connection()
    success = 0
    failed = 0

    try:
        for product in TEST_PRODUCTS:
            sku = product["sku"]
            product_url = product["product_url"]

            try:
                details = scrape_product_details(product_url)

                upsert_product(
                    conn,
                    sku=sku,
                    product_url=product_url,
                    details=details,
                )

                success +=1

            except Exception as e:
                failed +=1
                print(f"⚠️  Failed to process {sku}: {e}")
                continue

        conn.commit()
        total_elapsed = time.time() - overall_start_time
        print(f"Product discovery + enrichment completed successfully in {total_elapsed:.1f} seconds")

    except Exception as e:
        conn.rollback()
        print("ERROR during product discovery:", e)
        raise

    finally:
        conn.close()

    print(f"Discovery finished: {success} succeeded, {failed} failed")


if __name__ == "__main__":
    main()
