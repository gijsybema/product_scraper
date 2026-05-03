# Plan

Analyze the codebase for this task. Do NOT make changes yet.

## Instructions

1. Relevant files and how they currently work
2. Assumptions or ambiguities
3. Implementation plan — files to change or create, and why
4. Breakdown into slices (keep slices small and independent)
5. Recommended first slice
6. Risks or likely failure points

## State changes and status transitions

If the task involves changing a flag, status, or any shared state:
- Map all consumers and readers of that state before proposing any plan
- Surface threshold and policy questions explicitly (when does the transition trigger? how many times? what are the downstream effects?)
- Do not propose an implementation until these are answered — list them as open questions and wait for confirmation

## Constraints
- Focus only on this task
- Respect the definition of done
- Align with existing architecture
- Avoid unnecessary complexity
- Do NOT modify any files — analysis only

If the plan has more than 5 slices, flag it and suggest splitting into two tasks before proceeding.
