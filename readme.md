# Coolblue Headphones Price Tracker

This project is a data collection and analysis tool for tracking price and availability of headphones listed on [Coolblue](https://www.coolblue.nl/). It includes automated web scraping, historical price tracking, and utilities for analyzing product trends.

## Features

- **Automated scraping** of product price, name, brand, SKU, and stock status from Coolblue.
- **Historical price tracking:** Prices and product data are appended to a CSV file with timestamps for longitudinal analysis.
- **Product discovery:** Scripted collection of product URLs for all headphones on Coolblue.
- **Structured data extraction:** Uses BeautifulSoup to parse JSON-LD enriched data for robust product info retrieval.
- **Modular code**: Source modules for scraping/processing/data handling and utility scripts.

---

## Project Structure

- `src/` - Core scraping modules and helper functions (e.g., `coolblue_product_scraping.py`)
- `data/` - Collected datasets, including `products.json` (list of discovered headphone URLs) and `price_history.csv` (historical prices and info)
- `notebooks/` - Jupyter notebooks for exploratory analysis, plotting, and reporting
- `scripts/` - CLI/automation scripts (e.g., `discover_products.py`, `scrape_price_history.py`) for running scraping jobs and building the datasets

---

## Installation & Setup

1. **Create a virtual environment** (recommended):
    ```bash
    python -m venv .venv
    ```

2. **Activate the virtual environment**
    - Windows:
        ```bash
        .venv\Scripts\activate
        ```
    - macOS/Linux:
        ```bash
        source .venv/bin/activate
        ```

3. **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
    *Note: If `requirements.txt` is missing, minimally install `beautifulsoup4`, `requests`, and `pandas` to get started.*

---

## Quickstart

1. **Find all headphones** (populate products.json):

    ```bash
    python scripts/discover_products.py
    # Output: data/products.json with URLs of all headphones
    ```

2. **Scrape current prices and build price history:**

    ```bash
    python scripts/scrape_price_history.py
    # Output: data/price_history.csv (appends today's prices for all discovered products)
    ```


---

## Data Formats

- **`data/products.json`**: List of Coolblue product URLs (headphones only)
- **`data/price_history.csv`**: Table with columns:
    - `timestamp`, `sku`, `name`, `brand`, `price_cents`, `in_stock`, `url`

Example row:
```
2026-01-09,954349,Apple AirPods Max Goud,Apple,56100,True,https://www.coolblue.nl/product/954349/apple-airpods-max-goud.html
```

---

## Test: Handling Nonexistent Product

To test robustness to missing or non-existent product URLs, manually add the following fake product object to the start of your `data/products.json`, immediately after the opening `[`:

```json
{
  "product_id": 999999999,
  "name": "Does Not Exist",
  "url": "https://www.coolblue.nl/product/999999999/does-not-exist.html",
  "active": true
},
```

Now run:

```bash
python scripts/scrape_price_history.py
```

Expected outcome:  
The script should continue running and for this fake product, it should append a row to `data/price_history.csv` with `status` set to `not_found` (see the top of `price_history.csv` for a row like this:  
`...,999999999,Does Not Exist,,,,https://www.coolblue.nl/product/999999999/does-not-exist.html,not_found`)

---


## Reset whole database
To clear all tables in the database and reset indices the whole database, run the following SQL command (use with caution):

```sql
TRUNCATE TABLE
    price_history,
    products,
    retailers
RESTART IDENTITY
CASCADE;
```

## Current Status

- Scraper functions are operational for:
    - Extracting all headphone product URLs (see `discover_products.py`)
    - Parsing product info and historical prices (see `scrape_price_history.py`)
    - Saving and appending to `data/price_history.csv`
- Data for headphones collected in first run .

---

## Next Steps / Roadmap
- Add retry logic outside of run: what if certain product is not loaded correctly, try again in case of certain errors (http_error, parse_error(?))
- Add retry logic within run
- Alternatives for windows task scheduler
- implement better logging for tasks
- [ ] Improve robustness of scraper to handle captchas/blocks, edge cases (if needed)
- [ ] Add retry logic and proxy support (if needed)
- [ ] Expand data model with more product fields (e.g., ratings, reviews) (optional)
- [ ] Database integration for scalable historical storage 
- [ ] Publish analysis notebooks and interactive dashboards
- [ ] Schedule scraping runs (e.g., with cron/job scheduler)
- [ ] Add unit tests for scraping and parsing logic

---
