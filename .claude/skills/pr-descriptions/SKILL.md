---
name: pr-descriptions
description: Write or update a pull request description, including drafting pr_description.md before opening a PR. Use when opening a pull request or editing its body.
---

# Pull request descriptions

The reader is deciding whether to review.

- What changed and why, in a few sentences. Not how.
- Anything needing a reviewer decision goes in its own short list near the
  top, never mid-paragraph.
- No commit list. No testing; that goes in a separate `Testing` comment.
- Link the issue or upstream PR that gives context.
- Several fixes usually means several pull requests.

## Calibration

Pull request descriptions written by colleagues here run 28 words at the
median in Polaris and 46 in Omega, and 300 at the seventy-fifth
percentile. A recent AI-written one ran 1167 words, which is longer than
any human-written description in either repository.

## Enough

Real descriptions from these repositories.

> Add a missing assignment of the error code returned by
> `OMEGA::ocnFinalize`. We also clean up the C++/Fortran interface, by
> making the C++ function return void (now consistent with their Fortran
> declaration).
>
> Error codes are all handled on the C++ side; any logic dependent on the
> error code value is handled in C++. So, we have no need to pass the
> return codes to Fortran.
>
> Missing assignment came to light when testing E3SM-Project/Omega#526.

> This PR updates the test meshes to the latest versions for Omega tests.
>
> In addition, it removes the compiler configurations for AMD compilers on
> Frontier, whose support has been discontinued.
>
> Temporary fixes: #707

## Too much

A real description gave each of five fixes its own section and traced its
mechanism:

> `polaris.ocean.conservation` gained a module-scope import of
> `polaris.ocean.model.time`, which runs
> `polaris/ocean/model/__init__.py`, which imports the step classes, which
> import `polaris.ocean.conservation` back. The module could no longer be
> imported on its own; it worked only when something else imported
> `polaris.ocean.model` first.

Someone deciding whether to review does not need the cycle traced. Two
sentences would do, and the rest belongs in the commit message.
