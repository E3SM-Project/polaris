# Polaris version update testing utility

This utility runs the testing a Polaris version update asks for, such as
E3SM-Project/polaris#835: it deploys the Spack environments, and runs the
MPAS-Ocean `mpaso_pr` suite and the Omega CTests and `omega_pr` suite on
each supported machine, compiler and MPI library.  It reports each
machine's rows in one `Testing` comment on the Polaris PR, for the test
Spack environments and then for the shared ones.  It can be driven by a
developer or by AI agents, who follow [AGENTS.md](AGENTS.md).  The design
is in `docs/design_docs/polaris_update_testing.md`.

It works like the [Omega PR testing utility](../omega/pr_testing/README.md)
and shares its settings, its setup on your own computer and on each
machine, and its code in [utils/pr_testing](../pr_testing).

## How it works

1. **`init`** (your computer) pins the PR's head, its Omega and E3SM
   submodules and its rows in a manifest, committed on top of the head in
   a branch on your Polaris fork.  With `--baseline main`, it pins the
   current `main` of E3SM-Project/polaris as the baseline.
2. **`deploy`** (each machine) shows the `./deploy.py --deploy-spack`
   command for the machine's compilers and MPI libraries, with
   `--spack-path` for test environments.  `--run` runs it.  Either way, it
   checks that each row has a load script that uses the environments.
3. **`setup`** (each machine, once per compiler) checks the checkout and
   the loaded load script against the manifest, finds or sets up the
   baseline from a checkout of `main`, and sets up the PR suites and
   CTests for the rows the load script tests.  `--submit` submits the
   jobs.
4. **`report`** (each machine) writes one comment for the machine's rows
   with the loaded kind of Spack environment.  `--post` posts it.
5. **`post`** (your computer) posts a comment that `report` wrote on a
   machine without `gh`.
6. **`status`** lists which rows have been reported, for each kind of
   environment.

## Example

```bash
# on your computer
polaris_update_test.py init --pr 835 --baseline main --push

# on each machine, or over ssh, in a checkout of the PR
polaris_update_test.py deploy --fork git@github.com:me/polaris.git \
    --branch polaris-update-test/835-6db39cb --run
# ...then, with each compiler's load script sourced
polaris_update_test.py setup --fork git@github.com:me/polaris.git \
    --branch polaris-update-test/835-6db39cb \
    --baseline-load-script <main checkout>/load_polaris_<...>.sh --submit
# ...when all of the machine's jobs finish
polaris_update_test.py report --fork git@github.com:me/polaris.git \
    --branch polaris-update-test/835-6db39cb

polaris_update_test.py status --pr 835
```

## Layout

```
<work_base>/
  omega/<sha12>/                  Omega worktrees, shared with Omega PRs
  baselines/                      baselines, reused across PRs
  polaris-pr<N>-<head sha7>/
    deploy_<machine>.log
    shared/  test/                one for each kind of Spack environment
      report_<machine>.md         a machine's comment
      <machine>_<compiler>_<model>/
        build/  <suite>/  ctest/  setup.json
```

The test branch, `polaris-update-test/<N>-<head sha7>`, can be deleted
from your fork once the PR merges.
