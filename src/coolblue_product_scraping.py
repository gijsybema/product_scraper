
import requests
import time
import random
from bs4 import BeautifulSoup
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from src.utils import normalize_category
except ModuleNotFoundError:
    from utils import normalize_category

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nl-NL,nl;q=0.9",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

_SESSION = None


# ----------------------------
# Session + network layer
# ----------------------------

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

def _is_soft_block(resp: requests.Response) -> bool:
    """
    Coolblue can return HTTP 202 with an empty body (or other empty HTML).
    Treat that as a retriable "soft block".
    """
    if resp.status_code == 202:
        return True
    if resp.content is None or len(resp.content) == 0:
        return True
    # Sometimes content exists but is blank/whitespace
    if (resp.text or "").strip() == "":
        return True
    return False

def _warmup_session(session: requests.Session, timeout=(5, 20)) -> None:
    """
    Optional: hit homepage to set cookies/session.
    Often helps against bot mitigation.
    """
    try:
        session.get("https://www.coolblue.nl/", timeout=timeout, allow_redirects=True)
    except requests.RequestException:
        pass    

def fetch_response_with_retry(
    url: str,
    *,
    timeout=(5, 20),
    max_attempts: int = 6,
    warmup: bool = True,
    ) -> requests.Response:
    """
    Fetches a Response, retrying:
    - network timeouts/connection errors (requests)
    - HTTP 429/5xx (via urllib3 Retry configured on the session)
    - soft-block responses (202 and/or empty body)
    """
    session = _get_session()
    if warmup:
        _warmup_session(session, timeout=timeout)

    last_resp = None
    last_err = None

    # Referer sometimes helps; keep it light
    headers = {"Referer": "https://www.coolblue.nl/"}

    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[FETCH] Attempt {attempt}/{max_attempts} → {url}")
            resp = session.get(url, timeout=timeout, allow_redirects=True, headers=headers)
            last_resp = resp

            # If 4xx/5xx after retries -> fail hard
            if resp.status_code >= 400:
                resp.raise_for_status()

            # Soft-block / empty body -> backoff + retry
            if _is_soft_block(resp):
                sleep_s = min(2 ** attempt, 30) + random.random()
                time.sleep(sleep_s)
                print(
                    f"[FETCH] Soft-block detected "
                    f"(status={resp.status_code}, len={len(resp.content)}) "
                    f"→ sleeping {sleep_s:.2f}s"
                )
                continue

            print(
                f"[FETCH] Success "
                f"(status={resp.status_code}, len={len(resp.content)})"
            )
            return resp

        except (requests.Timeout, requests.ConnectionError) as e:
            last_err = e
            sleep_s = min(2 ** attempt, 30) + random.random()
            time.sleep(sleep_s)
            continue

    # Useful debug on failure
    if last_resp is not None:
        raise ValueError(
            f"Failed to fetch usable response after {max_attempts} attempts for {url}. "
            f"Last status={last_resp.status_code}, "
            f"content-type={last_resp.headers.get('Content-Type')}, "
            f"len(content)={0 if last_resp.content is None else len(last_resp.content)}"
        )
    raise ValueError(f"Failed to fetch {url} after {max_attempts} attempts. Last error: {last_err!r}")

# ----------------------------
# Validation layer
# ----------------------------
def ensure_html(response: requests.Response, url: str) -> str:
    """
    Final validation: we should have non-empty HTML.
    This is called only AFTER fetch_response_with_retry succeeded.
    """
    response.raise_for_status()

    if response.content is None or len(response.content) == 0:
        raise ValueError(
            f"Empty response body for {url}. "
            f"status={response.status_code}, content-type={response.headers.get('Content-Type')}"
        )

    html = response.text
    if html is None or html.strip() == "":
        raise ValueError(
            f"Empty/blank HTML text for {url}. "
            f"status={response.status_code}, content-type={response.headers.get('Content-Type')}"
        )

    # Optional sanity check (keeps false positives low)
    content_type = (response.headers.get("Content-Type") or "").lower()
    if "text/html" not in content_type and "<html" not in html.lower():
        snippet = html[:300].replace("\n", " ")
        raise ValueError(
            f"Non-HTML response for {url}. "
            f"status={response.status_code}, content-type={response.headers.get('Content-Type')}, "
            f"snippet={snippet!r}"
        )

    print("[VALIDATE] HTML validated successfully")
    return html

# ----------------------------
# Parsing layer
# ----------------------------
def parse_product_json_ld(html: str) -> dict:
    print("[PARSE] Searching for Product JSON-LD")
    soup = BeautifulSoup(html, "html.parser")

    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue

        if data.get("@type") == "Product":
            print("[PARSE] Product JSON-LD found")
            return data

    # Helpful debug: show a tiny snippet so you can see if it's a bot page
    snippet = html[:400].replace("\n", " ")
    raise ValueError(f"[PARSE] No Product JSON-LD found. HTML snippet: {snippet!r}")

# ----------------------------
# Extraction layer of product details
# ----------------------------
def extract_product_images(html: str, product_name: str, fallback_images) -> tuple[str | None, list[str]]:
    soup = BeautifulSoup(html, "html.parser")

    gallery_image_urls = []
    seen = set()

    product_name = (product_name or "").lower()

    for img in soup.find_all("img"):
        src = img.get("src")
        alt = (img.get("alt") or "").lower()

        if not src:
            continue

        if "image.coolblue.nl" not in src:
            continue

        if "/transparent/" in src:
            continue

        if product_name not in alt:
            continue

        # Deduplicatie op image id
        image_id = src.rstrip("/").split("/")[-1]

        if image_id in seen:
            continue

        seen.add(image_id)

        # Forceer consistente resolutie
        clean_url = f"https://image.coolblue.nl/max/700xauto/products/{image_id}"
        gallery_image_urls.append(clean_url)

    # Fallback naar JSON-LD image(s)
    if isinstance(fallback_images, list):
        fallback_main = fallback_images[0] if fallback_images else None
        fallback_all = fallback_images
    else:
        fallback_main = fallback_images
        fallback_all = [fallback_images] if fallback_images else []

    if gallery_image_urls:
        return gallery_image_urls[0], gallery_image_urls

    return fallback_main, fallback_all


def extract_product_category(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")

    scripts = soup.find_all("script", type="application/ld+json")
    for script in scripts:
        try:
            data = json.loads(script.string)
        except (TypeError, json.JSONDecodeError):
            continue

        if data.get("@type") != "BreadcrumbList":
            continue

        items = data.get("itemListElement", [])
        if not items:
            return None

        for item in items:
            category = normalize_category(item.get("name"))
            if category is not None:
                return category

    return None

# ----------------------------
# Public scraping functions
# ----------------------------
def scrape_product_details(url: str, timeout=(5,20)) -> dict:
    """
    Scrape stable product metadata from a Coolblue product page.
    Used for product discovery / enrichment.
    """
    print(f"[DETAILS] Start scraping: {url}")
    resp = fetch_response_with_retry(url, timeout=timeout)
    html = ensure_html(resp, url)

    product = parse_product_json_ld(html)

    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")

    # JSON-LD fallback images
    fallback_images = product.get("image")

    image_url, all_image_urls = extract_product_images(
        html,
        product.get("name"),
        fallback_images
    )

    category = extract_product_category(html)

    return {
        "name": product.get("name"),
        "brand": brand,
        "product_url": product.get("url"),
        "image_url": image_url,
        "all_image_urls": all_image_urls,
        "category": category,
    }

def scrape_product_facts(url: str, timeout=(5, 20)) -> dict:
    """
    Scrape daily product facts (price, availability, rating, review_count).
    Retries transient HTTP failures automatically (429/5xx/timeouts).
    """
    print(f"[FACTS] Start scraping: {url}")
    resp = fetch_response_with_retry(url, timeout=timeout)
    html = ensure_html(resp, url)

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



