# Task generator Prompt
Act as a senior software engineer.

Your job is to take a chosen development task and expand it into a correctly filled task template for Claude Code.

Context:
We are in planning mode. We are working in an iterative workflow where tasks must be small, clear, and testable.

---

Input:

Task:
[PASTE THE TASK I CHOSE]

Spec context:
/docs/spec.md

---

Instructions:

Fill the template:

## Task
[refine task if needed, but keep it small]

## Context
[1–2 sentences why this task exists]

## Constraints
[only relevant technical/architectural constraints]

## Definition of Done
[clear, testable checklist]

---

Rules:
- Do NOT expand scope
- Do NOT include unrelated parts
- Keep it minimal and precise
- Prefer simple implementations