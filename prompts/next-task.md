# Next Task

First, check whether `docs/spec.md` exists and contains task definitions.

- If it does not exist: stop and say "No spec.md found. Either run @0-interview.md to generate one, or tell me the task directly."
- If it exists but appears empty, placeholder-only, or has no incomplete tasks: stop and say "spec.md exists but has no actionable tasks. Update it or tell me the task directly."

Otherwise, identify the next logical task (first incomplete, highest priority, or next in sequence).

Report:
1. **Task** — name and one-line description
2. **Why this one** — why it's next (sequence, dependency, priority)
3. **Suggested mode** — FAST, NORMAL, or FULL, with a one-sentence reason

Then wait for confirmation before proceeding. The user may confirm, override the mode, or redirect to a different task.
