# CLAUDE.md

## Core Rules
- In FULL mode: always plan before coding and wait for explicit approval before implementing
- In NORMAL mode: plan is optional — if the task is clear, proceed directly to implementation; do not wait for approval between steps
- Work in small, clearly defined steps — never implement more than one task or slice at a time
- Keep changes minimal and focused; do not modify unrelated files
- Ask for clarification if requirements are unclear
- Be explicit about assumptions and decisions

## Working Style
- Follow existing architecture and patterns
- Reuse existing components where possible
- Do not refactor or rename unless necessary
- Avoid unnecessary complexity or over-engineering
- Avoid introducing new dependencies unless justified
- Do not expand scope beyond the current task
- Preserve backward compatibility unless explicitly told otherwise
- Consider edge cases, validation, error handling, security, privacy, and performance
- Add tests only when directly relevant
- Add comments only when they improve clarity
- Before implementing any task involving a state change or status transition: map all consumers/readers of that state first, and surface threshold and policy questions (when does the transition trigger? how many times?) before writing any code — one short clarifying exchange is cheaper than a full rewrite
- When a task involves side effects, do not start immediately after confirmation — pause and explicitly verify assumptions before proceeding
- Before implementing a task that depends on an external URL, path, or identifier (e.g. a Coolblue category URL): verify the exact value before writing any code — do not assume it follows the same pattern as prior examples
- When writing Coolblue parsers: anchor selectors on stable identifiers (section id, aria-label, heading text content) — never on generated CSS class names (css-*), which change between deploys
- Never modify `docs/spec.md` without explicit user confirmation; always show proposed changes and wait for approval


## Output Style
- Be concise and structured
- Do not dump large amounts of code unless necessary
- Explain key decisions briefly

## Workflow Modes

State the mode at the start of each task. If not stated, default to NORMAL silently — do not ask.

### FAST
**When:** single file, no logic risk, obvious change (rename, typo, config tweak)
```
Implement → Commit
```
No prompt needed — just describe the change and do it.

### NORMAL
**When:** features, bug fixes, clear scope, familiar code
```
Implement → Commit
```
- Plan is optional: if the task is clear, skip straight to implementation; run @plan.md only if needed
- Verify runs inline after each task (part of @implement.md)

### FULL
**When:** architecture changes, cross-cutting refactors, security-sensitive, unfamiliar area, high risk
```
Plan → Approve → Implement → Verify → Wrap-up → Commit
```
- Plan waits for explicit approval before implementing
- If the plan has more than 5 slices, flag it and suggest splitting into two tasks
- If a slice reveals an invalid assumption or missing dependency, stop, flag it, and re-run @plan.md before continuing
- Verify runs a thorough pass via @verify.md
- Wrap-up is expected

### Escalation
If scope or risk grows beyond the chosen mode mid-task: stop, state the new mode, and re-run @plan.md before continuing. Do not implement further until the new plan is approved.

### Manual Testing Handoff
If verification cannot be completed (no prod DB access, UI interaction required, external service needed, etc.): state what cannot be verified, list exact test scenarios (steps, inputs, expected outputs), and stop with **MANUAL TEST REQUIRED**. Do not mark a task done until the user confirms pass/fail.

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

## Validation Rules
- Validation functions return `(bool, list[str])` — a valid flag and a list of human-readable error reasons
- Validators mirror write path functions: one validator per DB write function, accepting the same dict shape
- When a field is intentionally left non-blocking pending a future task, add a comment referencing that task (e.g. `# category=None allowed until T11`)
- Validation failures are deterministic — do not retry them. In a retry loop, call validation after scraping and return early before the retry logic. Use `return False, ValueError(...)` to signal a validation failure to the caller.
- In scripts that track both `failed` and `skipped` counts: skipped = validation/quality issue (non-retriable, no DB write attempted); failed = scrape or DB error (retriable). Keep these counters separate.

## Dev Shortcuts
- Both `discover_products.py` and `scrape_price_history.py` accept a `--limit N` flag to process only the first N products — use this during development to test logic without running the full pipeline. Never pass `--limit` in Railway cron jobs.

## Testing Conventions
- One test file per source module: `tests/test_utils.py` → `src/utils.py`, `tests/test_db.py` → `src/db.py`
- Tests are pure where possible — no live DB, no network calls
- Idempotency is verified by inspecting SQL source strings, not by executing queries
- Do not live-test scripts for print-only changes — a syntax check + code review is sufficient; reserve live runs for changes that affect DB writes or scrape logic
- Never create one-off test scripts outside of `tests/` — write a proper unit test instead. Live DB verification belongs to the migration + manual run step, not a script.
