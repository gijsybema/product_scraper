# Implement

Implement ONLY the following task or slice.

Constraints:
- No unrelated changes
- Follow existing patterns
- Keep it simple

After implementing:
1. Files changed
2. What changed
3. Assumptions made

## Inline verify

After reporting, immediately run a quick sanity check — do not wait to be asked.

**Definition of done:**
- In FAST mode: skip DoD lookup. The task description is the definition of done.
- In NORMAL mode: check `docs/spec.md` for a DoD. If not found, derive it from the task description and state it explicitly before checking. Do not ask.
- In FULL mode: check `docs/spec.md` for a DoD. If not found, stop and ask the user to provide one before continuing. Do not infer or hallucinate.

**Check (fast sanity check — not a full review):**
1. Does it do what was asked?
2. Any critical bugs or security issues?

Fix critical issues immediately. List anything else but do not fix unless asked.

## Manual testing handoff

If Claude cannot fully verify (no prod DB access, UI interaction required, external service needed, etc.):
1. State what cannot be verified and why
2. List the specific scenarios to test: steps, inputs, expected outputs
3. Stop with: **MANUAL TEST REQUIRED** — test the above and reply with pass/fail before proceeding
4. Do not mark the task done or continue until the user confirms

If this reveals an invalid assumption or missing dependency:
- In FAST mode: flag it and ask how to proceed.
- In NORMAL mode: flag it and run @plan.md if at least one of these is true: (1) more than one additional file needs to change beyond what was originally described, (2) the original approach is no longer viable and a different one is needed.
- In FULL mode: stop, flag it, and re-run @plan.md before continuing.

In FULL mode, this is a baseline pass only. A separate thorough verify follows.
