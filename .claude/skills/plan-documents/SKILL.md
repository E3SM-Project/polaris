---
name: plan-documents
description: Write a plan for work not yet started, for a colleague or the user to approve before implementation begins.
---

# Plan documents

The reader is deciding whether to let you proceed.

- Open questions and anything needing a decision go at the top.
- The steps, in order, one line each.
- Do not justify each step. Do not list the files you will touch. Do not
  restate the codebase back.
- If a step needs a paragraph to explain, it belongs in a design document.

## Enough

> **Open:** should `ekman` come out of `omega_pr` too, or wait for #753?
>
> 1. Fix the interface-field trim in the single-column viz step.
> 2. Restore the tracer expansion in the conservation checks.
> 3. Take conservation times from the whole dataset, not one slice.
> 4. Tests for all three.
> 5. Rerun `omega_pr` and `mpaso_pr` against a `main` baseline.
