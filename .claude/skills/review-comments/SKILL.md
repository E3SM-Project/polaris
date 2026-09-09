---
name: review-comments
description: Write a review comment, review findings, or a reply to review feedback on a GitHub pull request. Use when reviewing code, reporting what testing someone else's branch turned up, or answering a reviewer's question.
---

# Review comments

The reader is deciding what to change.

- Findings first, ordered by how much they matter. At most one sentence
  before them.
- One short paragraph per finding: what is wrong, one piece of evidence,
  stop. Not how it works.
- No section on what already works. One line for all of it, if any.
- Reproduction and configuration go in one paragraph at the end.
- Headings help once there are several findings. Use them.

## Calibration

Review comments written by colleagues in these repositories run 22 to 32
words at the median, 63 to 92 at the ninetieth percentile, and 170 at the
longest seen. A recent AI-written review ran 1117 words, with the findings
starting 444 words in.

## Enough

Real comments from this project. One point each, one suggestion, done.

> It's preferable to use xarray's `isel()` instead of explicit axis
> indexing whenever possible. It is generally clearer which axis is being
> indexed and it also means you don't necessarily need to know the axis
> order.

> Since a user doesn't have control over what tests are in a test suite, I
> think we should just remove the `default` test case from the test suite.
> This might be appropriate to have in the developer's guide instead.

With several findings, label them and keep each to a paragraph. No
human example of this shape exists in these repositories, so the following
is constructed:

> Three things, one blocking.
>
> **blocking — `MOCLatBinBoundaries` carries a time dimension.** It is
> static, so a consumer reading twelve months gets twelve times as many
> latitudes as bins. Verified in the January output file.
>
> **worth fixing — the streamfunction has no units.** Both attributes are
> empty; the values are Sverdrups. Raised last review, unchanged.
>
> **noted — written bin boundaries differ from what the operator bins on**
> by 1.8e-4 degrees, below anything that matters for a plot.
>
> Reviewed with the analysis suite from E3SM-Project/polaris#743, QU240,
> one year, intel. Plots on the LCRC portal.

## Too much

The same review, actually posted, spent its first 444 words on "How this
was reviewed", "What the previous review asked for" and four paragraphs of
"What works", then traced each finding's mechanism:

> It is static: computed once in the `MOC` constructor from `NumBins`,
> `MinLat` and `MaxLat`, and never updated. But it is attached to the
> output streams with `addField()` like any other field, so every reduction
> in every file carries a copy of the same 61 numbers.
