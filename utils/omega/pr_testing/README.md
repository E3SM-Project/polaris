# Omega PR testing utility

This utility runs the testing the Omega pull request template asks for: the
CTests and the Polaris `omega_pr` suite on each supported machine and
compiler, plus linting and the documentation build, reported as `Testing`
comments on the PR.  It can be driven by a developer or by AI agents, who
follow [AGENTS.md](AGENTS.md).  The design is in
`docs/design_docs/omega_pr_testing.md`.

By default, one agent on your own computer does everything, running each
machine's commands over ssh through the connections you open by logging
in.  Frontier does not allow such connections, so an agent on Frontier tests
its rows.  An agent on every machine also works, but is discouraged.

## How it works

1. **`init`** (your computer) merges the PR into its base branch and pushes
   the result to the requester's fork as a test branch, with a manifest
   that pins the test and baseline commits and the rows to test.  The
   baseline is the Omega commit that Polaris `main` pins, unless another is
   given with a reason.  If the PR needs Polaris changes that the baseline
   Omega cannot run, `--polaris-ref` names a Polaris test merge for the PR
   and `--baseline-polaris-ref` the Polaris commit for the baseline.
2. **`lint`** (your computer) checks pre-commit and the docs build.  When
   Omega's CI has passed on the PR head, there is nothing to post, since
   the PR's checks show it.  Otherwise it runs them, and `--post` posts the
   result.
3. **`setup`** (each machine) checks the Polaris checkout against the
   manifest, reuses a matching baseline run if it finds one, and otherwise
   builds and sets one up.  A baseline with its own Polaris commit is found
   or set up from a second checkout, given by its load script with
   `--baseline-load-script`.  It then builds and sets up the PR suite, and
   prepares the CTests.  It prints the three jobs, or submits them with
   `--submit`.
4. **`report`** (each machine) writes the row's comment: a generated
   summary, the files Polaris and CTest wrote pasted unchanged, with the
   commits of Polaris and both Omega builds, and the compiler warnings the
   PR build has that the baseline build does not.  `--post` posts it.
5. **`post`** (your computer) posts a comment that `report` wrote on a
   machine without `gh`, once it is copied over unchanged.
6. **`status`** lists which rows have been reported and whether they are
   for the PR's current head.  Given the test branch, it lists the rows to
   test from each machine.

## Setup

On your own computer:

- A Polaris checkout with a load script (`./deploy.py`), a clone of
  E3SM-Project/Omega, and `gh`, logged in.
- `~/.config/omega_pr_test.cfg`, copied from [example.cfg](example.cfg),
  with a `[machines]` line for each machine to test over ssh, which
  `status` shows.
- A host alias for each of those machines in `~/.ssh/config`, sharing one
  connection, for example:
  ```
  Host *
      ControlMaster auto
      ControlPath ~/.ssh/connections/%r@%h:%p
  ```
  Log in to each machine with `ssh` and leave the session open while the
  testing runs.  Closing it closes the connection, which interrupts any
  testing on that machine.  To keep the connection open after you log
  out, add `ControlPersist <time>` (such as `12h`), and close it with
  `ssh -O exit <host>` when you are done.

On each machine:

- A Polaris checkout, with a load script for each compiler
  (`./deploy.py`).  A PR that needs Polaris changes needs a second one at
  the baseline's Polaris commit.  Agents make these when they are missing.
- A clone of E3SM-Project/Omega.
- `~/.config/omega_pr_test.cfg`, copied from [example.cfg](example.cfg).
- `gh` only on a machine where an agent tests by itself and posts, such as
  Frontier.  Otherwise comments are posted by hand, and everything else
  reads GitHub without logging in.

Source the load script, then run
`./utils/omega/pr_testing/omega_pr_test.py <command> --help` for the
options.

## Example

```bash
# on your computer
omega_pr_test.py init --pr 553 --push
omega_pr_test.py lint --fork git@github.com:me/E3SM.git \
    --branch omega-pr-test/553-54456ec --post

# on each machine, or over ssh, with the row's load script sourced
omega_pr_test.py setup --fork git@github.com:me/E3SM.git \
    --branch omega-pr-test/553-54456ec --submit
# ...when the jobs finish
omega_pr_test.py report --fork git@github.com:me/E3SM.git \
    --branch omega-pr-test/553-54456ec

# on your computer, after copying report.md from the machine
omega_pr_test.py post --pr 553 \
    <work_base>/pr553-54456ec/chrysalis_intel/report.md

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
