# CLAUDE.md

## Core Rules
- Always plan before coding
- Never implement more than one slice at a time
- Keep changes minimal and focused
- Ask for clarification if requirements are unclear

## Workflow
Interview Phase → Task Loop → Slice Loop

### Interview Phase
Interview → Generate spec → Save spec

### Task Loop
Select Task → Define → Plan → (Slice Loop) → Complete Task → Next Task

### Slice Loop
Implement → Verify → Review → Fix → Repeat (until task is done)

## Implementation Rules
- Follow existing architecture and patterns
- Do not modify unrelated files
- Reuse existing components where possible
- Do not refactor or rename unless necessary
- Avoid introducing new dependencies unless justified
- Do not expand scope beyond the current task
- Preserve backward compatibility unless explicitly told otherwise

## Output Style
- Be concise and structured
- Do not dump large amounts of code unless necessary
- Explain key decisions briefly

## Deploy & Migration Rules
- Never update Railway cron jobs until the full pipeline has been manually verified
- Always apply schema migrations locally in pgAdmin first, then Railway, before pushing any dependent code to `main`
- `sql/schema.sql` is the authoritative create-from-scratch reference — keep it in sync with the live schema after every migration

### After any `ALTER TABLE`, verify before pushing:
- [ ] `sql/schema.sql` updated to match live schema
- [ ] `sql/views/deal_candidates.sql` — check named column references; re-apply view if columns were renamed or dropped
- [ ] `sql/views/dealpage_topdeals.sql`, `homepage_topdeals.sql` — verify no unintended columns exposed
- [ ] `src/db.py` — check `upsert_product` INSERT/UPDATE column lists and `get_products_to_scrape` SELECT
- [ ] `scripts/send_alerts.py` — JOINs `products` with named columns; verify still valid

## Error Handling Rules
- In exception handlers, always wrap secondary operations (e.g. DB logging, run log writes) in their own try/except — a failure in the handler must never replace the original exception
- Always initialise variables used in `finally` before the `try` block (`run_id = None`, `status = "failed"`, `success = 0`) — the summary or cleanup must be safe to execute on any crash path
- When adding a `finally` to an existing `try`, check for `return`/`raise` inside the `try` first — they trigger `finally` and can produce misleading output if defaults are not set

## Testing Conventions
- One test file per source module: `tests/test_utils.py` → `src/utils.py`, `tests/test_db.py` → `src/db.py`
- Tests are pure where possible — no live DB, no network calls
- Idempotency is verified by inspecting SQL source strings, not by executing queries
- Do not live-test scripts for print-only changes — a syntax check + code review is sufficient; reserve live runs for changes that affect DB writes or scrape logic
