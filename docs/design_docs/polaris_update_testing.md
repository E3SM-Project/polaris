# Polaris Version Update Testing

date: 2026/10/14

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

A pull request that updates Polaris to a new version, such as #664 or #835,
usually changes the Spack environments and often the submodules. Its
checklist asks for the MPAS-Ocean `mpaso_pr` suite, and for the Omega
CTests and `omega_pr` suite, on every supported machine, compiler and MPI
library. The checklist is run twice: first with test Spack environments,
then with the shared environments deployed for the new version.

This design adds `utils/polaris_update_testing`, a utility for that
testing. It reuses the code in `utils/pr_testing` that the Omega PR testing
utility shares (see {doc}`omega_pr_testing`). The new parts are the rows,
the step that deploys Spack environments, and reports on the Polaris pull
request.

Success means that #835's deployment can be tested and reported with the
utility, and that a reviewer can tick each box of its checklist from the
`Testing` comments alone.

## Requirements

### Requirement: Every supported row is tested.

The rows are every machine, compiler and MPI library that the new version
supports, for MPAS-Ocean and for Omega.

### Requirement: Each report says which Spack environments it tested.

A report says whether it tested test environments or the shared ones, and
where they are.

### Requirement: The requester controls deploying Spack environments.

Deploying shared environments changes what every Polaris user on a machine
loads.

### Requirement: A baseline is optional.

When there is one, it is the previous version, from Polaris `main`, with
its shared environments.

### Requirement: Each machine's results are reported in one comment.

### Requirement: Progress across machines is visible.

The requester can see which rows have results with each kind of
environment, which were not run and why, and which results are for a
commit that is no longer the pull request's head.

### Requirement: Commits, provenance and permissions are handled as for Omega pull requests.

The requirements of {doc}`omega_pr_testing` hold, except those about
linting and the Omega pull request template: every machine tests the same
commits, each report carries its own provenance, results are reported as
Polaris and CTest write them, the requester controls every outward-facing
action, testers do not tick the checklist, and a matching baseline is
reused wherever it was run.

## Algorithm Design

### Algorithm Design: Every supported row is tested.

The rows come from `docs/developers_guide/supported_machines.yaml` at the
pull request's head. Each row is a machine, compiler, MPI library and
model. An MPAS-Ocean row runs `mpaso_pr`. An Omega row runs the CTests and
`omega_pr`. A machine and compiler that support both models give two rows.

Omega is built from the pull request's `e3sm_submodules/Omega` pin, in the
Omega worktrees the Omega utility makes. MPAS-Ocean is built from the
`e3sm_submodules/E3SM-Project` submodule of the Polaris checkout.
MPAS-Ocean builds inside its source tree, so the rows that share a tree
build one at a time (see [Decisions](#decisions)).

### Algorithm Design: Each report says which Spack environments it tested.

The environments are read from each row's load script, not set by the
requester. A load script whose Spack environment is under the machine's
`[deploy] spack` path uses the shared environments. Any other uses test
environments. The comment's heading names the kind, and the report gives
the path, the Polaris version and the mache version.

> **Rationale:** The report states what was loaded, so it cannot claim the
> shared environments when a test deployment was sourced by mistake. #835
> starts with the shared environments, since its test environments were
> already tested by hand.

### Algorithm Design: The requester controls deploying Spack environments.

`deploy` prints the `./deploy.py --deploy-spack` command for a machine. It
deploys the compilers and MPI libraries of the machine's supported rows at
the pull request's head. With a test path, it adds
`--spack-path`. On Perlmutter, pm-cpu and pm-gpu each get their own
command. Only with `--run` does `deploy` run the command, under `nohup`,
with its output in a log. Afterward, `deploy` checks that each of the
machine's rows has a load script in the checkout, and that the script
uses the environment just deployed.

### Algorithm Design: A baseline is optional.

`init --baseline main` pins the current `main` of E3SM-Project/polaris as
the baseline. The baseline runs from a second Polaris checkout that
contains that commit and not the pull request's head. It uses that
checkout's load scripts, and so the previous version's shared
environments. Omega and MPAS-Ocean come from that checkout's submodule
pins.

A row whose compiler the pull request renames uses the former name for the
baseline, as in the Omega utility. A row the previous version does not
support runs without a baseline, and its report says so.

Baseline differences can come from the environments, from the submodule
updates or from Polaris changes in the pull request. Each report names
the commits on both sides, so the tester can tell which changed.

### Algorithm Design: Each machine's results are reported in one comment.

Each machine gets one comment for each kind of environment, on the Polaris
pull request. Perlmutter's pm-cpu and pm-gpu rows share one, as in the
Omega utility. A table has a line for each row. Below it, each row has a
collapsed block with the files Polaris and CTest wrote, pasted unchanged.

### Algorithm Design: Progress across machines is visible.

Each comment's marker, prefixed `polaris-update-test`, lists its rows and
the kind of environment. `status` lists each row once for each kind of
environment, with its latest result.

### Algorithm Design: Commits, provenance and permissions are handled as for Omega pull requests.

`init` pins the pull request's head, its Omega and E3SM-Project pins and
the rows in a manifest. The manifest is committed on top of the head, in a
branch on the requester's Polaris fork. Testers fetch that branch. Their
Polaris checkout must contain the head, with this utility merged in
locally if the head does not have it.

The outward-facing steps are `init --push`, `deploy --run`,
`setup --submit` and `post`. Each needs the requester's permission in the
agent's session, as in the Omega utility. `report` only writes its comment,
and `post` posts it once someone has read it.

## Implementation

### Implementation: Every supported row is tested.

The shared `Row` gains an optional `model`, which the Omega utility leaves
out. `pr_test_setup` builds MPAS-Ocean as well as Omega:

- `polaris_suite()` already takes the suite and model. For MPAS-Ocean it
  passes no `--branch`, so the build uses the checkout's submodule.
- A lock on the E3SM-Project submodule, like the lock on an Omega
  worktree, makes rows build one at a time.
- A finished MPAS-Ocean build is recognized by its `ocean_model`.
- `BaselineCriteria.build_type` may be `None`, since MPAS-Ocean's
  provenance has no build type.

Only Omega rows set up CTests and compare build warnings.

```
polaris_update_test.py init --pr 835 [--baseline main] [--rows ...]
                            [--merge-omega-pr <number>]...
                            [--notes <text>] [--push]
```

`--merge-omega-pr` merges an Omega pull request, such as a build fix still
in review, into the Omega the pull request pins. The merge is pushed to the
requester's E3SM fork, recorded in the manifest's `omega_merge`, and built
by every Omega row in place of the pin. Checkouts are still checked against
the pin.

The manifest, `polaris_update_test.yaml`:

```yaml
schema_version: 1
requester: <GitHub user>
pull_request: 835
pr_head: <sha>
polaris_version: 1.2.0-alpha.1
omega_commit: <sha>
e3sm_commit: <sha>
omega_merge:            # or null
  commit: <sha>         # built in place of omega_commit
  pull_requests: [{pull_request: 600, commit: <sha>}]
  fork: <the requester's E3SM fork>
  branch: polaris-update-test/835-<sha7>-omega
baseline:               # or null
  polaris_commit: <sha>
  polaris_version: 1.1.0-alpha.7
  omega_commit: <sha>
  e3sm_commit: <sha>
rows:
  - {machine: chrysalis, compiler: gnu, mpi: openmpi, model: mpas-ocean}
  - {machine: chrysalis, compiler: gnu, mpi: openmpi, model: omega}
notes: <free text for the requester>
```

### Implementation: Each report says which Spack environments it tested.

`setup` reads the Spack environment from the loaded load script and
compares it with the machine's `[deploy] spack` path. It records the kind
of environment, `shared` or `test`, with the path and the versions, in
the row's `setup.json`. Row directories are kept apart by kind:

```
<work_base>/polaris-pr<N>-<head sha7>/<shared|test>/
    report_<machine>.md
    <machine>_<compiler>_<model>/
        build/  <suite>/  ctest/  setup.json
```

### Implementation: The requester controls deploying Spack environments.

```
polaris_update_test.py deploy --fork <fork> --branch <branch>
                              [--machine <machine>] [--spack-path <path>]
                              [--recreate] [--run]
```

The compilers and MPI libraries come from the rows in
`supported_machines.yaml` at the pull request's head, all of them, even if
the manifest tests only some. `AGENTS.md` tells an agent to ask before
`--run` on each machine, and to say whether it deploys test or shared
environments. With permission, `deploy --run` deploys the shared
environments as well as test ones (see [Decisions](#decisions)).

### Implementation: A baseline is optional.

```
polaris_update_test.py setup --fork <fork> --branch <branch> [--submit]
                             [--baseline-load-script <script>]
                             [--no-baseline <reason>]
```

`setup` sets up every row the loaded load script tests.
`--baseline-load-script` names the load script for the same compiler in
the baseline checkout, as in the Omega utility. `setup` checks that the
checkout contains the manifest's baseline commit and pins its Omega and
E3SM-Project commits. The baseline is found or set up with the shared
`get_baseline()`, so an Omega baseline that the Omega utility ran from the
same `main` is reused.

### Implementation: Each machine's results are reported in one comment.

```
polaris_update_test.py report [--machine <machine>] [--spack <kind>]
                              [--notes <file>] [--not-run <reason>]
                              [--agent <name>]
```

```markdown
## Testing on chrysalis with the shared Spack environments
<!-- polaris-update-test {...} -->

Tested E3SM-Project/polaris#835 (`<sha>`), Polaris 1.2.0-alpha.1 with
mache 5.0.0, Omega `<sha>` and E3SM `<sha>`, with the shared Spack
environments in `<path>`. The baseline is `<sha>`, Polaris 1.1.0-alpha.7,
Omega `<sha>` and E3SM `<sha>`, with its shared Spack environments, so
differences can come from any of these.

| Row | Suite | CTests | New build warnings |
|---|---|---|---|
| chrysalis, gnu, openmpi (MPAS-Ocean) | `mpaso_pr`: 24 of 24 passed | | |
| chrysalis, intel, openmpi (Omega) | `omega_pr`: 29 of 29 passed | 59 of 59 passed | 0 |
| chrysalis, gnu, openmpi (Omega) | `omega_pr`: 29 of 29 passed | 59 of 59 passed | 0 |

<details>...</details>
```

The comment uses the shared `format_rows()`, `assemble()` and
`deliver()`, with `E3SM-Project/polaris` as the repository.

### Implementation: Progress across machines is visible.

```
polaris_update_test.py status --pr 835 [--fork <fork> --branch <branch>]
```

`status` uses the shared `get_row_entries()` and `format_status()`. A row
is named `<machine>/<compiler>/<model>/<shared|test>`.

### Implementation: Commits, provenance and permissions are handled as for Omega pull requests.

`utils/polaris_update_testing/` holds `AGENTS.md`, `README.md`,
`polaris_update_test.py` and its `polaris_update_*.py` modules. `AGENTS.md`
links to the Omega utility's `AGENTS.md` for the rules and the ssh steps
the two share, rather than repeating them. The settings come from
`~/.config/polaris_pr_test.cfg`, the Omega utility's file, so the two
share `work_base`, its Omega worktrees and its baselines.

## Testing

### Testing and Validation: Every supported row is tested.

Unit tests read the rows from a fixture `supported_machines.yaml`, and set
up an MPAS-Ocean row with a stand-in for `polaris suite`. They check that
two MPAS-Ocean rows from one tree wait on its lock.

### Testing and Validation: Each report says which Spack environments it tested.

Unit tests read fixture load scripts with a Spack environment under the
shared path and under a test path.

### Testing and Validation: The requester controls deploying Spack environments.

Unit tests build the `deploy` command from fixture machine configs,
including Perlmutter's two, and check that nothing runs without `--run`.

### Testing and Validation: A baseline is optional.

Unit tests set up a row with and without a baseline, and with a baseline
load script that uses a compiler's former name.

### Testing and Validation: Each machine's results are reported in one comment.

Unit tests build a comment with MPAS-Ocean and Omega rows, and check that
the files appear byte for byte.

### Testing and Validation: Progress across machines is visible.

Unit tests parse markers for both kinds of environment.

### Testing and Validation: Commits, provenance and permissions are handled as for Omega pull requests.

The trial is #835's deployment, against a `main` baseline, on Chrysalis,
Perlmutter and Aurora over ssh and with an agent on Frontier.

## Decisions

- **A separate utility that shares code with the Omega one.** An update
  pull request is on another repository, has MPAS-Ocean rows, deploys
  Spack environments and needs no lint step. One command line for both
  would put two workflows in one `AGENTS.md`.
- **`deploy --run` does the deployment, shared environments included.**
  Handing the command back for the requester to run would defeat the
  utility. The requester's permission for each machine is what guards the
  shared environments.
- **The two utilities share one settings file**,
  `~/.config/polaris_pr_test.cfg`, which replaced the Omega utility's
  `~/.config/omega_pr_test.cfg`.
- **The pull request's head is tested, not a merge into `main`.**
  Deployment runs from the pull request's branch, and an update pull
  request is brought up to date with `main` before it merges.
- **The kind of environment is read from the load scripts**, so a report
  states what was loaded (see the algorithm design for each report saying
  which Spack environments it tested).
- **`deploy` covers only the compilers and MPI libraries of supported
  rows.** A machine's config can list combinations that are no longer
  supported, such as Frontier's `crayamd` in #835, or that do not build,
  such as pm-gpu's `intelgpu` (E3SM-Project/mache#526). The first trial
  deployed everything the config listed and stopped on both.
- **MPAS-Ocean builds in the checkout's submodule, one row at a time.**
  An E3SM worktree for each row would cost a large checkout for builds
  that take minutes.
- **New build warnings are compared for Omega rows only, at first.** The
  parser and build log names are Omega's. MPAS-Ocean can follow.
- **No lint step.** Polaris's own CI checks the pull request.
