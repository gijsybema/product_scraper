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

## T10b — Deactivate products on repeated 404s; filter inactive products from deal views

- **Trace downstream effects before designing any state change.** Setting `active = false` had non-obvious consumers: deal views showing broken URLs, re-discovery silently reactivating products. Walking through all readers of a flag before writing code is faster than finding them mid-implementation.
- **Clarify the "when" and "how many times" before implementing.** The first implementation was thrown away because the threshold (1 vs 3 404s) and the deactivation policy weren't agreed upfront. For any task involving a status transition, surface those questions first — one short exchange is cheaper than a full rewrite.
- **As a Claude user: slow it down when a task involves side effects.** Pushing back with "wait, what are the assumptions here?" before implementation begins is a legitimate and valuable move — it's not slowing things down, it's speeding up the net result.
- **Throwaway test scripts are a smell.** `test_t10b.py` mutated live data, was fragile to crashes, and lived in the wrong place. The right question is always: what can a mock cover, and what genuinely requires a live DB? Usually the answer is "more than you think."

---

## T11 — Wire slug generation into discovery; category-aware zero-product warning

- **`COALESCE(products.slug, EXCLUDED.slug)` is the right default for backfilled columns.** It means: preserve the existing value if set, accept the new one only if the column is null. This made the backfill (T5) and the live discovery run compatible without any ordering constraint — run either first, the result is the same.

---

## T11b — Enforce category validation; thread discovery URL category as fallback

- **Derive implicit context from what the caller already knows.** The discovery script already knows the category URL — deriving `fallback_category` from it required no new input from the user and no extra network call. When a fallback is needed, check what the caller has before adding a new parameter or config value.

---

## T13 — Multi-category discovery: speakers

- **Verify external identifiers before assuming the pattern holds.** The Coolblue URL for speakers (`draadloze-speakers/filter`) does not follow the Dutch-noun pattern of headphones (`hoofdtelefoons`) or earbuds (`oordopjes`). Assuming the pattern caused a wrong URL and an unnecessary `_CATEGORY_MAP` entry that had to be rolled back. For any new category, confirm the actual URL before writing code.

---

## T12 — Multi-category discovery: earbuds

- **Verify documented interfaces are actually wired up.** The docstring said the script accepted a `[category_url]` CLI arg, but `main()` never read `sys.argv`. Always trace the call path, not just the docstring.
- **Pass the semantic value, not a derived one.** The original design passed a URL and re-derived the category from it. Passing the category name directly eliminated the URL-parsing step, the fallback warning, and a potential misclassification bug — all at once.
- **Substring normalization has order-dependent bugs.** `"hoofdtelefoon"` is a substring of `"in-ear-hoofdtelefoons"`, so an earbuds URL would have silently mapped to `headphones`. Tracing the normalization logic during planning caught this before any data was written.

---

## T16 — Parser: description + specs for earbuds

- **A well-designed extension point pays off immediately.** `_SPEC_KEYS` as a plain dict meant T16 was one dict entry + tests — no structural changes, no new functions, no DB work. Investing in the right abstraction in T15 made T16 take 20 minutes instead of an hour.
- **The inspector tool caught the encoding bug on first real use.** The `→` crash in `tools/inspect_product_page.py` would have blocked every future category's recon step. Finding and fixing it in T16 (the first time the tool was actually run end-to-end on Windows) is exactly the payoff of building the tool early.
- **Category-specific key sets should be diffed against each other at review time.** Explicitly checking shared vs. earbuds-only vs. headphones-only keys in verify caught nothing wrong — but the habit of making the diff visible is worth keeping. For T17/T18 the diff will be larger.

---

## T15 — Parser: description + specs for headphones

- **DOM inspection is part of the plan, not a pre-plan nicety.** Fetching the live page and walking the DOM (10 minutes) produced concrete, stable selectors that made the implementation straightforward. Skipping this step would have produced wrong selectors discovered only at test time. For any Coolblue parser task: inspect first, then plan.
- **Anchor on semantic identifiers, never on generated CSS class names.** Coolblue uses CSS-in-JS (`css-19mtnxi`, etc.) that changes between deploys. The stable handles are: `section#product-information`, `section#product-specifications`, `h3` text content, `svg[aria-label]`. Follow this rule for T16–T18.
- **Build the dev tool on the first category, use it on the rest.** `tools/inspect_product_page.py` cost ~15 minutes in T15 but will cut the recon step for T16–T18 to seconds. Investing in a reusable inspection tool at the start of a repeated-category pattern is worth it.
- **`pytest` at the root silently collected dead archive files.** This only surfaced because we ran the full suite during verify. A `pytest.ini` with `testpaths = tests` is basic project hygiene — add it as soon as a project has non-test directories with test-shaped filenames.

---

## T18 — Parser: description + specs for soundbars

- **Bundle pages are identifiable from the inspector output — two `Artikelnummer` rows and duplicate Dutch labels are the tell.** When you see this pattern, the key mapping is still derivable from the first product's block, but the risk of silent spec mixing is real. Prefer single-product URLs for inspector recon; bundle URLs work but require manually scoping to the right product block.
- **Add known limitations to the spec risks table at the moment of discovery, not later.** The bundle page limitation was written into the risks table in the same session it was found. If it had stayed in the chat, it would have been lost. The spec is the right place — documentation tasks (T21/T22) are for narrative, not for decisions already made.
- **The plan review gate (propose key table → user adjusts → implement) consistently catches missing keys.** T15–T18 all had 2–5 user additions at plan review time. This is not incidental — the key table format makes it easy to scan and add. Always present the table before implementing S1; never skip straight to code after inspection.

---

## T17 — Parser: description + specs for speakers

- **Plan review is the right place for cross-category design questions.** The label-alignment question (align `Gewicht` / `Gewicht in gram` or keep separate?) was resolved in one exchange before any code was written. Raising it at plan time cost 30 seconds; discovering it at test time would have cost a rewrite.
- **Different Dutch labels → different English keys, even if semantically related.** `Waterdichtheid` (text: "Waterdicht") and `Waterbestendig` (bool: Ja/Nee) describe water resistance but have different shapes. Forcing a shared key would lose information. Let the JSONB column hold per-category variation naturally — unification is a frontend concern.
- **The inspector tool continues to pay for itself.** T17 recon was one command, one clean output, full specs table in one pass. The encoding fix in T16 meant no issues on Windows. The investment in T15 has now cut recon time on every subsequent category.
- **Adding keys during plan review is the correct workflow.** Two extra keys were caught in the plan review before implementation started — a 10-second change to a table. The same addition mid-implementation would have required re-reading the key map, re-counting, and updating test assertions.

---

## T20 — Cron/Railway update; retire retry script; add --all and --missed-only modes

- **Counter exhaustiveness needs a check, not trust.** The `total_products != success + failed + blocked` mismatch went unnoticed because 404-below-threshold products fell through all three counters silently. When building mutually exclusive outcome buckets, add an integrity assertion at the write site — don't rely on "the math looks right" in review.
- **Job name scope matters for observability.** Using a single `"discover_products"` job name would have made per-category audit trails in `scrape_runs` unreadable. Naming jobs by their specific scope (`discover_products_{category}`) is worth thinking about upfront, not retrofitting.
- **Recovery-mode semantics need an explicit decision before coding.** Whether a recovery run should overwrite existing prices or only fill gaps is easy to get wrong silently. Surfacing that question before writing any code saved a rewrite.
- **Update the docstring in the same edit as the flag.** Adding `--missed-only` without updating the module docstring caused a separate fix commit. Avoidable with a single habit.

---

## Post T14 — Running discovery in production + spec housekeeping

- **Verify SQL before stating behavioral claims.** Said "30 days of data needed before deals show" without reading `deal_candidates.sql` first — the view only requires one price drop. Read the source before asserting logic.
- **Verify CLI flags before recommending them.** Gave `--category earbuds` confidently without checking the script; it's a positional argument. One grep would have prevented the correction.
- **`railway run` injects its own env vars and overrides locals.** Setting `$env:DATABASE_URL` locally has no effect when using `railway run` — it overwrites with the internal hostname. The correct pattern for one-off production scripts: skip `railway run`, set `DATABASE_URL` to the public URL, and run Python directly.

---