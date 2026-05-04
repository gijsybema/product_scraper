"""
inspect_product_page.py — dev tool for exploring a Coolblue product page's DOM.

Run before implementing a new category parser to understand the HTML structure.
Shows: landmark sections (id/data-testid), specs table structure, and description location.

Usage:
    python tools/inspect_product_page.py <coolblue_product_url>

Example:
    python tools/inspect_product_page.py https://www.coolblue.nl/product/959897/jbl-tour-one-m3-goud.html
"""

import sys
import time
import requests
from bs4 import BeautifulSoup

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


def fetch(url: str) -> str:
    session = requests.Session()
    session.headers.update(HEADERS)
    # Warmup to set cookies
    session.get("https://www.coolblue.nl/", timeout=(5, 20))
    time.sleep(1)
    resp = session.get(url, timeout=(5, 20))
    resp.raise_for_status()
    print(f"Fetched {url} — status {resp.status_code}, {len(resp.content):,} bytes\n")
    return resp.text


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


def inspect(html: str) -> None:
    soup = BeautifulSoup(html, "html.parser")

    # ── 1. Landmark sections ──────────────────────────────────────
    section("LANDMARK ELEMENTS (id attributes)")
    for el in soup.find_all(id=True):
        eid = el.get("id", "")
        if eid.startswith(("S:", "B:", "_R_", "svg-", "idealW")):
            continue  # skip React internals and SVG sprites
        text = el.get_text(strip=True)[:80].replace("\n", " ")
        print(f"  <{el.name} id={eid!r}>  {text!r}")

    # ── 2. Page headings ─────────────────────────────────────────
    section("HEADINGS (h2 / h3 / h4)")
    for tag in ["h2", "h3", "h4"]:
        for h in soup.find_all(tag):
            print(f"  {tag}: {h.get_text(strip=True)!r}")

    # ── 3. Description section ───────────────────────────────────
    section("DESCRIPTION  (section#product-information → h3 'Omschrijving')")
    pi = soup.find("section", id="product-information")
    if pi:
        for h3 in pi.find_all("h3"):
            if "Omschrijving" in h3.get_text():
                container = h3.parent
                collapse = container.find(
                    "div", id=lambda x: x and x.startswith("collapse-content-")
                )
                if collapse:
                    print("  Found — text preview:")
                    print(" ", repr(collapse.get_text(separator=" ", strip=True)[:300]))
                else:
                    print("  h3 'Omschrijving' found but no collapse-content div inside")
                break
        else:
            print("  No h3 'Omschrijving' found inside section#product-information")
    else:
        print("  section#product-information not found")

    # ── 4. Specs table ───────────────────────────────────────────
    section("SPECS TABLE  (section#product-specifications)")
    ps = soup.find("section", id="product-specifications")
    if ps:
        for style in ps.find_all("style"):
            style.decompose()
        rows = []
        for tr in ps.find_all("tr"):
            th = tr.find("th")
            tds = tr.find_all("td")
            if not th or len(tds) < 2:
                continue
            label = th.get_text(strip=True)
            value_td = tds[-1]
            svg = value_td.find("svg")
            if svg and svg.get("aria-label"):
                value = svg["aria-label"]
                vtype = "bool"
            else:
                value = value_td.get_text(strip=True)
                vtype = "text"
            rows.append((label, value, vtype))

        max_label = max((len(r[0]) for r in rows), default=10)
        for label, value, vtype in rows:
            print(f"  {label:<{max_label}}  →  {value!r:30}  ({vtype})")
    else:
        print("  section#product-specifications not found")

    # ── 5. Short specs ───────────────────────────────────────────
    section("SHORT SPECS  (section#product-information → h3 'Korte specificaties')")
    if pi:
        for h3 in pi.find_all("h3"):
            if "Korte specificaties" in h3.get_text():
                container = h3.parent
                for style in container.find_all("style"):
                    style.decompose()
                print("  Found — content:")
                print(" ", repr(container.get_text(separator=" | ", strip=True)[:500]))
                break
        else:
            print("  No h3 'Korte specificaties' found")
    else:
        print("  section#product-information not found")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    html = fetch(url)
    inspect(html)
