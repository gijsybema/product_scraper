import requests
import time
import random
from bs4 import BeautifulSoup
import json
import pprint

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9"
}

url = "https://www.coolblue.nl/product/959897/jbl-tour-one-m3-goud.html"
timeout = 10

response = requests.get(url, headers=HEADERS, timeout=timeout)
response.raise_for_status()

# small random delay to lower the chance of being blocked
time.sleep(random.uniform(2, 4))

# Get HTML and check if scraping worked
html = response.text
print(html[:10])
soup = BeautifulSoup(html, "html.parser")

# Check for common error indicators
if "captcha" in html.lower() or "access denied" in html.lower() or len(html) < 1000:
    raise ValueError(f"Scraping may have failed - page might be blocked or invalid. HTML length: {len(html)}")

#print(soup.prettify())

# application/ld+json is structured data accoording to Schema.org
scripts = soup.find_all("script", type="application/ld+json")

len(scripts)
# there are multiple JSON-LD scripts because they describe different entities

#print(scripts[0])
# this first one contains BreadcrumbList: information about navigation

#print(scripts[1])
# this second one contains Product info 

# We'll store the extracted product info in this dictionary.
product_info = {}

# Loop through all <script type="application/ld+json"> tags to find and extract product info
for script in scripts:
    try:
        # Parse the JSON-LD data from the script tag
        data = json.loads(script.string)
    except (TypeError, json.JSONDecodeError):
        # Skip this script if it can't be decoded or is empty
        continue

    # We're only interested in scripts that define a Product entity
    if data.get("@type") != "Product":
        continue

    pprint.pprint(data, indent=2, width=120)  # Pretty-print the full product data for inspection

    # Extract price and availability information from the "offers" field
    offers = data.get("offers", {})
    price = offers.get("price")
    availability = offers.get("availability")

    # Extract average rating and review count
    ratings = data.get("aggregateRating", {})
    average_rating = ratings.get("ratingValue")
    review_count = ratings.get("reviewCount")

    # Convert price to cents (if price is present)
    price_cents = int(float(price) * 100) if price is not None else None

    # Determine if the product is in stock based on the "availability" value
    in_stock = availability and "InStock" in availability

    # Extract SKU (Stock Keeping Unit) if available
    sku = data.get("sku")

    # You can store additional values here as needed
    product_info = {
        "name": data.get("name"),
        "brand": data.get("brand", {}).get("name") if isinstance(data.get("brand"), dict) else data.get("brand"),
        "price_cents": price_cents,
        "in_stock": bool(in_stock),
        "average_rating": average_rating,
        "review_count": review_count,
        "url": data.get("url"),
        "sku": sku
    }
    # Break after finding the first Product entity (optional)
    break

# Now you can use product_info later in your program
print(product_info)
