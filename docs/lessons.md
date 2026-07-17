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

## T25 — OOS deactivation logic

- **Verify data density before hardcoding a window threshold.** The 30-calendar-day window (`scraped_at > CURRENT_DATE - 30 days` + `COUNT >= 30`) looked correct in code review but returned zero results in production because scraping gaps meant no product had 30 distinct scrape days in any 30-day window. A single diagnostic count query run before implementation would have caught this instantly. For any `COUNT(...) >= N` check: verify N against real data first.
- **Streak-based logic is more robust than calendar windows for irregular data.** Anchoring on the last state-change event (`MAX(scraped_at) WHERE availability = true`) and counting forward is resilient to scraping gaps — the streak only asks "has this been continuously true since the last change?" A calendar window requires consistent data density. Prefer the streak pattern when the data source has known gaps.
- **Diagnostic queries belong alongside the feature, not after it.** Building the deactivation health check query *before* committing the function would have exposed the window problem before the first push. For any DB-backed threshold feature: write and run the diagnostic query first, then design the logic around what the data actually looks like.
- **Expanding a tuple return touches more sites than expected.** Changing `process_single_product` from 3 to 4 values required updating 3 return sites + type hint + docstring + call site. Grep for all consumers of the function before starting. Pattern: search for the function name across the codebase before expanding its return signature.

---

## Post T14 — Running discovery in production + spec housekeeping

- **Verify SQL before stating behavioral claims.** Said "30 days of data needed before deals show" without reading `deal_candidates.sql` first — the view only requires one price drop. Read the source before asserting logic.
- **Verify CLI flags before recommending them.** Gave `--category earbuds` confidently without checking the script; it's a positional argument. One grep would have prevented the correction.
- **`railway run` injects its own env vars and overrides locals.** Setting `$env:DATABASE_URL` locally has no effect when using `railway run` — it overwrites with the internal hostname. The correct pattern for one-off production scripts: skip `railway run`, set `DATABASE_URL` to the public URL, and run Python directly.

---

## T26 — Spec document cleanup

- **A completed spec is a historical artifact — freeze it.** Once all tasks are done, the spec's job is to serve as a record of what was built and why. Don't append new features to it; start a fresh file so each spec has a clear scope and a clear end.
- **One spec per independent scope.** A self-contained feature with its own definition of done gets its own spec file. A minor tweak (adjusting a threshold, adding a column) doesn't need one — a clear commit message is enough.
- **Name spec files descriptively and version them.** `spec_backend_pipeline_v1.md` is better than `spec.md`: it says what the scope was and signals that future work builds on top of it rather than modifying this file.
- **Add start and completion dates.** A spec is a historical document; two lines at the top give immediate orientation without opening the whole file.
- **`docs/` becomes a library over time.** Each spec file is a closed chapter of the product's history. Future you (or a new collaborator) can read them in order and understand how the product evolved.

---

## T27 — Schema migration: add AI description columns

- **Migration-only tasks are fast when the exact DDL is specified in the spec.** T27 had zero ambiguity — the SQL was written out in `spec_ai_descriptions.md` before implementation started. For any future migration task: write the exact DDL in the spec first, then hand off.
- **`IF NOT EXISTS` / `IF EXISTS` on every migration statement is non-negotiable for idempotency.** Follows the convention set by migrations 001–003; means the migration can be re-run safely after a partial failure without manual cleanup.
- **New nullable columns are the safest schema change — no consumer mapping needed.** No NOT NULL constraint, no default, no existing reads. Recognising this up front meant the pre-implementation check was instant: zero downstream impact on views, validators, or `db.py`.

---

## T28 — Implement src/ai_descriptions.py

- **`truststore` is the Windows SSL fix for venv HTTP clients.** Python venvs don't inherit the Windows certificate store, so any HTTPS client (httpx, requests, etc.) fails with "unable to get local issuer certificate" on networks with proxy TLS inspection. `pip install truststore` + `truststore.inject_into_ssl()` before the first call is the fix. Only needed locally — Railway runs on Linux with standard certs.
- **A `__main__` block in the module itself is cleaner than a scratchpad script.** No path hacks, no separate file, runs with `python src/module.py`. Good default for any module with an external API call worth manually reviewing.
- **Extract prompt builders from API call functions.** Separating `_build_*_prompt()` from the API call lets the `__main__` preview capture `response.usage` without duplicating logic, and makes prompts directly unit-testable in T34 without needing to mock the prompt shape.
- **Stage previews before wiring to DB.** Reviewing real API output for all 4 categories before T30/T31 confirmed tone and content quality. Cheaper to adjust a prompt string than to rewrite pipeline wiring after the fact.

---

## T29 — Implement get_price_context in src/db.py

- **Sign-convention decisions deserve an explicit, single source of truth before coding.** `price_diff` and `drop_pct` briefly ended up with opposite sign conventions because each was decided in a separate exchange without cross-checking the other. Next time a task has two related signed fields, settle both conventions together, or derive one from the other, so they can't drift apart.
- **Change-point detection (LAG + cumulative SUM) is more robust than date-diffing for "since when has X held."** Computing `current_price_since` via an `is_change` flag + windowed `SUM` correctly handles gaps and repeated values without assuming daily-contiguous data. Reusable pattern for any "how long has this state held" query.
- **Printing the actual prompt (not a paraphrased summary) in preview tooling made prompt iteration much faster.** Once `__main__` printed `_build_deal_description_prompt()`'s real output instead of a hand-formatted context line, spotting exactly which instruction wording needed tightening became immediate instead of guesswork.
- **Small/cheap models (Haiku) don't reliably honor negative instructions ("never use word X") even when explicit.** A banned word still leaked through ~1 in 4 generations despite an explicit prohibition. Default to "ship and monitor" rather than chasing 100% prompt compliance on a cost-optimized model; escalate to a regex guard or a stronger model only if it's a recurring real-world issue.

---

## T32 — Wire generate_ai_deal_description into scrape_price_history.py

- **Reusing an established pattern (RETURNING clause for "previous state") kept the design decision cheap.** Applying T31's `RETURNING id, ai_description` approach to `upsert_price_history` (return previous price) avoided a second query and needed no new design discussion — the precedent did the work.
- **An established isolation pattern doesn't propagate automatically — it has to be re-applied deliberately.** `update_ai_deal_description` was wrapped in try/except from the start (copying T31's verify fix), but `get_price_context`/`generate_ai_deal_description` right above it weren't — same task, same file, same rationale, just missed. Treat "wrap secondary/AI calls in their own try/except" as an implementation checklist item, not something verify alone should catch.
- **Manual testing converged faster by working with reality instead of forcing it.** Early plans to edit specific DB rows and call `process_single_product` directly were dropped in favor of running the real `--limit N` pipeline and classifying results after the fact against a known prior scrape date — less setup, and it exercises the real commit/rollback/batching path.
- **Manual testing surfaces a different class of issue than verify.** Missing success-path console logging and inconsistent price formatting in the generated text were both invisible to unit tests and code review — they only showed up from reading actual console output and generated Dutch text during the live run.

---

## T33–T36 — Backfill scripts, unit tests, and the empty-specs hallucination guard

- **Backfills should read from already-stored columns, not re-scrape.** `generate_product_description` only needs `name`/`brand`/`category`/`description`/`specs` — all already on the `products` row — so the backfill script never touched the network. This also let it reach the 92 inactive/discontinued products that `discover_products.py`'s live category crawl could never re-visit.
- **Setting `DATABASE_URL` manually to point a local script at prod silently skips `.env.local` loading.** `get_connection()` only imports `src.config` (which calls `load_dotenv`) when `DATABASE_URL` isn't already set — the README's manual-prod pattern bypasses that entirely. First surfaced as a cryptic Anthropic auth error on T33's first prod dry run; any future manual-prod script needing other `.env.local` vars needs its own explicit `load_dotenv` call.
- **Query live prod state before assuming a pipeline works.** Checking `scrape_runs` + a raw `COUNT(ai_description)` revealed the real explanation for "0/828 populated despite a successful discover_products run" was an undeployed feature, not a bug — avoided chasing a phantom issue in already-correct code.
- **A shared function's return-value contract can silently gain new meanings.** T36 made `generate_product_description` return `None` for both "API failed" and "correctly skipped, no specs." `backfill_ai_descriptions.py`, written before T36, still lumps both into one `skipped` counter — worth checking all existing callers whenever a shared function's failure semantics expand, not just the caller being actively edited.

---

## T30 — Rename `blocked_count` to `deactivated_count`; split out `ip_blocked_count`

- **Live verification found a bug the plan didn't anticipate.** Driving `discover_products.py` end-to-end (not just `py_compile`) surfaced a pre-existing Windows console encoding crash that silently zeroed `scrape_runs` counters on any error path. Only running the actual CLI, not a syntax check, caught it.
- **A "PASS" with mismatched numbers is not a pass.** The first verify report rationalized a sum mismatch (`total=1` but all counts `0`) as "pre-existing, unrelated" without root-causing it first. When numbers don't add up, root-cause before writing "pre-existing" — the two look identical from the outside until you check.
- **Provoking the real error condition beats mocking it.** Forcing the actual `CoolblueBlockedError` (403) branch — rather than just confirming the column accepts a write — is what proved `ip_blocked_count` accounts correctly with a real nonzero value.
- **Migration ordering discipline (local → Railway → code) paid off.** Waiting for explicit Railway confirmation before touching code that reads/writes the renamed column meant zero risk of a prod script hitting a missing column mid-run.

---

## T_E1 — Verify pgvector; schema migration for embedding column

- **Confirm which server a diagnostic query ran against before drawing conclusions, especially with multiple pgAdmin connections open.** The `SELECT version()` result (Debian 17.9) was accidentally run against the Railway connection, not local — this triggered a real detour (Docker/WSL/service forensics) chasing a phantom "two Postgres instances" mystery that didn't exist. A single mislabeled result cost the most time in this task.
- **Native Windows Postgres installs don't ship pgvector via Stack Builder — building from source is the real path.** Needed: VS Build Tools (C++ workload only, not the full IDE), an explicit `PGROOT` pointing at the correct version when multiple PG versions coexist on one machine, and an elevated terminal for the final `nmake install` step (writes into `Program Files`). Worth keeping as a runbook — this will recur if local Postgres is ever rebuilt or a teammate sets up the same project.
- **When multiple native Postgres versions are installed side by side, don't assume the one on PATH is the one in use.** `pg_config` resolved to PG17 while the actual dev DB service was PG18 — silently targeting the wrong version's `lib`/`share` directories would have made the extension invisible to the real dev DB despite a "successful" build.
- **The actual schema change was trivial — the spec had zero DDL ambiguity, all the effort was environment setup.** Reinforces the T27 pattern: writing exact DDL into the spec up front makes the code-writing step nearly instant; the local dev environment is where unplanned work actually surfaces.