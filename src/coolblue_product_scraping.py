
import requests
import time
import random
from bs4 import BeautifulSoup
import json

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9"
}

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


def scrape_product_facts(url: str, timeout=10) -> dict:
    """
    Scrape daily product facts (price, availability).
    Used for price history collection.
    """
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()

    html = response.text
    product = parse_product_json_ld(html)

    offers = product.get("offers", {})
    price = offers.get("price")
    availability = offers.get("availability")

    ratings = product.get("aggregateRating", {})
    average_rating = ratings.get("ratingValue")
    review_count = ratings.get("reviewCount")

    return {
        "price": price,
        "in_stock": availability is not None and "InStock" in availability,
        "rating": average_rating,
        "review_count": review_count
    }


if __name__ == "__main__":
    # Example usage for test/debug:
    example_url = "https://www.coolblue.nl/product/959897/jbl-tour-one-m3-goud.html"

    product_details = scrape_product_details(example_url)
    print("Product details:", product_details)

    product_facts = scrape_product_facts(example_url)
    print("Product facts:", product_facts)



