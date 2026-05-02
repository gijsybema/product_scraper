#utils.py

import re
import unicodedata
import requests

# Slice A: controlled category enum
VALID_CATEGORIES = frozenset({"headphones", "earbuds", "speakers", "soundbars"})

_CATEGORY_MAP = {
    "hoofdtelefoon": "headphones",
    "koptelefoon": "headphones",
    "in-ear hoofdtelefoon": "earbuds",
    "oortelefoon": "earbuds",
    "earbud": "earbuds",
    "speaker": "speakers",
    "soundbar": "soundbars",
}

# Pre-sorted once at import time; longest key first so specific keys beat general ones
_SORTED_KEYS = tuple(sorted(_CATEGORY_MAP, key=len, reverse=True))

# Guard: every map value must be a valid category — catches typos at import time
assert all(v in VALID_CATEGORIES for v in _CATEGORY_MAP.values()), (
    "BUG: _CATEGORY_MAP contains a value not in VALID_CATEGORIES"
)

def normalize_category(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        print("[CATEGORY] Warning: empty category value")
        return None
    lowered = raw.strip().lower()
    if lowered in _CATEGORY_MAP:
        return _CATEGORY_MAP[lowered]
    for key in _SORTED_KEYS:
        if key in lowered:
            return _CATEGORY_MAP[key]
    print(f"[CATEGORY] Warning: unrecognized category '{raw}'")
    return None

def generate_slug(name: str, existing_slugs: set[str]) -> str:
    if not name or not name.strip():
        raise ValueError("Product name must not be empty")
    existing_slugs = set(existing_slugs)
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    lowered = ascii_name.lower()
    hyphenated = re.sub(r"[^a-z0-9]+", "-", lowered)
    slug = hyphenated.strip("-")
    if not slug:
        raise ValueError(f"Product name '{name}' produces an empty slug")
    if slug not in existing_slugs:
        return slug
    counter = 2
    while f"{slug}-{counter}" in existing_slugs:
        counter += 1
    return f"{slug}-{counter}"


def validate_product_details(details: dict) -> tuple[bool, list[str]]:
    """
    Validate product metadata before upsert_product.
    Returns (is_valid, [error_messages]).
    """
    errors = []

    name = details.get("name")
    if not name or not str(name).strip():
        errors.append("missing or empty 'name'")

    product_url = details.get("product_url")
    if not product_url or not str(product_url).strip():
        errors.append("missing or empty 'product_url'")
    elif not str(product_url).startswith(("http://", "https://")):
        errors.append(f"invalid 'product_url': {product_url!r}")

    image_url = details.get("image_url")
    if not image_url or not str(image_url).strip():
        errors.append("missing or empty 'image_url'")
    elif not str(image_url).startswith(("http://", "https://")):
        errors.append(f"invalid 'image_url': {image_url!r}")

    category = details.get("category")
    if category is not None and category not in VALID_CATEGORIES:
        errors.append(f"invalid 'category': {category!r}")

    return (len(errors) == 0, errors)


def validate_price_facts(facts: dict) -> tuple[bool, list[str]]:
    """
    Validate daily price facts before upsert_price_history.
    Returns (is_valid, [error_messages]).
    """
    errors = []

    price = facts.get("price")
    if price is None:
        errors.append("missing 'price'")
    else:
        try:
            if float(price) <= 0:
                errors.append(f"'price' must be > 0, got {price!r}")
        except (TypeError, ValueError):
            errors.append(f"'price' must be numeric, got {price!r}")

    in_stock = facts.get("in_stock")
    if not isinstance(in_stock, bool):
        errors.append(f"'in_stock' must be boolean, got {type(in_stock).__name__}: {in_stock!r}")

    return (len(errors) == 0, errors)


def fetch_debug(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.7,en;q=0.6",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }

    with requests.Session() as s:
        r = s.get(url, headers=headers, timeout=30, allow_redirects=True)
        print("STATUS:", r.status_code)
        print("FINAL URL:", r.url)
        print("LEN:", len(r.text))
        print("SERVER:", r.headers.get("server"))
        print("CACHE:", r.headers.get("x-cache"), r.headers.get("cf-cache-status"))
        print("TITLE SNIP:", r.text[:2000])

        # snelle signalen
        lowered = r.text.lower()
        print("has product cards?", "product-card" in lowered or "productkaart" in lowered)
        print("has next data?", "__next_data__" in lowered)
        block_words = ["captcha", "access denied", "blocked", "bot", "robot"]
        block_signals = ["captcha", "access denied", "blocked", "verify you are human", "too many requests"]
        hits = [w for w in block_signals if w in lowered]
        print("block signals:", hits)
        return r.text

def print_progress(current, total, identifier=None, elapsed=None, avg_time=None, est_time_left=None):
    """
    Print progress information for long-running operations.
    
    Args:
        current: Current item index (0-based)
        total: Total number of items
        identifier: Optional identifier to display (e.g., SKU, product_id)
        elapsed: Total elapsed time in seconds
        avg_time: Average time per item in seconds
        est_time_left: Estimated time remaining in seconds
    """
    percent = 100 * ((current + 1) / total)
    msg = f"[{current+1}/{total}] ({percent:.1f}%)"
    
    if identifier is not None:
        # Handle different identifier types
        if isinstance(identifier, int):
            msg += f" Product ID: {identifier}"
        elif isinstance(identifier, str):
            # If string looks numeric, treat as SKU, otherwise just display
            if identifier.isdigit():
                msg += f" SKU: {identifier}"
            else:
                msg += f" {identifier}"
        else:
            # For dict-like identifiers, show the most relevant key
            if "sku" in identifier:
                msg += f" SKU: {identifier['sku']}"
            elif "product_id" in identifier:
                msg += f" Product ID: {identifier['product_id']}"
    
    if elapsed is not None:
        msg += f" | Elapsed: {elapsed:.1f}s"
    
    if avg_time is not None and est_time_left is not None:
        eta_minutes = est_time_left / 60
        msg += f" | Avg: {avg_time:.2f}s/item, ETA: {est_time_left:.1f}s ({eta_minutes:.1f} min)"
    
    print(msg, flush=True)

if __name__ == "__main__":
    url = "https://www.coolblue.nl/hoofdtelefoons/filter"
    fetch_debug(url)