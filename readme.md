# Coolblue Headphones Price Tracker

Automated price tracking pipeline for headphones on [Coolblue](https://www.coolblue.nl/). Discovers products weekly, scrapes prices daily, detects drops, and sends Telegram alerts.

## How it works

```
discover_products  (weekly)
    → crawl category pages → scrape product detail pages → upsert to products table

scrape_price_history  (daily)
    → scrape price + availability per product → upsert to price_history
    → detect_drops runs inline
    → send_alerts sends qualifying drops via Telegram
```

## Scripts

| Script | Schedule | What it does |
|---|---|---|
| `scripts/discover_products.py` | Weekly | Crawls Coolblue category pages, enriches each product with detail page metadata, upserts to `products` |
| `scripts/scrape_price_history.py` | Daily | Scrapes price + availability for all active products, upserts to `price_history`, runs drop detection inline |
| `scripts/detect_drops.py` | Inline (daily run) | Compares today vs. previous price, inserts qualifying drops to `price_drops` |
| `scripts/send_alerts.py` | After daily run | Sends unsent drops (≥5% drop, ≥€150) as Telegram messages |

## Database schema

| Table | Purpose |
|---|---|
| `retailers` | Retailer registry (currently only Coolblue) |
| `products` | Product catalogue — name, brand, category, specs, URLs |
| `price_history` | Daily price, availability, rating, review count per product |
| `price_drops` | Detected price drops with old/new price and drop % |
| `scrape_runs` | Audit log for every script run (status, counts, errors, retry schedule) |

Schema source of truth: [`sql/schema.sql`](sql/schema.sql)

## Setup

### Local

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Create `.env.local`:

```
DB_HOST=localhost
DB_PORT=5432
DB_NAME=pricetracker
DB_USER=postgres
DB_PASSWORD=your_password
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Railway (production)

Set `DATABASE_URL` — this takes precedence over all `DB_*` vars. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as env vars.

## Running scripts

```bash
python scripts/discover_products.py
python scripts/scrape_price_history.py
python scripts/send_alerts.py
```

## Project structure

```
src/
  config.py                        # env/db config
  db.py                            # all DB reads/writes
  coolblue_discovery.py            # category page crawler
  coolblue_product_scraping.py     # product + price page scraper
  utils.py                         # helpers + validation

scripts/
  discover_products.py
  scrape_price_history.py
  detect_drops.py
  send_alerts.py
  retry_scrape_price_history.py
  check_category_coverage.py
  backfill_category_slug.py

sql/
  schema.sql                       # authoritative DDL
  views/                           # deal page and homepage views
  migrate_001_products_columns.sql
  db_healthchecks.sql
  db_analytical_checks.sql
```

## Useful SQL

Reset all tables (caution — destructive):

```sql
TRUNCATE TABLE price_history, products, retailers RESTART IDENTITY CASCADE;
```

Seed retailer:

```sql
INSERT INTO retailers (name, base_url) VALUES ('Coolblue', 'https://coolblue.nl');
```
