# Lessons Learned

## T6 — Unit tests + project housekeeping

- **The verify → review → fix cycle caught real issues incrementally.** The redundant smoke test, missing whitespace edge case, and in-function `import pytest` were all found through review — not upfront. Trusting the loop works.
- **Scope rules in prompts are guidelines, not hard blocks.** The fix prompt says critical/high/medium only, but you asked to fix low issues every time. Either update the prompt to say "all issues" or accept overriding it — the current wording creates friction each round.
- **Ask the structural question earlier.** Separating `test_utils.py` and `test_db.py` only came up at the end after the file was already built. Deciding file structure upfront (during recon/plan) avoids a refactor step.
- **`CLAUDE.md` is more powerful than prompt files for a solo workflow.** Rules in `CLAUDE.md` load automatically every session; prompt files require a manual step. Consolidating saved a step you'd otherwise repeat every session.
- **Duplicate rules across files will drift.** The migration checklist existed in both `spec.md` and `CLAUDE.md` briefly. One source of truth per rule — enforce this at the moment of writing, not after.
- **Testing pure functions is fast and high-value.** The entire T6 test suite runs in under 0.1s with no mocking, no fixtures, no DB. Keeping functions pure makes testing trivial — worth keeping this in mind when designing new functions.
- **Source inspection (`inspect.getsource`) is a pragmatic way to test SQL contracts** without a live DB. It's not a substitute for integration tests but catches accidental rewrites cheaply.

---

## T7 — Wire scrape_runs into discover_products.py

- **Architectural questions before implementation are worth the time.** The meta-discussion about retry logic (is `retry_scrape_price_history.py` over-engineered?) took 10 minutes but prevented adding the same pattern to `discover_products.py`. The answer was "don't extend it" — that only comes from asking first.
- **The review step caught a real bug.** The medium issue — `finish_scrape_run` throwing in the except block would swallow the original exception — was not caught during implementation or verification. The review step is doing its job; don't skip it on "simple" tasks.
- **Wrap logging calls in exception paths defensively.** When you log failure inside an except block, that log call can itself fail (dead connection, serialisation error). Always wrap it in its own try/except so the original exception is never replaced by a secondary one.
- **Recon on a reference implementation is faster than reading docs.** Reading `scrape_price_history.py` gave the exact call signature, commit pattern, and status values in one pass — no need to re-read `db.py` in depth.
- **Defer zero-value warnings to the observability task.** A `total_products=0` result is ambiguous (empty run vs. blocked scrape) but the right fix is a structured warning in T8, not a one-off print here. Noting it in the spec and moving on kept T7 small.

---

## T8 — Structured observability summary across all scripts

- **Slice by file, not by feature.** Doing one script per slice (S1→S2→S3) made review and fixes focused. The alternative — adding the summary block to all three scripts at once — would have bundled three sets of edge cases into one review cycle.
- **`return` inside a `try` block triggers `finally` unexpectedly.** Moving early exits (no retry due, max retries) outside the `try` block before adding a `finally` summary prevented misleading `status=failed` output on normal no-op runs. Always check for `return`/`raise` inside `try` when adding a `finally`.
- **Initialise all variables used in `finally` before the `try`.** `run_id = None`, `status = "failed"`, `success = 0` as defaults made the summary safe to print on any crash path. This is the pattern to follow in every new script.
- **A bad fix attempt is worse than leaving a medium issue open.** The first attempt at fixing the pre-`try` unguarded exception used a `finally` clause that referenced unbound variables — introducing a new `NameError`. Reverting and keeping the original structure was cleaner. When a fix adds complexity, step back.
- **Live testing expensive scripts only for logic changes, not print statements.** The jitter sleep (up to 10 minutes) makes full runs expensive. For pure observability changes (print statements in `finally`), a syntax check + code review is sufficient verification. Reserve live runs for changes that affect DB writes or scrape logic.
- **Defer false-positive warnings to the task that introduces multi-category.** The zero-product warning is a false positive if a category genuinely has no products — but that case doesn't exist yet. Adding the warning now and noting the limitation in T11 is the right call; don't pre-solve hypothetical problems.
- **Quote nesting in f-strings is a real friction point.** `due['id']` inside a double-quoted f-string is valid Python but flagged by some linters and confusing to read. Extracting to a named variable (`due_id = due["id"]`) is cleaner and avoids the issue entirely — do this by default.

---

## T9 — Implement data quality validation function

- **Two write paths → two validators.** When a module has two separate DB write functions (`upsert_product` and `upsert_price_history`) with different field shapes, separate validators per write path are cleaner than one combined function. Mirror the write path structure in validation design.
- **Deliberate temporary exceptions need a task reference.** `category=None` is allowed in `validate_product_details` to avoid blocking valid writes before T11 closes the gap. Without noting this, a future tightening pass will either over-block or silently leave the exception in place. Flag intentional deferrals at the point of decision.
- **Pure functions with `(bool, list[str])` returns are frictionless to test.** No mocking, no fixtures — just call with a dict and assert. Established as the validation signature pattern for this project; follow it for any future validators (e.g. specs in T15–T18).

---

## T10 — Wire validation into DB write path; log skipped records

- **Validation failures are a different failure mode from scrape failures.** Distinguishing `skipped` (quality issue, non-retriable) from `failed` (scrape error, retriable) keeps fail-ratio metrics honest and prevents wasted retry attempts. This distinction should be decided at plan time, not implementation time.

---