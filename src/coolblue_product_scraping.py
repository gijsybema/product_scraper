
from multiprocessing.sharedctypes import Value
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

def scrape_coolblue_product_info(url, timeout=10):
    """
    Given a Coolblue product URL, fetches the price, availability, name, brand, and url from the product's JSON-LD.
    Returns a dictionary with the extracted info.
    """
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()
    time.sleep(random.uniform(2, 4))  # Delay to lower chance of being blocked

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Check for common scraping failure indicators
    if (
        "captcha" in html.lower()
        or "access denied" in html.lower()
        or len(html) < 1000
    ):
        raise ValueError(
            f"Scraping may have failed - page might be blocked or invalid. HTML length: {len(html)}"
        )

    scripts = soup.find_all("script", type="application/ld+json")

    product_info = {}
    for script in scripts:
        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue

        if data.get("@type") != "Product":
            continue

        offers = data.get("offers", {})
        price = offers.get("price")
        availability = offers.get("availability")
        price_cents = int(float(price) * 100) if price is not None else None
        in_stock = availability and "InStock" in availability

        product_info = {
            "name": data.get("name"),
            "brand": data.get("brand", {}).get("name") if isinstance(data.get("brand"), dict) else data.get("brand"),
            "price_cents": price_cents,
            "in_stock": bool(in_stock),
            "url": data.get("url"),
        }
        # Optional: add more fields from the product data if needed
        break  # Stop after first Product entity

    return product_info

if __name__ == "__main__":
    # Example usage for test/debug:
    example_url = "https://www.coolblue.nl/product/959897/jbl-tour-one-m3-goud.html"
    product_data = scrape_coolblue_product_info(example_url)
    print(product_data)
