# Coolblue Audio Price Tracker

Automated price tracking pipeline for audio products on [Coolblue](https://www.coolblue.nl/). Tracks headphones, earbuds, speakers, and soundbars. Discovers products weekly, scrapes prices daily, detects drops, and sends Telegram alerts.

## How it works

```
discover_products  (weekly)
    → crawl category pages → scrape product detail pages → upsert to products table

scrape_price_history  (daily × 2)
    → scrape price + availability per product → upsert to price_history
    → detect_drops runs inline
    → send_alerts sends qualifying drops via Telegram

scrape_price_history --missed-only  (daily recovery run)
    → scrapes only products with no price_history row for today
```

## Scripts

| Script | Schedule | What it does |
|---|---|---|
| `scripts/discover_products.py` | Weekly | Crawls Coolblue category pages, enriches each product with detail page metadata, upserts to `products`. Use `--all` to run all categories in one invocation. |
| `scripts/scrape_price_history.py` | Daily (×2) | Scrapes price + availability for all active products, upserts to `price_history`, runs drop detection inline. Use `--missed-only` for the recovery run. |
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

## Local development database

To develop against a realistic dataset, pull a subset of prod data into your local DB:

```bash
bash scripts/refresh_local_db.sh
```

This will:
1. Apply `sql/schema.sql` + all migrations to the local DB (idempotent)
2. Truncate all local tables
3. Stream from prod (read-only): all retailers + products, last 90 days of price_history/price_drops, last 30 days of scrape_runs

**Prerequisites:**
- PostgreSQL client tools installed (`psql` on PATH) — download from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/), install "Command Line Tools" only
- `PROD_READONLY_URL` set in `.env.local` (Railway read-only connection string)
- Local DB vars set in `.env.local`: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`

**Verification queries** (run in pgAdmin before/after):
- Local DB: [`sql/checks/refresh_before_after.sql`](sql/checks/refresh_before_after.sql)
- Prod DB (confirm nothing changed): [`sql/checks/refresh_prod_unchanged.sql`](sql/checks/refresh_prod_unchanged.sql)

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
DB_NAME=price_tracker
DB_USER=postgres
DB_PASSWORD='your_password'
PROD_READONLY_URL=postgresql://scraper_readonly:your_password@your-railway-host:port/railway
DATABASE_PUBLIC_URL=postgresql://postgres:your_password@your-railway-host:port/railway
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

### Railway (production)

Set `DATABASE_URL` — this takes precedence over all `DB_*` vars. Add `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` as env vars.

## Running scripts

```bash
# Discovery
python scripts/discover_products.py --all          # all categories (production)
python scripts/discover_products.py headphones     # single category

# Price scraping
python scripts/scrape_price_history.py             # full daily run
python scripts/scrape_price_history.py --missed-only  # recovery: missed products only

# Alerts
python scripts/send_alerts.py
```

Both `discover_products.py` and `scrape_price_history.py` accept `--limit N` to process only the first N products — useful during development to test logic without running the full pipeline. Never pass `--limit` in Railway cron jobs.

### Running a script manually against production

Railway cron jobs run automatically, but occasionally you need to trigger a script once (e.g. to seed a new category).

**Do not use `railway run`** — it injects the internal database hostname (`postgres.railway.internal`), which is unreachable from your local machine.

Instead, connect directly using the public database URL.

**One-time setup** — add this to `.env.local` (find the value in Railway dashboard → Postgres service → Variables tab):

```
DATABASE_PUBLIC_URL=postgresql://postgres:<password>@<public-host>:<port>/railway
```

**PowerShell:**
```powershell
$env:DATABASE_URL = (Get-Content .env.local | Select-String "^DATABASE_PUBLIC_URL=").ToString().Split("=",2)[1]
python scripts/discover_products.py --all
```

**bash:**
```bash
export DATABASE_URL=$(grep ^DATABASE_PUBLIC_URL= .env.local | cut -d= -f2-)
python scripts/discover_products.py --all
```

The script reads `DATABASE_URL` and connects over the public hostname. No Railway CLI needed.

## Adding a new category

1. **Verify the Coolblue category URL** — do not assume it follows the same pattern as existing ones. Open the category filter page in a browser and copy the exact URL (e.g. `https://www.coolblue.nl/draadloze-speakers/filter`).

2. **Inspect a product page** to map spec keys:
   ```bash
   python tools/inspect_product_page.py <product-url>
   ```
   This prints all spec labels and values. Pick the ones worth storing.

3. **Add the category URL** to `CATEGORY_URLS` in `scripts/discover_products.py`:
   ```python
   "my-category": "https://www.coolblue.nl/<slug>/filter",
   ```

4. **Add a `_SPEC_KEYS` entry** in `src/coolblue_product_scraping.py` mapping Dutch spec labels to English storage keys. Follow the existing pattern for headphones/earbuds/speakers/soundbars.

5. **Run discovery locally with `--limit`** to verify parsing and DB writes:
   ```bash
   python scripts/discover_products.py my-category --limit 5
   ```

6. **Railway cron** — if using `--all` (current setup), no cron change is needed. The new category is picked up automatically.

## Scraping safety & legal risk

### Safety measures in place

- **Request pacing** — 2.5–5s randomised sleep between category page requests; product detail pages are fetched sequentially with the same jitter
- **Timeouts** — 5s connect / 20s read on all requests; prevents a hung connection from stalling a run
- **Retry with backoff** — 429 and 5xx responses trigger exponential backoff retries; the scraper backs off rather than hammering on errors
- **Daily cadence** — scraping runs once (plus one recovery pass) per day, not continuously
- **Page cap** — category crawler stops after 50 pages maximum, preventing runaway pagination

### Source terms risk

The scraper uses a browser-like User-Agent and does not check `robots.txt`. Coolblue's [Terms of Service](https://www.coolblue.nl/c/algemene-voorwaarden.html) were reviewed — no explicit prohibition on scraping was found. Current assumptions:

- Usage is currently personal and non-commercial
- Scraping is low-volume and polite enough not to constitute a denial-of-service risk
- Data is not redistributed or sold

**Intended future use:** affiliate marketing (commercial). Before going commercial, the goal is to migrate to Coolblue's official product feed, which would remove the scraping dependency entirely.

### Future migration path

Business logic (deal detection, DB writes, alerts) is fully decoupled from scraping. If Coolblue provides an official product feed or affiliate API, replacing the scraper requires changing only `src/coolblue_discovery.py` and `src/coolblue_product_scraping.py` — no changes to deal detection, validation, or the DB schema.

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

tools/
  inspect_product_page.py          # recon tool: prints specs/description for a product URL

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
