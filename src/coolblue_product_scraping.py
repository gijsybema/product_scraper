
import requests
import time
import random
from bs4 import BeautifulSoup
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9"
}

_SESSION = None

def _get_session() -> requests.Session:
    global _SESSION
    if _SESSION is not None:
        return _SESSION

    retry = Retry(
        total=3,                 # 1 initial try + up to 3 retries
        connect=3,
        read=3,
        status=3,
        backoff_factor=1.0,      # 1s, 2s, 4s...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET", "HEAD"),
        raise_on_status=False,
    )

    adapter = HTTPAdapter(max_retries=retry)
    s = requests.Session()
    s.mount("http://", adapter)
    s.mount("https://", adapter)
    s.headers.update(HEADERS)
    _SESSION = s
    return _SESSION

def parse_product_json_ld(html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue

        if data.get("@type") == "Product":
            return data

    raise ValueError("No Product JSON-LD found")

def scrape_product_details(url: str, timeout=10) -> dict:
    """
    Scrape stable product metadata from a Coolblue product page.
    Used for product discovery / enrichment.
    """
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()

    html = response.text
    product = parse_product_json_ld(html)

    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")

    return {
        "name": product.get("name"),
        "brand": brand,
        "product_url": product.get("url"),
    }

def scrape_product_facts(url: str, timeout=(5, 20)) -> dict:
    """
    Scrape daily product facts (price, availability, rating, review_count).
    Retries transient HTTP failures automatically (429/5xx/timeouts).
    """
    session = _get_session()
    response = session.get(url, timeout=timeout)

    # If still not OK after retries, raise for visibility
    response.raise_for_status()

    html = response.text
    product = parse_product_json_ld(html)

    offers = product.get("offers", {}) or {}
    price = offers.get("price")
    availability = offers.get("availability")

    ratings = product.get("aggregateRating", {}) or {}
    average_rating = ratings.get("ratingValue")
    review_count = ratings.get("reviewCount")

    return {
        "price": price,
        "in_stock": availability is not None and "InStock" in str(availability),
        "rating": average_rating,
        "review_count": review_count,
    }

if __name__ == "__main__":
    # Example usage for test/debug:
    example_url = "https://www.coolblue.nl/product/959897/jbl-tour-one-m3-goud.html"

    product_details = scrape_product_details(example_url)
    print("Product details:", product_details)

    product_facts = scrape_product_facts(example_url)
    print("Product facts:", product_facts)



