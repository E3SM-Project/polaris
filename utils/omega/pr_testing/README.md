# Omega PR testing utility

This utility runs the testing the Omega pull request template asks for: the
CTests and the Polaris `omega_pr` suite on each supported machine and
compiler, plus linting and the documentation build, reported as `Testing`
comments on the PR.  It can be driven by a developer or by AI
agents, one per machine; agents follow [AGENTS.md](AGENTS.md).  The design
is in `docs/design_docs/omega_pr_testing.md`.

## How it works

1. **`init`** (any machine) merges the PR into its base branch and pushes
   the result to the requester's fork as a test branch, with a manifest
   that pins the test and baseline commits and the rows to test.  The
   baseline is the Omega commit that Polaris `main` pins, unless another is
   given with a reason.
2. **`lint`** (the initiator) checks pre-commit and the docs build.  When
   Omega's CI has passed on the PR head, there is nothing to post, since
   the PR's checks show it.  Otherwise it runs them, and `--post` posts the
   result.
3. **`setup`** (each machine) checks the Polaris checkout against the
   manifest, reuses a matching baseline run if it finds one, and otherwise
   builds and sets one up.  It then builds and sets up the PR suite, and
   prepares the CTests.  It prints the three jobs, or submits them with
   `--submit`.
4. **`report`** (each machine) writes the row's comment: a generated
   summary, the files Polaris and CTest wrote pasted unchanged, with the
   commits of Polaris and both Omega builds, and the compiler warnings the
   PR build has that the baseline build does not.  `--post` posts it.
5. **`status`** lists which rows have been reported and whether they are
   for the PR's current head.

## Setup on each machine

- A Polaris checkout with a load script for the compiler (`./deploy.py`).
- A clone of E3SM-Project/Omega.
- `~/.config/omega_pr_test.cfg`, copied from [example.cfg](example.cfg).
- `gh`, logged in, for `init`, `lint`, `status` and `--post`.

Source the load script, then run
`./utils/omega/pr_testing/omega_pr_test.py <command> --help` for the
options.

## Example

```bash
# initiator
omega_pr_test.py init --pr 553 --push
omega_pr_test.py lint --fork git@github.com:me/E3SM.git \
    --branch omega-pr-test/553-54456ec --post

# each tester
omega_pr_test.py setup --fork git@github.com:me/E3SM.git \
    --branch omega-pr-test/553-54456ec --submit
# ...when the jobs finish
omega_pr_test.py report --fork git@github.com:me/E3SM.git \
    --branch omega-pr-test/553-54456ec --post

omega_pr_test.py status --pr 553
```

## Layout

```
<work_base>/
  omega/<sha12>/                  Omega worktrees, one per commit
  baselines/<machine>_<compiler>_polaris-<sha7>_omega-<sha7>/
    build/  omega_pr/             baselines, reused across PRs
  pr<N>-<head sha7>/
    lint/                         lint report (and local logs)
    <machine>_<compiler>/
      build/  omega_pr/  ctest/   the PR build, suite and CTest job
      setup.json  report.md
```

Test branches, `omega-pr-test/<N>-<head sha7>` and its `-baseline`
branch, can be deleted from the fork once the PR merges.
