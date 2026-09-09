---
name: testing-comments
description: Write a Testing comment on a pull request, recording what was run and what the results were. Use after running suites, tests or linting for a PR.
---

# Testing comments

Scanned now, re-audited later. Tables carry the results.

- One line of configuration: machine, compiler, submodule hashes.
- Results go in tables. Prose only for what a table cannot say.
- Do not restate in prose what the table already shows.
- Do not repeat the pull request description.
- Failures unrelated to the branch go under their own heading at the end.

## Enough

A colleague's whole testing report:

> Builds were successful on pm-cpu (gnu), pm-gpu (gnugpu), Frontier CPU
> (craygnu), and Frontier GPU (craygnu-mphipcc).
>
> All CTests passed.

With suite results, let the table do it:

> Chrysalis, gnu, MPAS-Ocean at `b7759691a5`. 840 tests pass, pre-commit
> clean.
>
> | suite | main | this branch |
> | --- | --- | --- |
> | `mpaso_pr` execution failures | 7 of 24 | 0 |
> | `mpaso_pr` baseline diffs | not reached | 5 |
>
> The five diffs are missing baseline files; `main` never wrote those
> outputs.

## Too much

A real comment put the table in, then said the same thing again in prose:

> Every task now runs to completion. The five diffs are all of the form
> `File ... does not exist`: `main` crashed before writing those outputs,
> so there is nothing to compare against. Every comparison that had a file
> on both sides passed. A clean like-for-like comparison for those five
> tasks needs a fresh baseline once this lands.
