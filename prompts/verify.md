# Verify

This prompt is for FULL mode. In NORMAL mode, verify runs inline as part of @implement.md — you do not need to run this separately.

---

Before verifying, retrieve the definition of done from `docs/spec.md`. If not found, stop and ask the user to provide one before continuing.

This pass focuses on thoroughness:

1. Full edge case and failure mode coverage
2. Security, privacy, and performance implications
3. Code quality: unnecessary complexity, missing tests, brittle patterns
4. Anything a PR reviewer would push back on

List issues by severity: critical / high / medium / low.

Fix critical and high immediately. List medium and low but do not fix unless asked.

If this reveals an invalid assumption or missing dependency, stop, flag it, and re-run @plan.md before continuing.

## Manual testing handoff

If any part of the verification cannot be completed (no prod DB access, UI interaction required, external service needed, etc.):
1. State what cannot be verified and why
2. List the specific scenarios to test: steps, inputs, expected outputs
3. Stop with: **MANUAL TEST REQUIRED** — test the above and reply with pass/fail before proceeding
4. Do not mark the task done until the user confirms

If no issues (and no manual testing required), confirm the task is done.
