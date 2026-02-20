"""
Scrape product URLs + SKU + Name from a Coolblue category filter page.

Strategy:
1) Parse schema.org JSON-LD ItemList (<script type="application/ld+json">) when available (most stable).
2) Fallback to parsing <a href="/product/..."> links.
3) Paginate via ?pagina= until 404 or no new products.
"""

import requests
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from typing import Optional, List, Dict
import re
import json

HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.7,en;q=0.6",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
}

BASE = "https://www.coolblue.nl"
# Compile the product href regex once at the module level
PRODUCT_ID_IN_PATH_RE  = re.compile(r"^/product/(\d+)/")


def polite_sleep(min_s: float = 2.5, max_s: float = 5.0) -> None:
    time.sleep(random.uniform(min_s, max_s))

def extract_product_id_from_url(url: str) -> Optional[int]:
    """
    Extract product id from full product URL, e.g.
    https://www.coolblue.nl/product/962722/sony-wh-1000xm6-zwart.html
    """
    path = urlparse(url).path
    m = PRODUCT_ID_IN_PATH_RE.match(path)
    if not m:
        return None
    return int(m.group(1))


def extract_name_from_url(url: str) -> Optional[str]:
    """
    Fallback name extraction from slug.
    Prefer JSON-LD 'name' when possible.
    """
    path = urlparse(url).path
    m = re.search(r"^/product/\d+/(.+)$", path)
    if not m:
        return None
    slug = m.group(1).split("?", 1)[0].split("#", 1)[0]
    slug = slug.replace(".html", "")
    name = slug.replace("-", " ")

    # keep tokens with digits as uppercase
    words = []
    for w in name.split():
        if any(c.isdigit() for c in w):
            words.append(w.upper())
        else:
            words.append(w.capitalize())
    return " ".join(words) if words else None


def extract_products_from_ld_json(html: str) -> List[Dict[str, str]]:
    """
    Extract products (sku, product_url, name) from schema.org ItemList JSON-LD.
    """
    soup = BeautifulSoup(html, "html.parser")
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})

    products: List[Dict[str, str]] = []

    for s in scripts:
        if not s.string:
            continue
        try:
            data = json.loads(s.string)
        except json.JSONDecodeError:
            continue

        blocks = data if isinstance(data, list) else [data]
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("@type") != "ItemList":
                continue

            for item in block.get("itemListElement", []):
                if not isinstance(item, dict):
                    continue
                if item.get("@type") != "Product":
                    continue

                url = item.get("url") or item.get("@id")
                sku = item.get("sku") or item.get("productID")
                name = item.get("name")

                if url and sku:
                    products.append({
                        "sku": str(sku),
                        "product_url": str(url),
                        "name": str(name) if name else ""
                    })

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for p in products:
        if p["product_url"] not in seen:
            seen.add(p["product_url"])
            # ensure name fallback if empty
            if not p["name"]:
                p["name"] = extract_name_from_url(p["product_url"]) or ""
            deduped.append(p)

    return deduped

def extract_products_from_anchors(html: str) -> List[Dict[str, str]]:
    """
    Fallback: parse product URLs from <a href="/product/...">.
    """
    soup = BeautifulSoup(html, "html.parser")
    products: List[Dict[str, str]] = []
    seen = set()

    for a in soup.select('a[href^="/product/"]'):
        href = a.get("href", "")
        href = href.split("?", 1)[0].split("#", 1)[0]  # normalize
        full_url = urljoin(BASE, href)

        pid = extract_product_id_from_url(full_url)
        if not pid:
            continue

        if full_url in seen:
            continue
        seen.add(full_url)

        products.append({
            "sku": str(pid),
            "product_url": full_url,
            "name": extract_name_from_url(full_url) or ""
        })

    return products

def fetch_html(session, url, timeout=20, retries=2):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            r = session.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
        except requests.RequestException as e:
            last_exc = e
            time.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
            continue

        if r.status_code == 404:
            return None

        if r.status_code in (429, 503):
            time.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
            continue

        r.raise_for_status()
        return r.text

    # After retries
    if last_exc:
        raise last_exc
    r.raise_for_status()


def get_products_from_category_page(session: requests.Session, url: str, timeout=20, retries=2):
    """
    Fetch one page and extract products.
    Retries if extraction yields 0 (handles intermittent HTML variants).
    """
    last_products = []
    for attempt in range(retries + 1):
        html = fetch_html(session, url, timeout=timeout)

        if html is None:
            return None  # page not found => stop pagination

        # Primary JSON-LD, fallback anchors
        products = extract_products_from_ld_json(html)
        if not products:
            products = extract_products_from_anchors(html)

        if products:
            return products

        # If 0 products: backoff + retry
        last_products = products
        time.sleep((2 ** attempt) + random.uniform(0.5, 1.5))

    return last_products  # still empty


def get_all_coolblue_products(base_category_url: str, max_pages=50, timeout=20):
    """
    Pagination via ?pagina=1..N (your preferred method),
    stop when a page adds 0 NEW products.
    """
    all_products = []
    seen_urls = set()
    zero_new_streak = 0

    with requests.Session() as session:
        for page in range(1, max_pages + 1):
            polite_sleep(2.5, 5.0)  # between requests

            url = f"{base_category_url}?pagina={page}"
            page_products = get_products_from_category_page(session, url, timeout=timeout, retries=2)

            if page_products is None:
                print(f"Page {page} not found (404): {url}. Stopping.")
                break

            new_count = 0
            for p in page_products:
                if p["product_url"] not in seen_urls:
                    seen_urls.add(p["product_url"])
                    all_products.append(p)
                    new_count += 1

            print(f"Page {page}: found {len(page_products)} products, new {new_count}")

            # Stop when this page contributes no NEW products
            # (prevents infinite loops + handles glitches better than 'if not page_products')
            if new_count == 0:
                zero_new_streak += 1
                if zero_new_streak >= 2:
                    break
            else:
                zero_new_streak = 0

    return all_products

if __name__ == "__main__":
    # Example usage / debug
    base_category_url = "https://www.coolblue.nl/hoofdtelefoons/filter"

    products = get_all_coolblue_products(base_category_url, max_pages=50, timeout=20)
    print(f"Total unique products found: {len(products)}")
    for p in products[:10]:
        print(p)
