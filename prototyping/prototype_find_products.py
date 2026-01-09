from typing import Any
import requests
import json
import time
import random
from bs4 import BeautifulSoup
import pprint
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

base_category_url = "https://www.coolblue.nl/hoofdtelefoons/filter"
timeout = 10

# PRODUCT_HREF_RE should be kept as a global variable (defined once outside the function)
# so it can be reused in multiple places without recompiling and to keep the regex logic in one spot.
PRODUCT_HREF_RE = re.compile(r"^/product/\d+/.+\.html$")

response = requests.get(base_category_url, headers=HEADERS, timeout=timeout)
response.raise_for_status()

# small random delay to lower the chance of being blocked
time.sleep(random.uniform(2, 4))

# Get HTML and check if scraping worked
html = response.text
print(html[:100])
soup = BeautifulSoup(html, "html.parser")

# Check for common error indicators
if "captcha" in html.lower() or "access denied" in html.lower() or len(html) < 1000:
    raise ValueError(f"Scraping may have failed - page might be blocked or invalid. HTML length: {len(html)}")

print(soup.prettify())

urls = []
for a in soup.select('a[href^="/product/"]'):
    href = a.get("href", "")
    print(href)
    if PRODUCT_HREF_RE.match(href):
        urls.append(urljoin("https://www.coolblue.nl", href))

urls = list(dict.fromkeys(urls))
pprint.pprint(urls)
print(len(urls))


def get_coolblue_product_urls_from_category(url):
    """
    Given a category page URL from Coolblue, scrape the product URLs from that page.
    Returns a list of absolute product URLs found.
    """

    response = requests.get(url, headers=HEADERS, timeout=timeout)
    response.raise_for_status()

    # small random delay to lower the chance of being blocked
    time.sleep(random.uniform(2, 4))

    html = response.text
    soup = BeautifulSoup(html, "html.parser")

    # Check for common error indicators
    if ("captcha" in html.lower() or 
        "access denied" in html.lower() or 
        len(html) < 1000):
        raise ValueError(
            f"Scraping may have failed - page might be blocked or invalid. HTML length: {len(html)}"
        )

    urls = []
    for a in soup.select('a[href^="/product/"]'):
        href = a.get("href", "")
        if PRODUCT_HREF_RE.match(href):
            urls.append(urljoin("https://www.coolblue.nl", href))

    # dedupe in order
    urls = list(dict.fromkeys(urls))
    return urls

urls = get_coolblue_product_urls_from_category(base_category_url)
print(len(urls))
pprint.pprint(urls[:5])

# found all urls on the first page
# now do pagination

max_pages = 20
all_urls = []

for page in range(1, max_pages + 1):

    url = f"{base_category_url}?pagina={page}"
    try:
        page_urls = get_coolblue_product_urls_from_category(url)
        #print(page_urls)
        print(f"Page: {page}, found {len(page_urls)} products")
        
        if not page_urls:
            break
        
        all_urls.extend(page_urls)
    except (requests.exceptions.HTTPError, ValueError) as e:
        # Page doesn't exist or scraping failed - reached end of pagination
        print(f"Stopped at page {page}: {e}")
        break

all_urls = list(dict.fromkeys(all_urls))
print(all_urls)
pprint.pprint(all_urls)
print(len(all_urls))


def get_all_coolblue_product_urls(url=base_category_url, max_pages=20):
    """
    Crawl all product URLs from a Coolblue category's paginated listing.

    Args:
        base_category_url (str): The base URL of the Coolblue category (first page of listings).
        max_pages (int): Maximum number of pages to iterate through to avoid infinite loops.

    Returns:
        list: All found product URLs across all paginated pages (deduplicated, in order).
    """
    all_urls = []

    for page in range(1, max_pages + 1):
        url = f"{url}?pagina={page}"
        try:
            page_urls = get_coolblue_product_urls_from_category(url)
            if not page_urls:
                # No products found on this page, likely end of pagination
                break
            
            all_urls.extend(page_urls)
        except (requests.exceptions.HTTPError, ValueError) as e:
            # Page doesn't exist or scraping failed - reached end of pagination
            print(f"Stopped at page {page}: {e}")
            break

    # Dedupe while preserving order
    all_urls = list(dict.fromkeys(all_urls))
    return all_urls

all_urls = get_all_coolblue_product_urls(base_category_url)
print(all_urls)
pprint.pprint(all_urls)
print(len(all_urls))

