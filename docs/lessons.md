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