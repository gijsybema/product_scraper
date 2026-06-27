# Spec: AI Product Description Pipeline

**Status:** Draft — awaiting approval  
**Date:** 2026-06-26  
**Model:** claude-haiku-4-5  

---

## Overview

Two types of AI-generated copy, stored on the `products` table:

| Field | Purpose | Generated when | Regenerated when |
|---|---|---|---|
| `ai_description` | Static product description | First discovery | Never (unless NULL) |
| `ai_deal_description` | Dynamic deal context | Today's price ≠ yesterday's | Every time price changes |

Both are Dutch, neutral factual tone.

---

## Schema Changes

**Migration:** `sql/migrations/004_add_ai_columns.sql`

```sql
ALTER TABLE products
  ADD COLUMN IF NOT EXISTS ai_description TEXT,
  ADD COLUMN IF NOT EXISTS ai_deal_description TEXT,
  ADD COLUMN IF NOT EXISTS ai_deal_description_updated_at TIMESTAMPTZ;
```

**Rollback:** `sql/migrations/rollback_004_add_ai_columns.sql`

```sql
ALTER TABLE products
  DROP COLUMN IF EXISTS ai_description,
  DROP COLUMN IF EXISTS ai_deal_description,
  DROP COLUMN IF EXISTS ai_deal_description_updated_at;
```

`sql/schema.sql` updated to include these three columns.

---

## New File: `src/ai_descriptions.py`

Single module responsible for all Claude API interaction. No Claude calls live anywhere else.

### Functions

#### `generate_product_description(product: dict) -> str | None`

Builds and sends the product description prompt. Returns the generated Dutch text, or `None` on failure.

**Input fields used:**
- `name`, `brand`, `category`
- `description` (scraped from Coolblue — may be None)
- `specs` (JSONB dict — category-specific keys)

**Prompt structure:**
```
Je bent een neutrale productredacteur voor een Nederlandse prijsvergelijkingssite.

Schrijf één alinea van 2-3 zinnen die het volgende product beschrijft op basis van de onderstaande gegevens.
Schrijf feitelijk en bondig. Geen marketingtaal. Geen prijsinformatie.

Product: {name}
Merk: {brand}
Categorie: {category}
Omschrijving: {description or "niet beschikbaar"}
Specificaties: {specs as formatted key: value lines}

Beschrijving:
```

**Output:** 2–3 sentence Dutch paragraph, ~60–80 words.

---

#### `generate_ai_deal_description(product: dict, price_context: dict) -> str | None`

Builds and sends the deal description prompt. Returns 1–2 Dutch sentences, or `None` on failure.

**Input — product fields:**
- `name`, `brand`, `category`

**Input — price_context dict (assembled by caller from price_history queries):**
- `current_price` — today's price
- `current_price_since` — date today's price was first seen (i.e. when this price level started)
- `previous_price` — most recent prior measurement before today
- `price_diff` — absolute change (positive = drop, negative = rise)
- `drop_pct` — percentage change (signed)
- `lowest_ever_price` — MIN(price) over all history
- `lowest_ever_date` — date of that minimum
- `low_30d` — MIN(price) over last 30 days
- `low_30d_date` — date of that 30-day minimum
- `high_30d` — MAX(price) over last 30 days
- `high_30d_date` — date of that 30-day maximum

**Prompt structure:**
```
Je bent een neutrale prijsanalist voor een Nederlandse prijsvergelijkingssite.

Schrijf 1-2 zinnen die de huidige prijssituatie van dit product samenvatten.
Noem alleen de meest opvallende feiten. Schrijf feitelijk, geen marketingtaal.

Product: {name} ({brand})
Huidige prijs: €{current_price} (sinds {current_price_since})
Vorige prijs: €{previous_price} ({price_diff:+.2f}, {drop_pct:+.1f}%)
Laagste prijs ooit: €{lowest_ever_price} (op {lowest_ever_date})
30-daags laagste prijs: €{low_30d} (op {low_30d_date})
30-daags hoogste prijs: €{high_30d} (op {high_30d_date})

Prijsanalyse:
```

**Output examples:**
- "De prijs daalde vandaag met €50 (−17%) naar €249 — de laagste prijs in 30 dagen. De laagste prijs ooit was €219 op 3 maart 2025."
- "De prijs steeg vandaag licht met €10 naar €289, maar blijft onder het 30-daags maximum van €320. De laagste prijs ooit was €249 op 15 januari 2025."

---

### Shared API Behaviour

- **Client:** `anthropic.Anthropic()` — reads `ANTHROPIC_API_KEY` from environment
- **Model:** `claude-haiku-4-5-20251001`
- **max_tokens:** 200 (product description), 120 (deal description)
- **temperature:** 0.3 (low variance for consistent tone)
- **Failure handling:** catch all exceptions, log the error, return `None` — caller skips the DB write and leaves existing value in place (NULL or stale)
- **No retries inside the function** — retry happens naturally on next pipeline run

---

## Pipeline Integration

### 1. `discover_products.py` — static product description

After `upsert_product()` succeeds for a product, check if `ai_description` is NULL. If NULL, call `generate_product_description()` and update the column.

**New DB function:** `update_ai_description(product_id: int, text: str)`

```sql
UPDATE products SET ai_description = %s WHERE id = %s
```

**Flow per product:**
```
upsert_product()
  → fetch ai_description for product_id
  → if NULL:
      text = generate_product_description(product)
      if text: update_ai_description(product_id, text)
      else: log warning, continue
```

**Scale:** 800 products, but only NULL rows trigger an API call. On first run all 800 will be generated. Subsequent discovery runs: only new products.

**Rate limiting:** 0.5s sleep between API calls.

---

### 2. `scrape_price_history.py` — deal description

After `upsert_price_history()` succeeds, compare today's price to the previous measurement. If they differ (up or down), fetch price context and regenerate the deal description.

**New DB function:** `get_price_context(product_id: int) -> dict | None`

Returns all fields needed for the prompt. The exact SQL will be finalised during implementation and verified against live data density before hardcoding any date ranges. Returns `None` if no previous price exists (new product).

**New DB function:** `update_ai_deal_description(product_id: int, text: str)`

```sql
UPDATE products
SET ai_deal_description = %s,
    ai_deal_description_updated_at = NOW()
WHERE id = %s
```

**Flow per product:**
```
upsert_price_history(price_facts)
  → if today_price != previous_price:
      ctx = get_price_context(product_id)
      if ctx:
          text = generate_ai_deal_description(product, ctx)
          if text: update_ai_deal_description(product_id, text)
          else: log warning, leave stale value
```

**Scale:** ~800 products scraped daily. Typically 10–50 will have a price change. Claude is only called for those.

---

## New Dependency

Add to `requirements.txt`:

```
anthropic>=0.40.0
```

---

## Environment Variables

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Required. Anthropic API key. Add to `.env.local` and Railway environment. |

---

## Cost Estimate

| Use case | Frequency | Input tokens (est.) | Output tokens (est.) | Cost (est.) |
|---|---|---|---|---|
| Product descriptions (backfill) | Once, 800 products | ~400/product | ~100/product | ~$0.06 one-time |
| Product descriptions (ongoing) | ~5–10 new/week | ~400 | ~100 | negligible |
| Deal descriptions | ~20–50/day | ~250 | ~60 | ~$0.003/day |

Haiku pricing: $0.80/M input tokens, $4.00/M output tokens (as of June 2026).

---

## File Checklist

| File | Change |
|---|---|
| `sql/migrations/004_add_ai_columns.sql` | New migration |
| `sql/migrations/rollback_004_add_ai_columns.sql` | New rollback |
| `sql/schema.sql` | Add 3 columns to products |
| `src/ai_descriptions.py` | New module — all Claude API logic |
| `src/db.py` | Add `update_ai_description`, `update_ai_deal_description`, `get_price_context` |
| `scripts/discover_products.py` | Call `generate_product_description` after upsert |
| `scripts/scrape_price_history.py` | Call `generate_ai_deal_description` when price changes |
| `requirements.txt` | Add `anthropic>=0.40.0` |

---

## Task Breakdown

| Status | # | Task |
|---|---|---|
| ✅ | T27 | Schema migration: add `ai_description`, `ai_deal_description`, `ai_deal_description_updated_at` to `products`; write rollback; update `sql/schema.sql` |
| ⬜ | T28 | Implement `src/ai_descriptions.py`: `generate_product_description` and `generate_ai_deal_description` with shared API behaviour (model, tokens, temperature, error handling) |
| ⬜ | T29 | Implement `get_price_context` in `src/db.py`: write and verify SQL query against live data; confirm date fields and 30-day window have sufficient data density before finalising |
| ⬜ | T30 | Implement `update_ai_description` and `update_ai_deal_description` in `src/db.py` |
| ⬜ | T31 | Wire `generate_product_description` into `discover_products.py`: call after upsert for NULL `ai_description` rows; add 0.5s rate-limit sleep; log outcomes |
| ⬜ | T32 | Wire `generate_ai_deal_description` into `scrape_price_history.py`: detect price change after upsert; call `get_price_context` + `generate_ai_deal_description`; log outcomes |
| ⬜ | T33 | Backfill `ai_description` for all 800 existing products: run `discover_products.py --limit` in batches or a one-off script; verify no NULL rows remain |
| ⬜ | T34 | Unit tests for `src/ai_descriptions.py`: mock the Anthropic client; test prompt construction, None-on-failure, and that no API calls are made when input is invalid |

---

## Out of Scope

- Storing prompt version or generation history
- A/B testing different prompts
- Displaying descriptions in any frontend (out of scope for this pipeline)
- Regenerating `ai_description` when specs change (deferred — specs rarely change after discovery)
