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
- `price_diff` — absolute change (positive = price dropped, negative = price rose)
- `drop_pct` — percentage change (positive = price dropped, negative = price rose)
- `low_90d` — MIN(price) over last 90 days (bounded to 90 days, not full history — matches the
  window the site's own price-history graph shows, so the claim is always verifiable by a visitor;
  see T38 lessons below)
- `low_90d_date` — date of that 90-day minimum
- `low_30d` — MIN(price) over last 30 days
- `low_30d_date` — date of that 30-day minimum
- `high_30d` — MAX(price) over last 30 days
- `high_30d_date` — date of that 30-day maximum

**Scenario classification (T38):** `_classify_price_situation()` in `src/ai_descriptions.py`
deterministically picks which single extra fact to surface (`low_90d`, `low_30d`, `high_30d`,
or `none`) instead of asking the model to judge what's "salient" — see T38 lessons below.

**Prompt structure (as of T38):**
```
Je bent een neutrale prijsanalist voor een Nederlandse prijsvergelijkingssite.

Schrijf een korte prijsanalyse van twee korte zinnen:
Zin 1: benoem de huidige prijs en het verschil met de vorige prijs.
Zin 2: {situation_instruction}
Houd beide zinnen kort en bondig. Schrijf feitelijk, geen marketingtaal.

Product: {name} ({brand})
Huidige prijs: €{current_price} (sinds {current_price_since})
Vorige prijs: €{previous_price} ({price_diff:+.2f}, {drop_pct:+.1f}%)
90-daags laagste prijs: €{low_90d} (op {low_90d_date})
30-daags laagste prijs: €{low_30d} (op {low_30d_date})
30-daags hoogste prijs: €{high_30d} (op {high_30d_date})

Prijsanalyse:
```

**Output examples (real, from T38 preview against live data):**
- "De Sony WF-C510 Zwart kost momenteel €42,99, een daling van €4 ten opzichte van de vorige prijs van €46,99. Dit is de laagste prijs in de afgelopen 90 dagen."
- "De Sonos Beam Gen2 Zwart kost momenteel €499, een stijging van €41 ten opzichte van de vorige prijs van €458. Dit is de hoogste prijs in de afgelopen 30 dagen."

---

### Shared API Behaviour

- **Client:** `anthropic.Anthropic()` — reads `ANTHROPIC_API_KEY` from environment
- **Model:** `claude-haiku-4-5-20251001`
- **max_tokens:** 200 (product description), 100 (deal description, lowered from 120 in T38 — a
  safety ceiling only, not the shortening mechanism; the length target comes from the prompt's
  two-sentence structure)
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
| Product descriptions (backfill) | Once, 800 products | ~400/product | ~100/product | ~$0.72 one-time |
| Product descriptions (ongoing) | ~5–10 new/week | ~400 | ~100 | negligible |
| Deal descriptions | ~20–50/day | ~250 | ~60 | ~$0.01–0.03/day |

Haiku pricing: $1.00/M input tokens, $5.00/M output tokens (as of July 2026).

See "Cost Considerations" below for actual measured cost from the T33+T35 backfill.

---

## Cost Considerations

**Actual measured cost (T33 + T35 backfill, 2026-07-12):** $1.53 for ~1,548 calls
(~828 product descriptions + ~720 deal descriptions), per Anthropic's usage
dashboard — about 2x the naive per-call estimate above. Real prompts ran
longer than the flat token estimate, mainly because formatted `specs` blocks
vary a lot in size product to product.

**Ongoing cost is a real line item, not negligible, for a pre-revenue project.**
Deal descriptions alone could run roughly €20–40/year at sales-event volumes
(100+ price changes/day), on top of whatever product-description generation
continues to cost as new products are discovered. For a project with no
revenue yet, a few euros a month for one feature is worth optimizing, not
dismissing — revisit this once there's time to focus on it specifically.

**Cost visibility:** every `generate_product_description`/`generate_ai_deal_description`
call now logs `[AI COST] ...` with tokens in/out and USD cost
(`src/ai_descriptions.py`), and every script that calls them prints an
`[AI COST TOTAL]` for the whole run. Use this instead of estimating — actual
spend is directly observable in each script's own output.

**Cost-cutting options to evaluate later** (not scoped now — revisit as a
dedicated task):
- Anthropic's Message Batches API (flat 50% discount, async) for any future
  large one-off backfill
- A cheaper/smaller model for deal descriptions specifically (shorter output,
  more templated structure — may tolerate a lower-tier model better than
  product descriptions do)
- Shortening the prompt itself (the banned-word instructions and full price
  context block add fixed overhead to every call)
- Skipping regeneration for very small price changes (e.g. <1%) where the
  deal description wouldn't meaningfully change
- Templating instead of generating for the most common/predictable cases,
  falling back to AI generation only for edge cases

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

Implementation follows a two-stage preview gate before any DB writes are introduced:
- **Stage 1 (T28):** implement the module, preview product descriptions with real DB data (one per category), user reviews quality
- **Stage 2 (T29):** implement `get_price_context`, preview deal descriptions with real price data covering key scenarios, user reviews quality
- **T30–T32** proceed only after both previews pass

| Status | # | Task |
|---|---|---|
| ✅ | T27 | Schema migration: add `ai_description`, `ai_deal_description`, `ai_deal_description_updated_at` to `products`; write rollback; update `sql/schema.sql` |
| ✅ | T28 | Implement `src/ai_descriptions.py`: `generate_product_description` and `generate_ai_deal_description` with shared API behaviour (model, tokens, temperature, error handling); preview product descriptions for one product per category (headphones, earbuds, speakers, soundbars); user reviews output before proceeding |
| ✅ | T29 | Implement `get_price_context` in `src/db.py`: write and verify SQL query against live data; preview deal descriptions with real DB data covering: price drop to all-time low, price drop (not lowest ever), price increase, small fluctuation; user reviews output before proceeding |
| ✅ | T30 | Implement `update_ai_description` and `update_ai_deal_description` in `src/db.py` |
| ✅ | T31 | Wire `generate_product_description` into `discover_products.py`: call after upsert for NULL `ai_description` rows; add 0.5s rate-limit sleep; log outcomes — **add `ANTHROPIC_API_KEY` to Railway environment variables before deploying** |
| ✅ | T32 | Wire `generate_ai_deal_description` into `scrape_price_history.py`: detect price change after upsert; call `get_price_context` + `generate_ai_deal_description`; log outcomes — **verify `ANTHROPIC_API_KEY` is present in Railway environment** |
| ✅ | T33 | Backfill `ai_description` for all 800 existing products: run `discover_products.py --limit` in batches or a one-off script; verify no NULL rows remain |
| ✅ | T34 | Unit tests for `src/ai_descriptions.py`: mock the Anthropic client; test prompt construction, None-on-failure, and that no API calls are made when input is invalid |
| ✅ | T35 | One-off backfill `ai_deal_description` for products with a genuine price change already in history: new script `scripts/backfill_ai_deal_descriptions.py` using existing `get_price_context` + `generate_ai_deal_description`; skips products with no real price change (no context to generate from); needed to seed deal descriptions for frontend development ahead of the next natural price-change cycle |
| ✅ | T36 | `generate_product_description` skips generation (returns `None`, no API call) when `specs` is `None`/empty — avoids hallucinated product copy with no factual grounding; reset the already-affected prod rows (`ai_description` generated from empty `specs`) back to `NULL` so they self-correct once real specs are scraped |
| ✅ | T37 | Verify in production that `scrape_price_history.py` actually regenerates `ai_deal_description` on a real price change: manually trigger `scrape_price_history.py --limit N` (e.g. 50) from the Railway dashboard; query prod for `ai_deal_description_updated_at` within the run's timeframe; cross-check those product IDs against `price_history` to confirm a genuine price change occurred, not just that the column was touched — see below for the full procedure |
| ✅ | T38 | Review and improve prompt wording for both `ai_description` and `ai_deal_description`: sample real production output across all categories; identify recurring quality issues (awkward phrasing, banned-word slippage, overly generic sentences); iterate on prompt copy and/or add few-shot examples; re-run previews and compare before/after |
| ⬜ | T39 | Evaluate and implement cost-cutting options for AI generation: measure current ongoing spend using `[AI COST]` logs; assess the options listed in Cost Considerations (Batches API, model downgrade for deal descriptions, prompt shortening, skip-on-small-delta, templating); implement the best trade-off(s) and re-measure |

---

## T37 Procedure: Verifying `ai_deal_description` regeneration in production

Unlike T31 (verifiable on demand — `discover_products.py --limit N` triggered manually always hits products), T32's regeneration only fires when a product's price actually changed since the last scrape, so it can't be forced on a specific run. To confirm the live wiring works in production:

1. Manually trigger `scrape_price_history.py --limit N` from the Railway dashboard, using a larger N (e.g. 50) since price changes are not guaranteed on any given day.
2. Query prod for `ai_deal_description_updated_at >= NOW() - INTERVAL '1 hour'` (or the run's timeframe) to find products touched by that run.
3. Cross-check those product IDs against `price_history` to confirm the price genuinely differs from the prior day's row — this proves the trigger condition (price change detected) matched reality, not just that the column was touched.

If no products in the sample had a price change, the run proves nothing either way — retry with a larger `--limit` or wait for a regular daily cron run and repeat the same check afterward.

---

## Known Limitation: Deal Description Wording (T29)

During T29 preview, the deal description prompt explicitly bans the words "minimum", "maximum", and "segment" in favour of concrete phrasing ("laagste prijs in 30 dagen"). Claude Haiku follows this in most cases but not 100% reliably — in preview testing it slipped ("middensegment") in roughly 1 of 4 runs despite the explicit instruction. This is a known limitation of smaller/cheaper models with negative-instruction adherence, not a bug.

**Decision:** ship as-is. Since `ai_deal_description` regenerates on every price change, an occasional awkward phrasing self-corrects on the next run. Risk accepted as low.

**Options for later iteration, if this becomes a recurring quality issue in production:**

1. **Post-processing regex guard** — after generation, check output for banned words and either retry once with a stronger reminder, or fall back to a simpler templated sentence. Cheap, deterministic.
2. **Few-shot examples in the prompt** — add 1-2 example input/output pairs showing desired phrasing. Usually the most effective lever for steering small models; slightly higher input token cost (still negligible).
3. **Structured output** — have the model fill specific slots instead of free text, reducing room to invent phrasing. More engineering, less natural-sounding text.
4. **Stronger model for deal descriptions only** — Sonnet would likely follow the ban reliably at a higher per-call cost (still cheap at ~50/day volume).
5. **Periodic spot-check in production** — monitor real output after T31/T32 ship; only invest further if quality issues are frequent.

---

## T38 Lessons: Prompt Wording Iteration

Sampled real production output across all 4 categories via `PROD_READONLY_URL` (read-only,
~26 `ai_description` + 20 `ai_deal_description` rows) before changing anything.

**Product descriptions:** no changes made. Factual, consistent 60–74 words, matches spec target.
Only soft observation: near-identical template structure across products (headline feature →
connectivity/battery → weight/materials), most visible on near-duplicate colour variants of the
same product. Not a defect against the "feitelijk en bondig" brief — left as-is.

**Deal descriptions — findings and fixes:**

1. **Verbose by default.** Every sampled row used the full 2-sentence structure and packed in
   current price + previous price + 30-day range + all-time-low regardless of whether that much
   detail served the story (baseline avg ~39 words/call). Fixed by moving to a fixed 2-sentence
   template (current price + diff, then exactly one deterministically-chosen extra fact) — avg
   ~29 words/call in the final version.
2. **"Pick the most salient fact" was too subjective.** An early revision asked the model to
   judge what's noteworthy itself; results were inconsistent between otherwise-similar inputs.
   Replaced with `_classify_price_situation()` in `src/ai_descriptions.py` — a small deterministic
   Python function that decides which single fact (`low_90d`, `low_30d`, `high_30d`, or none) is
   true from the data, so the model only phrases a pre-selected fact instead of judging anything.
3. **Invented timeframe for the previous price.** One live-data test produced "...slechts €1 meer
   dan **vorige week**" — but no date for the previous measurement is ever given in the prompt
   (only `current_price_since` has one). The model was guessing a plausible-sounding period. Fixed
   with an explicit prompt rule forbidding any time-period word (`vorige week`, `gisteren`,
   `eerder`, etc.) attached to the previous price.
4. **"Laagste prijs ooit" (lowest ever) was not verifiable by site visitors.** `lowest_ever_price`
   was `MIN(price)` over the *entire* `price_history` table, unbounded — but the site's own
   price-history graph only shows 90 days, and prod data already spans 175 days. A visitor could
   be told "the lowest price ever" for a price point they can't see on the graph. Fixed by bounding
   the query to 90 days (`get_price_context` in `src/db.py`: field renamed `lowest_ever_price` /
   `lowest_ever_date` → `low_90d` / `low_90d_date`, same windowing pattern as the existing
   `low_30d`/`high_30d`) and rewording the prompt from "ooit" to "in de afgelopen 90 dagen"
   throughout. Considered but rejected: keeping the "ooit" wording while silently bounding the
   query — still misleading, just less visibly so. Long-term preferred fix (showing more than 90
   days of history on the site) is a frontend-repo concern, out of scope here — flagged to the
   user to track there.
5. **`max_tokens` is a truncation ceiling, not a shortening mechanism.** Lowering it alone
   (120 → 60) caused one live response to cut off mid-sentence. The actual shortening comes from
   the prompt's fixed sentence structure; `max_tokens=100` is only a safety backstop.

**Verification:** re-ran the deal-description prompt against 5 real scenarios pulled fresh from
prod (all-time-low-equivalent/`low_90d`, drop-not-lowest, price-increase/`high_30d`, small
fluctuation, and a `low_30d`-but-not-`low_90d` case) — all classified correctly, no banned words,
no invented timeframes, no truncation. Full test suite (138 tests) passes after the `get_price_context`
rename.

---

## Out of Scope

- Storing prompt version or generation history
- A/B testing different prompts
- Displaying descriptions in any frontend (out of scope for this pipeline)
- Regenerating `ai_description` when specs change (deferred — specs rarely change after discovery)
