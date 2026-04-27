"""
One-off backfill: populate `category` and `slug` for all existing products.

Current slices implemented:
  S1 — fetch and print products where category is null/invalid or slug is null
  S2 — generate and write slugs for products with slug IS NULL
  S3 — resolve and write category for products with null/invalid category

Usage:
    python scripts/backfill_category_slug.py
"""

import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import time

from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection
from src.utils import VALID_CATEGORIES, generate_slug
from src.coolblue_product_scraping import (
    fetch_response_with_retry,
    ensure_html,
    extract_product_category,
)

# All products currently in the DB were discovered from the headphones
# category. If breadcrumb extraction fails (e.g. Sony brand-path pages),
# fall back to this value rather than leaving category null.
_BACKFILL_CATEGORY_FALLBACK = "headphones"


def fetch_existing_slugs(conn) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT slug FROM products WHERE slug IS NOT NULL")
        return {row[0] for row in cur.fetchall()}


def fetch_products_needing_backfill(conn) -> list[dict]:
    valid = tuple(VALID_CATEGORIES)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, name, product_url, category, slug
            FROM products
            WHERE active = true
              AND (
                  category IS NULL
                  OR category NOT IN %s
                  OR slug IS NULL
              )
            ORDER BY id
            """,
            (valid,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": row[0],
            "name": row[1],
            "product_url": row[2],
            "category": row[3],
            "slug": row[4],
        }
        for row in rows
    ]


def resolve_category(product_url: str, first_fetch: bool) -> str:
    """
    Fetch the product page and extract category from the breadcrumb.
    Falls back to _BACKFILL_CATEGORY_FALLBACK if the page is gone (404),
    unreachable, or the breadcrumb returns None.
    """
    try:
        resp = fetch_response_with_retry(product_url, warmup=first_fetch)
        html = ensure_html(resp, product_url)
        category = extract_product_category(html)
        if category is not None:
            return category
        print(f"    [CATEGORY] Breadcrumb extraction returned None — using fallback '{_BACKFILL_CATEGORY_FALLBACK}'")
    except Exception as e:
        print(f"    [CATEGORY] Could not fetch page ({e.__class__.__name__}: {e}) — using fallback '{_BACKFILL_CATEGORY_FALLBACK}'")
    return _BACKFILL_CATEGORY_FALLBACK


def main():
    total = 0
    slugs_written = 0
    slug_already_set = 0
    slugs_failed = 0
    categories_written = 0
    categories_already_set = 0
    categories_failed = 0

    conn = get_connection()
    try:
        existing_slugs = fetch_existing_slugs(conn)
        products = fetch_products_needing_backfill(conn)

        total = len(products)
        print(f"Products needing backfill (category null/invalid or slug null): {total}\n")

        first_fetch = True

        for p in products:
            issues = []
            category_needs_update = False
            if p["category"] is None:
                issues.append("category=null")
                category_needs_update = True
            elif p["category"] not in VALID_CATEGORIES:
                issues.append(f"category=invalid({p['category']})")
                category_needs_update = True
            if p["slug"] is None:
                issues.append("slug=null")
            print(f"  id={p['id']}  issues={issues}  name={p['name']}")

            # --- slug ---
            if p["slug"] is None:
                try:
                    slug = generate_slug(p["name"], existing_slugs)
                    existing_slugs.add(slug)
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE products SET slug = %s WHERE id = %s",
                            (slug, p["id"]),
                        )
                    conn.commit()
                    slugs_written += 1
                    print(f"    -> slug written: {slug}")
                except Exception as e:
                    conn.rollback()
                    slugs_failed += 1
                    print(f"    -> ERROR writing slug: {e}")
            else:
                slug_already_set += 1

            # --- category ---
            if not category_needs_update:
                categories_already_set += 1
                continue

            try:
                category = resolve_category(p["product_url"], first_fetch)
                first_fetch = False
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE products SET category = %s WHERE id = %s",
                        (category, p["id"]),
                    )
                conn.commit()
                categories_written += 1
                print(f"    -> category written: {category}")
                time.sleep(1)
            except Exception as e:
                conn.rollback()
                categories_failed += 1
                print(f"    -> ERROR writing category: {e}")

    finally:
        conn.close()

    print(f"\nDone.")
    print(f"  Total:                              {total}")
    print(f"  Slugs written:                      {slugs_written}")
    print(f"  Slug already set:                   {slug_already_set}")
    print(f"  Slugs failed:                       {slugs_failed}")
    print(f"  Categories written:                 {categories_written}")
    print(f"  Category already set (valid):       {categories_already_set}")
    print(f"  Categories failed:                  {categories_failed}")


if __name__ == "__main__":
    main()
