
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
# Spec key mappings per category
# ----------------------------

# Maps Coolblue Dutch label → stored English key, per category.
# Only these keys are extracted and stored in the specs JSONB column.
_SPEC_KEYS: dict[str, dict[str, str]] = {
    "headphones": {
        "Type oorkussen": "ear_cup_type",
        "Bluetooth": "bluetooth",
        "Bluetooth-versie": "bluetooth_version",
        "Noise cancelling": "noise_cancelling",
        "Kwaliteit noise cancelling": "noise_cancelling_quality",
        "Ingebouwde microfoon": "built_in_microphone",
        "Gemiddelde accuduur": "battery_life",
        "Geluidsweergave": "audio_rendering",
        "Gewicht in gram": "weight_grams",
        "Waterbestendig": "water_resistant",
        "Kleur": "color",
        "Materiaal": "material",
        "Type stroomvoorziening": "power_type",
        "Kabel los te koppelen": "detachable_cable",
    },
    "earbuds": {
        "Type oorkussen": "ear_cup_type",
        "Bluetooth": "bluetooth",
        "Bluetooth-versie": "bluetooth_version",
        "Noise cancelling": "noise_cancelling",
        "Kwaliteit noise cancelling": "noise_cancelling_quality",
        "Ingebouwde microfoon": "built_in_microphone",
        "Gemiddelde accuduur": "battery_life",
        "Geluidsweergave": "audio_rendering",
        "Gewicht in gram": "weight_grams",
        "Waterbestendig": "water_resistant",
        "Kleur": "color",
        "Materiaal": "material",
        "Type stroomvoorziening": "power_type",
        "Volledig draadloze oordopjes": "fully_wireless",
        "Oplaadcase": "charging_case",
        "Accuduur case": "battery_life_case",
        "Draadloos opladen": "wireless_charging",
        "IP-certificering": "ip_rating",
        "Multipoint pairing": "multipoint_pairing",
    },
    "speakers": {
        "Type speaker": "speaker_type",
        "Formaat draadloze speaker": "speaker_size",
        "Gewicht": "weight",
        "Kleur": "color",
        "Ingebouwde microfoon": "built_in_microphone",
        "Gemiddelde accuduur": "battery_life",
        "Maximale accu/batterijduur": "battery_life_max",
        "IP-certificering": "ip_rating",
        "Bluetooth": "bluetooth",
        "Wifi ingebouwd": "wifi",
        "Multiroom audio": "multiroom",
        "Geluidsweergave": "audio_rendering",
        "Bediening via app": "app_control",
        "Waterdichtheid": "water_resistance",
        "NFC": "nfc",
        "Radio": "radio",
        "Afstandsbediening": "remote_control",
        "Bediening via knoppen op apparaat": "physical_controls",
    },
    "soundbars": {
        "Gewicht": "weight",
        "Kleur": "color",
        "Losse subwoofer": "separate_subwoofer",
        "Aantal audio kanalen": "audio_channels",
        "Aantal subwooferkanalen": "subwoofer_channels",
        "Geluidsweergave": "audio_rendering",
        "Surround sound": "surround_sound",
        "Hi-res audio": "hi_res_audio",
        "HDMI-aansluiting": "hdmi",
        "HDMI ARC (Audio Return Channel)": "hdmi_arc",
        "Bluetooth": "bluetooth",
        "Wifi ingebouwd": "wifi",
        "Speelt van netwerk": "plays_from_network",
        "Multiroom audio": "multiroom",
        "NFC": "nfc",
        "Radio": "radio",
        "Spotify Connect": "spotify_connect",
        "AirPlay": "airplay",
        "Google Cast": "google_cast",
        "Compatibel met smartphone / apps": "smartphone_compatible",
        "Smart home platform": "smart_home_platform",
        "Bediening via app": "app_control",
    },
}


def extract_product_description(html: str) -> str | None:
    """
    Extract the product description text from the 'Omschrijving' section
    inside section#product-information.
    Returns None if the section or heading is absent.
    """
    soup = BeautifulSoup(html, "html.parser")
    sec = soup.find("section", id="product-information")
    if not sec:
        return None

    omschrijving_div = None
    for h3 in sec.find_all("h3"):
        if "Omschrijving" in h3.get_text():
            omschrijving_div = h3.parent
            break

    if omschrijving_div is None:
        return None

    collapse = omschrijving_div.find("div", id=lambda x: x and x.startswith("collapse-content-"))
    if not collapse:
        return None

    text = collapse.get_text(separator=" ", strip=True)
    return text or None


def extract_product_specs(html: str, category: str) -> dict | None:
    """
    Extract category-specific specs from section#product-specifications.
    Parses every <tr>: key from <th>, value from last <td> (text or SVG aria-label).
    Returns only keys defined in _SPEC_KEYS for the given category.
    Returns None if the specs section is absent; {} if category has no mapping yet.
    """
    soup = BeautifulSoup(html, "html.parser")
    sec = soup.find("section", id="product-specifications")
    if not sec:
        return None

    key_map = _SPEC_KEYS.get(category, {})

    raw: dict[str, str] = {}
    for tr in sec.find_all("tr"):
        th = tr.find("th")
        tds = tr.find_all("td")
        if not th or len(tds) < 2:
            continue
        label = th.get_text(strip=True)
        value_td = tds[-1]
        svg = value_td.find("svg")
        if svg and svg.get("aria-label"):
            value = svg["aria-label"]
        else:
            value = value_td.get_text(strip=True)
        raw[label] = value

    return {eng_key: raw[nl_label] for nl_label, eng_key in key_map.items() if nl_label in raw}


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
    description = extract_product_description(html)
    specs = extract_product_specs(html, category) if category else None

    return {
        "name": product.get("name"),
        "brand": brand,
        "product_url": product.get("url"),
        "image_url": image_url,
        "all_image_urls": all_image_urls,
        "category": category,
        "description": description,
        "specs": specs,
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



