---
name: pr-descriptions
description: Write or update a pull request description, including drafting pr_description.md before opening a PR. Use when opening a pull request or editing its body.
---

# Pull request descriptions

The reader is deciding whether to review.

- What changed and why, in a few sentences. Not how.
- Anything needing a reviewer decision goes in its own short list near the
  top, never mid-paragraph.
- A list of changed behaviours is fine. A trace of the mechanism is not.
- No commit list. No testing; that goes in a separate `Testing` comment.
- Link the issue or upstream pull request that gives context.
- Several fixes usually means several pull requests.

## Calibration

Measured over pull requests from 2023 and 2024, before any agent wrote
here. Descriptions run 27 to 28 words at the median, 45 to 62 at the
seventy-fifth percentile, 103 to 110 at the ninetieth, and 354 at the
longest. A recent agent-written one ran 1167 words, more than three times
the longest a colleague has written.

## Enough

A bug fix, stated and done:

> When you add an input in a subdirectory and the target is also in the
> subdirectory of another step, polaris was previously incorrectly creating
> an absolute path to the input relative to the step's workdir, rather than
> the subdirectory where the symlink exists. This merge fixes that bug.

A port, with the changes as a list:

> This PR ports the `ocean/single_column_model/planar/cvmix_test` from
> compass-legacy as `ocean/single_column/10km/cvmix`.
>
> The following changes are made from compass-legacy:
> * creating the initial state in python instead of MPAS-Ocean's init mode
> * using a uniform vertical grid rather than a custom grid, which was
>   specified in init mode
> * adding a viz step

## Too much

A real agent-written description gave each of five fixes its own section
and traced its mechanism:

> `polaris.ocean.conservation` gained a module-scope import of
> `polaris.ocean.model.time`, which runs
> `polaris/ocean/model/__init__.py`, which imports the step classes, which
> import `polaris.ocean.conservation` back. The module could no longer be
> imported on its own; it worked only when something else imported
> `polaris.ocean.model` first.

Someone deciding whether to review does not need the cycle traced. One
sentence would do; the rest belongs in the commit message.
