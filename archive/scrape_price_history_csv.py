"""
Script to scrape product information and append to price history CSV.
This script can be run daily to track price changes over time.
Automatically skips products that have already been scraped today.

Usage:
    python scripts/scrape_price_history.py [products.json]

Example:
    python scripts/scrape_price_history.py
"""

import sys
import json
import csv
from pathlib import Path
from datetime import datetime
import requests
from datetime import datetime

# Create logs directory if it doesn't exist
log_dir = Path(__file__).parent.parent / "logs"
log_dir.mkdir(exist_ok=True)

# Use current datetime in log file name
log_time_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = log_dir / f"task_scheduler_{log_time_str}.log"

# Add current datetime to the log itself as well
with open(log_file, "a", encoding="utf-8") as lf:
    lf.write(f"\n---\nScript started at {datetime.now().isoformat(sep=' ', timespec='seconds')}\n")

sys.stdout = open(log_file, "a", encoding="utf-8")
sys.stderr = sys.stdout

# Add parent directory to path to import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

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

def get_scraped_ids(csv_file, current_date):
    """
    Return set of product_ids (as strings) for which a record for current_date already exists in CSV.
    """
    scraped_ids = set()
    if not csv_file.exists():
        return scraped_ids
    try:
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("date", "").strip() == current_date:
                    pid = row.get("product_id", "").strip()
                    if pid:
                        scraped_ids.add(pid)
    except Exception as e:
        print(f"Warning: Could not read existing CSV: {e}")
    return scraped_ids


def get_error_status_and_message(exception):
    """
    Determine status and error message based on exception type.
    Returns (status, error_message) tuple.
    """
    if isinstance(exception, requests.exceptions.HTTPError):
        if exception.response.status_code == 404:
            return "not_found", f"HTTP {exception.response.status_code}: {exception}"
        else:
            return "http_error", f"HTTP {exception.response.status_code}: {exception}"
    elif isinstance(exception, requests.exceptions.Timeout):
        return "timeout", f"Timeout: {exception}"
    elif isinstance(exception, requests.exceptions.RequestException):
        return "timeout", f"Network error: {exception}"
    elif isinstance(exception, ValueError):
        return "blocked", f"Blocked: {exception}"
    else:
        return "parse_error", f"Unknown error: {exception}"


def write_error_row(writer, product, status, error_msg):
    """
    Write an error row to the CSV for given product.
    product_id is the only identifier.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    scraped_at = datetime.now().isoformat(timespec="seconds")
    row = {
        "date": today,
        "scraped_at": scraped_at,
        "product_id": product.get("product_id", ""),
        "name": product.get("name", ""),
        "brand": "",
        "price_cents": "",
        "in_stock": "",
        "url": product.get("url", ""),
        "status": status
    }
    writer.writerow(row)
    print(f"  [{product.get('product_id', '')}] {product.get('name', '')}: {error_msg}")


def main():
    # Determine path for products.json
    if len(sys.argv) > 1:
        products_file = Path(sys.argv[1])
    else:
        products_file = Path(__file__).parent.parent / "data" / "products.json"

    if not products_file.exists():
        print(f"Error: Products file not found: {products_file}")
        print("Please run discover_products.py first to generate products.json")
        sys.exit(1)

    # Load products list
    print(f"Loading products from: {products_file}")
    with open(products_file, "r", encoding="utf-8") as f:
        products = json.load(f)

    # Select only active products with required keys
    products = [
        p for p in products
        if p.get("active", True) and p.get("url") and p.get("product_id") is not None
    ]
    print(f"Found {len(products)} active products to consider.")

    # Prepare output directory and paths
    data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    csv_file = data_dir / "price_history.csv"
    today = datetime.now().strftime("%Y-%m-%d")

    # Find already scraped product_ids (as string) for today
    already_scraped_ids = get_scraped_ids(csv_file, today)
    if already_scraped_ids:
        print(f"{len(already_scraped_ids)} products already scraped today, skipping those.")
    else:
        print("No existing data found for today. Starting fresh.")

    # Only scrape products that have not been scraped today
    products_to_scrape = [
        p for p in products if str(p["product_id"]) not in already_scraped_ids
    ]

    if not products_to_scrape:
        print("All products have already been scraped today!")
        return

    print(f"Scraping {len(products_to_scrape)} remaining products...")

    file_exists = csv_file.exists()
    successful = 0
    failed = 0

    # CSV fieldnames: note there is no 'sku' field anymore
    fieldnames = [
        "date",
        "scraped_at",
        "product_id",
        "name",
        "brand",
        "price_cents",
        "in_stock",
        "url",
        "status"
    ]

    with open(csv_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
            f.flush()

        for i, product in enumerate(products_to_scrape, 1):
            url = product["url"]
            pid = product["product_id"]
            pname = product.get("name", "")
            try:
                print(f"[{i}/{len(products_to_scrape)}] Scraping [{pid}] {pname}")
                product_info = scrape_coolblue_product_info(url)

                # Defensive: If parsing failed, output error for this product_id
                if not product_info:
                    write_error_row(writer, product, "parse_error", "Parse error: Could not extract product data from page")
                    f.flush()
                    failed += 1
                    continue

                # Get product_id from product argument; this is the identifier
                scraped_id = str(product.get("product_id", ""))

                # Double-check: don't write duplicate record for (date, product_id)
                if scraped_id in already_scraped_ids:
                    print(f"  [{pid}] Already scraped today, skipping (duplicate check).")
                    continue

                row_date = today
                row_scraped_at = datetime.now().isoformat(timespec="seconds")
                row = {
                    "date": row_date,
                    "scraped_at": row_scraped_at,
                    "product_id": scraped_id,
                    "name": product_info.get("name", ""),
                    "brand": product_info.get("brand", ""),
                    "price_cents": product_info.get("price_cents", ""),
                    "in_stock": product_info.get("in_stock", ""),
                    "url": product_info.get("url", url),
                    "status": "ok"
                }
                writer.writerow(row)
                f.flush()
                successful += 1
                already_scraped_ids.add(scraped_id)
            except KeyboardInterrupt:
                print("\n\nInterrupted by user.")
                print("Progress saved. Run the script again to continue from where it stopped.")
                sys.exit(0)
            except Exception as e:
                status, error_msg = get_error_status_and_message(e)
                write_error_row(writer, product, status, error_msg)
                f.flush()
                failed += 1

    print(f"\nScraping complete!")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")
    print(f"  Results appended to: {csv_file}")


if __name__ == "__main__":
    main()
