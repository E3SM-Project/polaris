---
name: design-documents
description: Write or revise a design document under docs/design_docs/. Use when proposing a new capability, not when fixing a bug.
---

# Design documents

Long is fine. A design document is scanned and returned to, not read
straight through. What must be scannable is the specification.

- Normative statements come first in a section and stand alone. Rationale
  goes in a marked block below, which a reader can skip.
- Rejected alternatives and superseded drafts go in one `Decisions`
  section, cited from the places they affect. Never re-argued in place.
- A principle is stated once. Later sections cite it by name.
- Do not pre-empt objections. Drop "worth noting", "not an accident",
  "deliberately", "this is not a stylistic preference". State the decision
  and let it stand.
- Open questions go at the top or in their own section, never
  mid-paragraph.

## Calibration

The two design documents in `docs/design_docs/` run 9,516 and 24,630 words,
at 28 and 30 words per sentence, with six and sixteen instances of the
hedging phrases above. Aim for twenty words per sentence and none of them.

## Enough

> ### Requirement: analysis runs on simulations Polaris did not run
>
> An analysis task shall accept a run directory it did not create, and
> shall read the model's configuration from that directory rather than
> being told it.
>
> > *Rationale.* Users bring runs from E3SM and from hand-built cases.
> > Requiring Polaris to have set them up would rule those out. Two
> > alternatives were rejected; see `Decisions: configuration discovery`.
