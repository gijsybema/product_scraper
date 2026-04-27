"""
Diagnostic script: check category mapping coverage across all products in the DB.

For each product URL, fetches the page, extracts all raw breadcrumb item names,
and runs normalize_category() against each. Reports which raw strings are not
mapped to a valid category so gaps in _CATEGORY_MAP can be identified.

Usage:
    python scripts/check_category_coverage.py           # all products
    python scripts/check_category_coverage.py --limit 20  # sample first N
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import time
import random
import argparse
import json
import os
from pathlib import Path
from collections import defaultdict
from contextlib import redirect_stdout

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection
from src.coolblue_product_scraping import fetch_response_with_retry, ensure_html
from src.utils import normalize_category

from bs4 import BeautifulSoup


def extract_raw_breadcrumb_names(html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue
        if data.get("@type") != "BreadcrumbList":
            continue
        return [item.get("name") for item in data.get("itemListElement", []) if item.get("name")]
    return []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Check only first N products")
    args = parser.parse_args()

    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id, product_url FROM products WHERE active = true ORDER BY id")
            rows = cur.fetchall()
    finally:
        conn.close()

    if args.limit:
        rows = rows[:args.limit]

    total = len(rows)
    print(f"Checking {total} products...\n")

    mapped = 0
    unmapped_products = []
    unmapped_string_counts = defaultdict(int)
    mapped_string_counts = defaultdict(int)

    for i, (product_id, url) in enumerate(rows, 1):
        print(f"[{i}/{total}] {url}", flush=True)
        try:
            resp = fetch_response_with_retry(url, warmup=(i == 1))
            html = ensure_html(resp, url)
        except Exception as e:
            print(f"  ERROR fetching: {e}")
            continue

        raw_names = extract_raw_breadcrumb_names(html)
        resolved = None
        resolved_name = None

        with open(os.devnull, "w") as devnull, redirect_stdout(devnull):
            for name in raw_names:
                category = normalize_category(name)
                if category is not None:
                    resolved = category
                    resolved_name = name
                    break

        if resolved:
            mapped += 1
            mapped_string_counts[resolved_name] += 1
        else:
            unmapped_products.append((product_id, url, raw_names))
            for name in raw_names:
                unmapped_string_counts[name] += 1

        time.sleep(random.uniform(0.5, 1.0))

    print("\n" + "=" * 60)
    print(f"RESULTS: {total} products checked")
    print(f"  Mapped:   {mapped}")
    print(f"  Unmapped: {total - mapped}")
    print()

    if mapped_string_counts:
        print("Recognised breadcrumb strings (mapped to a valid category):")
        for name, count in sorted(mapped_string_counts.items(), key=lambda x: -x[1]):
            category = normalize_category(name)
            print(f"  {count:>4}x  {repr(name):<40} -> {category}")
        print()

    if unmapped_string_counts:
        # Filter out known structural non-categories to highlight true gaps
        known_skip = {"home", "coolblue"}
        gaps = {
            k: v for k, v in unmapped_string_counts.items()
            if k.lower() not in known_skip
        }
        if gaps:
            print("Distinct unrecognised breadcrumb strings (excluding 'Home'/'Coolblue'):")
            for name, count in sorted(gaps.items(), key=lambda x: -x[1]):
                print(f"  {count:>4}x  {repr(name)}")
        else:
            print("No unexpected unrecognised strings found.")
    else:
        print("All products resolved to a valid category.")


if __name__ == "__main__":
    main()
