# Product Scraper — Backend Pipeline Spec

## 1. Product Brief

Extend the existing Coolblue headphone price-tracking pipeline to support four audio product categories (headphones, earbuds, speakers, soundbars), improve data quality and structure, and produce clean, queryable data that powers SEO-driven deal pages. The pipeline must be reliable, observable, idempotent, and structured so a future switch to an official product feed does not require rewriting business logic.

---

## 2. Functional Requirements

### Categories
- Support exactly four categories: `headphones`, `earbuds`, `speakers`, `soundbars`
- Each product must have a single, controlled `category` value (no raw Coolblue text)
- Existing headphone products must be backfilled with a valid category value

### Product Data
- Required fields per product: `name`, `category`, `slug`, `current_price`, `image_url`, `product_url`, `retailer`, `in_stock`, `description`
- Minimal structured specs per category stored as a JSON or normalized field (scraped from Coolblue product page specs table)
- Slug generated from product name, unique per product

### Price History
- Daily price + availability records per product
- Running the same scrape twice on the same day must not create duplicate records (idempotent upsert)

### Deal Detection
- A product is a deal if: current price is > €100 AND current price is > €25 below the 30-day price high
- Rules apply identically across all four categories
- No changes to deal detection logic unless multi-category support requires it

### Discovery
- Weekly discovery run per category to find new product URLs
- Daily price scrape for all active products across all categories
- Categories added one at a time: headphones first (validation), then earbuds, then speakers, then soundbars

### Data Quality Validation
- Before any DB write, validate: price (numeric, > 0), availability (boolean), category (controlled value), image URL (non-empty, valid format), product URL (non-empty), all required fields present
- Invalid records are skipped and logged — they do not break the full run

### Failure Handling
- Scrape failures are caught per product, logged with reason, and do not halt the full run
- Failed products can be retried by re-running the script
- Scripts use rate limiting, timeouts, and a user-agent header

### Observability
- Each run outputs a structured summary: products discovered, products scraped, prices inserted, records skipped, failures, run duration
- Every run is logged to a `run_log` table: run type, start time, end time, summary counts, status (success/partial/failed)

### Idempotency
- Running discovery twice on the same day does not create duplicate product records
- Running the price scrape twice on the same day does not create duplicate price history records

---

## 3. Non-Functional Requirements

- **Performance**: category deal queries and product price history queries must be fast enough for frontend use; indexes added where needed
- **Reliability**: no single product failure breaks the full run
- **Scraping safety**: rate limits, timeouts, user-agent identification; do not overload Coolblue
- **Safe deploy**: migrations are applied safely; a rollback plan or backup step is documented
- **Documentation**: updated README explains the category model, required fields, scripts, cron schedule, and how to add a new category
- **Source terms**: scraping/data usage assumptions documented, including risks and future plan to move to official feeds

---

## 4. Technical Constraints

- Language: Python 3
- Scraping: requests + BeautifulSoup (no framework migration)
- Database: PostgreSQL on Railway
- Scheduler: Railway cron jobs (not updated until new schema is manually verified)
- ORM: raw psycopg2 (no ORM added)
- Deploy: Railway is linked to the `main` branch on GitHub — pushing to `main` automatically redeploys the Python cron scripts (e.g. `discover_products.py`, `scrape_price_history.py`). There is no migration runner; schema migrations are plain SQL files that must be applied manually to the Railway PostgreSQL DB. See `CLAUDE.md` for deploy and migration rules.
- Frontend: Next.js on Vercel — do not touch in this phase
- API layer: not added in this phase
- Retailer: Coolblue only in this phase; `retailer` column added to support future expansion without rewrite

---

## 5. Architecture Notes

### Source Abstraction
- Scraping logic (Coolblue HTML parsing) must be separated from business logic (deal detection, data validation, DB writes)
- Business logic must work regardless of data source so a future official product feed can replace scraping without touching deal detection

### Category Model
- `category` is a controlled enum: `headphones | earbuds | speakers | soundbars`
- Never store raw Coolblue category text as the canonical value
- Normalization function maps raw Coolblue category strings → controlled values

### Schema Changes
- Add to `products` table: `category` (controlled), `slug`, `description`, `specs` (JSONB), `retailer`
- `scrape_runs` table already exists and serves as the run log — no separate `run_log` table needed
- Add indexes: `products(category)`, `products(slug)`, `price_history(product_id, scraped_at)`

### Slug Generation
- Derived from product name: lowercased, hyphenated, unique
- Backfilled for all existing products

---

## 6. Implementation Phases (Slices)

### Phase 1 — Schema Migration
- Add `category`, `slug`, `description`, `specs`, `retailer` columns to `products`
- `scrape_runs` already exists — no new run log table needed
- Add indexes
- Write rollback SQL

### Phase 2 — Category Normalization + Backfill
- Define controlled category enum
- Write normalization function (raw Coolblue text → controlled value)
- Write slug generation function
- Backfill all existing headphone products with `category = 'headphones'` and valid slugs

### Phase 3 — Basic Tests
- Unit tests: category normalization, slug generation, deal detection rules, idempotency (upsert logic)

### Phase 4 — Observability
- Verify `scrape_runs` writes are wired into all scripts (start/end of each run)
- Add structured summary output to all scripts (discovered, scraped, inserted, skipped, failed, duration)

### Phase 5 — Data Quality Validation
- Implement validation function for required fields before DB write
- Invalid records logged and skipped, not written

### Phase 6 — Multi-Category Discovery (one at a time)
- Phase 6a: headphones — validate full flow with new schema
- Phase 6b: earbuds — add discovery + scrape, verify
- Phase 6c: speakers — add, verify
- Phase 6d: soundbars — add, verify

### Phase 7 — Parser Improvements (one category at a time)
- Scrape `description` from product pages
- Scrape minimal structured `specs` per category from Coolblue specs table
- Same order: headphones → earbuds → speakers → soundbars

### Phase 8 — Deal Detection Across Categories
- Verify deal detection query works correctly across all four categories
- Confirm €100 minimum and €25 drop threshold applied per product regardless of category

### Phase 9 — Cron/Railway Update
- Update Railway cron jobs to run discovery and scrape for all categories
- Only after manual verification of full pipeline

### Phase 10 — Documentation
- Update README: category model, required fields, scripts, cron schedule, how to add a new category
- Document scraping safety assumptions and source terms risk

### Phase 11 — Additional Tests
- Edge-case tests for parsers (missing fields, malformed HTML)
- Integration-style tests for full upsert flow against a test DB (if time allows)

---

## 7. Risks & Ambiguities

| Risk | Mitigation |
|---|---|
| Schema migration breaks existing headphone pipeline | Test migration on a DB snapshot first; write rollback SQL before applying |
| Coolblue HTML structure differs per category | Inspect each category page before writing parsers; treat headphones as baseline |
| Raw category text from Coolblue is inconsistent | Normalization function with explicit mapping + fallback logging for unknown values |
| Some products have no category breadcrumb (e.g. Sony brand-path pages: `Home > Alle merken > Sony > ...`) | Use discovery URL as category fallback during backfill and discovery runs; confirmed affecting ~9/203 headphone products |
| Slug collisions on backfill | Slug generation adds a suffix if collision detected |
| Color variants treated as separate products (separate SKU, slug, price history) | Acceptable for now; if variant grouping is ever needed, requires schema change and slug strategy revision |
| Railway cron updated before new schema is stable | Explicit constraint: do not update cron until manual verification passes |
| Schema too tied to Coolblue | `retailer` column added; scraping logic isolated from business logic |
| Rewriting too much at once | Strict slice-by-slice workflow; no phase spans more than one concern |
| Source terms / scraping legality | Document assumptions now; plan migration to official feed as future work |
| Specs schema varies by category | Use JSONB for specs; document expected keys per category in README |

---

## 8. Task Breakdown

| Status | # | Task | Phase |
|---|---|---|---|
| ✅ | T1 | Write and apply schema migration (products columns + indexes; scrape_runs already exists) | 1 |
| ✅ | T2 | Write rollback SQL for migration | 1 |
| ✅ | T3 | Implement category normalization function + controlled enum | 2 |
| ✅ | T3b | Fix `extract_product_category()` to reliably identify the category breadcrumb item (not brand/product name) | 2 |
| ✅ | T4 | Implement slug generation function | 2 |
| ✅ | T5 | Backfill existing products with category + slug; use discovery URL as category fallback for products with no category breadcrumb (e.g. Sony brand-path products) | 2 |
| ✅ | T6 | Unit tests: normalization, slug, deal detection, idempotency | 3 |
| ✅ | T7 | Wire scrape_runs logging into discover_products.py (scrape_price_history.py and retry_scrape_price_history.py were already wired) | 4 |
| ✅ | T8 | Add structured observability summary to all scripts; include a warning when `discover_products.py` finishes with `total_products=0` (may indicate a blocked/failed discovery run) | 4 |
| ✅ | T9 | Implement data quality validation function | 5 |
| ✅ | T10 | Wire validation into DB write path; log skipped records | 5 |
| ✅ | T10b | Mark products inactive when price scrape returns 3 consecutive 404s; filter inactive products from deal views; log deactivations in run summary | 5 |
| ⬜ | T11 | Multi-category discovery: headphones (validate new schema end-to-end); wire slug generation into `upsert_product()` so every new product gets a slug on insert; re-run backfill after to catch any products added during weekly discovery runs; update zero-product warning in `discover_products.py` to be category-aware (current warning is a false positive if a category genuinely has no products) | 6a |
| ⬜ | T12 | Multi-category discovery: earbuds | 6b |
| ⬜ | T13 | Multi-category discovery: speakers | 6c |
| ⬜ | T14 | Multi-category discovery: soundbars | 6d |
| ⬜ | T15 | Parser: description + specs for headphones | 7 |
| ⬜ | T16 | Parser: description + specs for earbuds | 7 |
| ⬜ | T17 | Parser: description + specs for speakers | 7 |
| ⬜ | T18 | Parser: description + specs for soundbars | 7 |
| ⬜ | T19 | Verify deal detection query across all four categories | 8 |
| ⬜ | T20 | Update Railway cron jobs; retire `retry_scrape_price_history.py` and replace hourly retry cron with a second daily run of `scrape_price_history.py` (e.g. 07:00 + 19:00); optionally add single within-script retry for transient failures; remove `get_due_retry_run` and `clear_next_retry` from `src/db.py` | 9 |
| ⬜ | T21 | Update README and add-a-category guide | 10 |
| ⬜ | T22 | Document scraping safety + source terms risk | 10 |
| ⬜ | T23 | Edge-case parser tests + optional integration tests | 11 |

---

## 9. Acceptance Checklist (Definition of Done)

- [ ] All 4 categories scraping cleanly without errors
- [ ] Every product has a controlled `category` value (no raw Coolblue text)
- [ ] Every product has a unique `slug`, `description`, and `retailer` value
- [ ] Minimal structured specs stored per product
- [ ] Deal detection applies the €100 / €25 rules correctly across all categories
- [ ] No regressions in existing headphone data or pipeline
- [ ] Railway cron jobs updated and running for all categories
- [ ] Data quality validation runs before every DB write; invalid records logged and skipped
- [ ] Failed scrapes logged clearly; full run does not abort on single failure
- [ ] Running scrape/discovery twice on the same day produces no duplicates
- [ ] Every run logged in `scrape_runs` with summary counts and status
- [ ] Each run prints a structured observability summary to stdout
- [x] Queries for category deals and product price history are fast (indexes in place)
- [x] Schema migration has a tested rollback path
- [ ] Scripts use rate limiting, timeouts, and user-agent headers
- [ ] Scraping logic is isolated from business logic (source abstraction)
- [ ] Existing headphone products backfilled with valid category, slug, and required fields
- [ ] README documents category model, required fields, scripts, cron schedule, and how to add a category
- [ ] Source terms and scraping risk documented
- [ ] Unit tests pass for: normalization, slug generation, deal detection, idempotency
