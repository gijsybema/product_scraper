
import requests
import time
import random
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import re

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "nl-NL,nl;q=0.9"
}

# Compile the product href regex once at the module level
PRODUCT_HREF_RE = re.compile(r"^/product/\d+/.+\.html$")


def extract_product_id_from_url(url):
    """Extract product ID from a Coolblue product URL."""
    match = re.search(r"/product/(\d+)/", url)
    if match:
        return int(match.group(1))
    raise ValueError(f"Could not extract product ID from URL: {url}")


def extract_name_from_url(url):
    """Extract and format product name from URL slug."""
    # Extract the slug part (between product ID and .html)
    match = re.search(r"/product/\d+/(.+?)\.html", url)
    if not match:
        raise ValueError(f"Could not extract name from URL: {url}")
    
    slug = match.group(1)
    # Replace hyphens with spaces and apply title case
    name = slug.replace("-", " ").title()
    return name


def get_coolblue_products_from_category(url, timeout=10):
    """
    Given a category page URL from Coolblue, scrape the products from that page.
    Returns a list of product dictionaries with product_id, name, url, and active.
    """
    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()

    # small random delay to lower chance of being blocked
    time.sleep(random.uniform(2, 4))

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Check for common error indicators
    if (
        "captcha" in html.lower()
        or "access denied" in html.lower()
        or len(html) < 1000
    ):
        raise ValueError(
            f"Scraping may have failed - page might be blocked or invalid. HTML length: {len(html)}"
        )

    products = []
    seen_urls = set()
    
    for a in soup.select('a[href^="/product/"]'):
        href = a.get("href", "")
        if PRODUCT_HREF_RE.match(href):
            full_url = urljoin("https://www.coolblue.nl", href)
            
            # Dedupe by URL
            if full_url not in seen_urls:
                seen_urls.add(full_url)
                try:
                    product = {
                        "product_id": extract_product_id_from_url(full_url),
                        "name": extract_name_from_url(full_url),
                        "url": full_url,
                        "active": True
                    }
                    products.append(product)
                except ValueError as e:
                    # Skip URLs that can't be parsed
                    print(f"Warning: Skipping invalid URL {full_url}: {e}")
                    continue

    return products

def get_all_coolblue_products(base_category_url, max_pages=20, timeout=10):
    """
    Crawl all products from a Coolblue category's paginated listing.

    Args:
        base_category_url (str): The base URL of the Coolblue category (first page of listings).
        max_pages (int): Maximum number of pages to iterate through to avoid infinite loops.
        timeout (int): requests timeout in seconds

    Returns:
        list: All found products across all paginated pages (deduplicated by URL, in order).
              Each product is a dict with product_id, name, url, and active.
    """
    all_products = []
    seen_urls = set()

    for page in range(1, max_pages + 1):
        url = f"{base_category_url}?pagina={page}"
        try:
            page_products = get_coolblue_products_from_category(url, timeout=timeout)
            if not page_products:
                # No products found on this page, likely end of pagination
                break
            
            # Dedupe by URL while preserving order
            for product in page_products:
                if product["url"] not in seen_urls:
                    seen_urls.add(product["url"])
                    all_products.append(product)
                    
        except (requests.exceptions.HTTPError, ValueError) as e:
            # Page doesn't exist or scraping failed - reached end of pagination
            print(f"Stopped at page {page}: {e}")
            break

    return all_products

if __name__ == "__main__":
    # Example usage / debug
    base_category_url = "https://www.coolblue.nl/hoofdtelefoons/filter"
    products = get_all_coolblue_products(base_category_url)
    print(products)
    print(f"Total products found: {len(products)}")

