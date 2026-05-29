# Product Scraper — Backend Pipeline Spec

**Started:** 2026-04-26
**Completed:** 2026-05-29

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
| Scrape run time scales with product count | Current pacing (2–4s/product + batch pauses) gives ~60–80 min for 800 products — acceptable for a daily job; revisit if categories expand significantly or run time approaches 3–4 hours |
| Bundle product pages expose specs for multiple products in one `section#product-specifications` | Bundle pages do not appear on category filter pages used by discovery, so this is low risk currently. If a bundle URL were scraped, `extract_product_specs` would silently mix specs from both products (last Dutch label occurrence wins). Fix if needed: scope parsing to the first `div[id^='tabs-panel-']` rather than the whole section. |
| **Known issue:** ~4.4% of headphone products have `description = NULL` permanently | These are discontinued products ("nooit meer leverbaar") — still return HTTP 200 so deactivation logic never fired, but Coolblue removes them from category filter pages so `discover_products.py` never re-upserts them. Null description is cosmetically harmless (these products are out of stock and excluded from deal pages). Fixed in T25 ✅: OOS deactivation after 30 consecutive days now catches these products; T25b verifies no active products remain above the threshold. |
| **Known issue:** deactivation logic does not catch permanently discontinued products | Fixed in T25 ✅: deactivation now also triggers after 30 consecutive OOS days (streak since last `availability = true`), catching "nooit meer leverbaar" products that return HTTP 200 indefinitely. T25b: verify no active products remain above threshold in production. |

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
| ✅ | T11 | Multi-category discovery: headphones (validate new schema end-to-end); wire slug generation into `upsert_product()` so every new product gets a slug on insert; re-run backfill after to catch any products added during weekly discovery runs; update zero-product warning in `discover_products.py` to be category-aware (current warning is a false positive if a category genuinely has no products) | 6a |
| ✅ | T11b | Enforce `category` as required in `validate_product_details`; thread discovery URL category as fallback into `details` in `discover_products.py` so breadcrumb-failure products (e.g. Sony brand-path pages) are still inserted with a valid category rather than skipped | 6a |
| ✅ | T12 | Multi-category discovery: earbuds | 6b |
| ✅ | T13 | Multi-category discovery: speakers | 6c |
| ✅ | T14 | Multi-category discovery: soundbars | 6d |
| ✅ | T15 | Parser: description + specs for headphones | 7 |
| ✅ | T16 | Parser: description + specs for earbuds | 7 |
| ✅ | T17 | Parser: description + specs for speakers | 7 |
| ✅ | T18 | Parser: description + specs for soundbars | 7 |
| ✅ | T19 | Verify deal detection query across all four categories | 8 |
| ✅ | T19b | Enforce €25 minimum drop in `deal_candidates` view: add `AND (m.max_price_30d - cp.current_price) >= 25` to the WHERE clause | 8 |
| ✅ | T20 | Update Railway cron jobs; retire `retry_scrape_price_history.py` and replace hourly retry cron with a second daily run of `scrape_price_history.py` (e.g. 07:00 + 19:00); add `--all` mode to `discover_products.py` to run discovery for all categories in a single invocation and update Railway cron to use one job instead of four; optionally add single within-script retry for transient failures; remove `get_due_retry_run` and `clear_next_retry` from `src/db.py`. **Note:** once cron is updated for all categories, update the website copy to reflect that all audio categories are tracked — not just headphones (frontend task, outside current project scope). Get briefing and prompt for that project | 9 |
| ✅ | T20c | Add count integrity check to `sql/db_healthchecks.sql`: query `scrape_runs` to verify `total_products = success_count + failed_count + blocked_count` and flag any rows where they don't match | 9 |
| ✅ | T20b | Stop crawling category pages early when `--limit N` is set: pass the limit into `get_all_coolblue_products` so it stops after fetching `ceil(N / products_per_page)` pages instead of crawling all pages first | 9 |
| ✅ | T21 | Update README and add-a-category guide | 10 |
| ✅ | T22 | Document scraping safety + source terms risk | 10 |
| ✅ | T23 | Edge-case parser tests + optional integration tests; investigate ~10% of products with null description/specs after production discovery pass (likely non-standard page structure or inactive products) | 11 |
| ✅ | T23b | After next Railway discovery run: re-run Query 1 and confirm headphone null description rate dropped. **Finding:** residual ~4.4% nulls are exclusively discontinued ("nooit meer leverbaar") products — removed from Coolblue filter pages so never re-discovered; null description is harmless as these products are out of stock. Deactivation gap logged as T25. | 11 |
| ✅ | T24 | Cleanup of repo | 11 |
| ✅ | T25 | Revisit deactivation logic: currently only triggers on 3× HTTP 404, but Coolblue "nooit meer leverbaar" products return HTTP 200 indefinitely and never get deactivated. **Implemented option (b):** deactivate after 30 consecutive OOS days using a streak from last in-stock date (robust to scraping gaps). **Verified:** Railway log showed `🚫 OOS deactivated` lines confirming deactivation fired. | 11 |
| ⬜ | T25b | Run deactivation health check in `sql/db_analytical_checks.sql` and confirm no active products have `consecutive_oos_days >= 30` (status `⚠ should be deactivated`). | 11 |
| ✅ | T26 | Check spec document and clean it | 11 |

---

## 9. Acceptance Checklist (Definition of Done)

- [x] All 4 categories scraping cleanly without errors *(T12–T14)*
- [x] Every product has a controlled `category` value (no raw Coolblue text) *(T3, T5, T11b)*
- [x] Every product has a unique `slug`, `description`, and `retailer` value *(T4, T5, T15–T18)*
- [x] Minimal structured specs stored per product *(T15–T18)*
- [x] Deal detection applies the €100 / €25 rules correctly across all categories *(T19, T19b)*
- [x] No regressions in existing headphone data or pipeline *(T11)*
- [x] Railway cron jobs updated and running for all categories *(T20)*
- [x] Data quality validation runs before every DB write; invalid records logged and skipped *(T9, T10)*
- [x] Failed scrapes logged clearly; full run does not abort on single failure *(T10)*
- [x] Running scrape/discovery twice on the same day produces no duplicates *(T6, T11)*
- [x] Every run logged in `scrape_runs` with summary counts and status *(T7, T8)*
- [x] Each run prints a structured observability summary to stdout *(T8)*
- [x] Queries for category deals and product price history are fast (indexes in place) *(T1)*
- [x] Schema migration has a tested rollback path *(T2)*
- [x] Scripts use rate limiting, timeouts, and user-agent headers *(T11–T18)*
- [x] Scraping logic is isolated from business logic (source abstraction) *(T3, T9, T15–T18)*
- [x] Existing headphone products backfilled with valid category, slug, and required fields *(T5)*
- [x] README documents category model, required fields, scripts, cron schedule, and how to add a category *(T21)*
- [x] Source terms and scraping risk documented *(T22)*
- [x] Unit tests pass for: normalization, slug generation, deal detection, idempotency *(T6)*
