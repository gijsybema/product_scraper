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

1. **Discover all headphones and populate the database:**

    ```bash
    python scripts/discover_products.py
    # Output: Product metadata is discovered and stored directly in the database.
    ```

2. **Scrape current prices and update price history in the database:**

    ```bash
    python scripts/scrape_price_history.py
    # Output: Today's prices and facts for all products are stored in the database price_history table.
    ```


---

## Reset whole database
To clear all tables in the database and reset indices the whole database, run the following SQL command (use with caution):

```sql
TRUNCATE TABLE
    price_history,
    products
RESTART IDENTITY
CASCADE;
```

## Current Status

- Scraper functions are operational for:
    - Collecting brand, product name, URL, ratings, review counts, price, and availability from Coolblue product pages
    - Upserting product name, brand, URL into the PostgreSQL `products` table per weekly run (see `discover_products.py`)
    - Upserting price and availability data into the PostgreSQL `price_history` table for each daily run (see `scrape_price_history.py`)
    - Uses modular code structure: database, scraping, and utility functions split out in `src/`
    - Designed to run as a scheduled task (e.g. via cron or Task Scheduler)

- Data for headphones collected in first run and stored in both the database and local CSV
- Scripts validated on multiple products (>10 SKUs), with stable operation
- Easy extension to other product categories possible by modifying `discover_products.py`
- Installation and quickstart instructions included for reproducibility


---

## Next Steps / Roadmap
- Add retry logic outside of run: what if certain product is not loaded correctly, try again in case of certain errors (http_error, parse_error(?))
- Add retry logic within run
- Progress reporting and error capture for each product scrape in both scripts
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
