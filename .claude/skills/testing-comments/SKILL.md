---
name: testing-comments
description: Write a Testing comment on a pull request, recording what was run and what the results were. Use after running suites, tests or linting for a PR.
---

# Testing comments

What you ran, where, and whether it passed.

- Name the suite, the machine and the compiler. One sentence.
- Give the work directory or the baseline you compared against.
- Say the result. Bit-for-bit, passed, or the numbers if they matter.
- Use a table only when there are several runs to compare.
- Do not restate in prose what a table or a pasted result already shows.
- Failures unrelated to the branch go under their own heading at the end.

## Calibration

Measured over Testing comments from 2023, before any agent wrote here.
They run 21 to 43 words. A recent agent-written one ran 606 words.

## Enough

> ## Testing
>
> I ran the cosine bell test suite on Chrysalis with Intel and OpenMPI:
> ```
> /lcrc/group/e3sm/ac.xylar/polaris_0.1/chrysalis/test_20230304/cosine_bell_yaml
> ```
> Results are bit-for-bit with the current `main`.

> ## Testing
>
> I tested this by successfully running several baroclinic channel and
> cosine bell tests on Chrysalis (comparing with a baseline).

When the results are worth pasting, paste them and stop:

> ## Testing
>
> I ran 4 baroclinic channel test cases on Chrysalis and verified that they
> are BFB with a baseline from 2 days ago:
> ```
> Test Runtimes:
> 00:07 PASS ocean/baroclinic_channel/10km/decomp_test
> 00:04 PASS ocean/baroclinic_channel/10km/restart_test
> ```

## Too much

A real agent-written comment put the table in, then said the same thing
again in prose:

> Every task now runs to completion. The five diffs are all of the form
> `File ... does not exist`: `main` crashed before writing those outputs,
> so there is nothing to compare against. Every comparison that had a file
> on both sides passed. A clean like-for-like comparison for those five
> tasks needs a fresh baseline once this lands.
