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
python scripts/discover_products.py            # defaults to headphones
python scripts/discover_products.py earbuds
python scripts/discover_products.py speakers
python scripts/discover_products.py soundbars
python scripts/scrape_price_history.py
python scripts/send_alerts.py
```

Both `discover_products.py` and `scrape_price_history.py` accept `--limit N` to process only the first N products — useful during development to test logic without running the full pipeline. Never pass `--limit` in Railway cron jobs.

### Running a script manually against production

Railway cron jobs run automatically, but occasionally you need to trigger a script once (e.g. to seed a new category).

**Do not use `railway run`** — it injects the internal database hostname (`postgres.railway.internal`), which is unreachable from your local machine.

Instead, connect directly using the public database URL:

1. Open the [Railway dashboard](https://railway.app) → your project → Postgres service → **Variables** tab
2. Copy the value of `DATABASE_PUBLIC_URL` (hostname looks like `roundhouse.proxy.rlwy.net`)
3. Set it locally and run the script:

**PowerShell:**
```powershell
$env:DATABASE_URL="postgresql://postgres:<password>@<public-host>:<port>/railway"
python scripts/discover_products.py earbuds
```

**bash:**
```bash
DATABASE_URL="postgresql://postgres:<password>@<public-host>:<port>/railway" python scripts/discover_products.py earbuds
```

The script reads `DATABASE_URL` and connects over the public hostname. No Railway CLI needed.

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
