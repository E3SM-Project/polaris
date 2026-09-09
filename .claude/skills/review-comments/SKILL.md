---
name: review-comments
description: Write a review comment, review findings, or a reply to review feedback on a GitHub pull request. Use when reviewing code, reporting what testing someone else's branch turned up, or answering a reviewer's question.
---

# Review comments

The reader is deciding what to change.

- Put each finding as an inline comment on the line it concerns, one point
  each. That is where colleagues put them, and it is why their review
  bodies are short.
- The review body summarizes: what you ran, and the verdict. Two or three
  sentences.
- Use a list in the body only for requests that span files.
- No section on what already works. One line for all of it, if any.
- Say what you could not check.

## Calibration

Measured over review comments from 2023, before any agent wrote here.
Review bodies run 14 words at the median, 55 at the ninetieth percentile,
and 239 at the longest. Inline comments run 22 to 32 words at the median
and 170 at the longest. A recent agent-written review ran 1117 words, with
the findings starting 444 words in.

## Enough

Inline, one point and a suggestion:

> It's preferable to use xarray's `isel()` instead of explicit axis
> indexing whenever possible. It is generally clearer which axis is being
> indexed and it also means you don't necessarily need to know the axis
> order.

> Since a user doesn't have control over what tests are in a test suite, I
> think we should just remove the `default` test case from the test suite.
> This might be appropriate to have in the developer's guide instead.

In the body, when several requests span the whole change:

> Thanks for putting this together and the overall system looks good.
> However, I think we need to make this a cleaner, simpler PR with the
> following changes:
>
> - For the CIME changes and YAKL submodule, I think we need to sync the
>   OMEGA repo so it's up to date with E3SM.
> - Can you please remove the logger and spdlog. This will need a separate
>   PR and discussion.

## Too much

A real agent-written review spent its first 444 words on "How this was
reviewed", "What the previous review asked for" and four paragraphs of
"What works", then traced each finding's mechanism:

> It is static: computed once in the `MOC` constructor from `NumBins`,
> `MinLat` and `MaxLat`, and never updated. But it is attached to the
> output streams with `addField()` like any other field, so every reduction
> in every file carries a copy of the same 61 numbers.
