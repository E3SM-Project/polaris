# Testing a Polaris version update: instructions for agents

These instructions are for an agent that a developer (the *requester*) has
asked to test a Polaris pull request that updates Polaris to a new version
and its Spack environments, such as E3SM-Project/polaris#835, with this
utility.  Read the Polaris `AGENTS.md` at the root of this checkout as well;
it still applies.

The workflow is that of the Omega PR testing utility, so these sections of
[its AGENTS.md](../omega/pr_testing/AGENTS.md) apply here as they are:
Rules, Before you start, Running commands on a machine, Testing on a
machine itself and When something fails.  Read them first.  Where they say
`omega_pr_test.py`, use this utility's script, and where they say the
Omega PR, read the Polaris PR.  This file gives what is different.

Below, `polaris_update_test.py` means
`./utils/polaris_update_testing/polaris_update_test.py`.

## What is different

- **Rows.** The rows are every machine, compiler and MPI library the PR's
  `docs/developers_guide/supported_machines.yaml` lists, for MPAS-Ocean
  (`mpaso_pr`) and for Omega (the CTests and `omega_pr`).  A load script
  can test two rows, one for each model.
- **The fork** is the requester's Polaris fork, `polaris_fork` in the
  settings.
- **There is no lint step.**  Polaris's own CI checks the PR.
- **Deploying is outward-facing.**  `deploy --run` builds Spack
  environments.  Without `--spack-path`, it builds the shared environments
  that every Polaris user on the machine loads.  Ask the requester before
  each machine's `deploy --run`, and say which kind you will deploy.
- **Each report is for one kind of Spack environment**, shared or test,
  which `setup` and `report` read from the loaded load script.

## The PR's mache

A version update often moves to a new mache.  If the requester asks you
to make that change in the PR's branch, follow
[Updating Polaris to a new mache](../../docs/developers_guide/updating_spack/testing/updating_mache.md#updating-polaris-to-a-new-mache).
The steps are:

1. In the PR's branch, run
   `./deploy.py --bootstrap-only --mache-version <version>`.
2. Do what it prints: `pixi shell -m deploy_tmp/bootstrap_pixi/pixi.toml`,
   then `mache deploy update --software polaris --mache-version <version>`
   in that shell, then `exit`.  This replaces the files mache owns,
   `deploy.py` and `deploy/cli_spec.json`.
3. Set `mache` under `[pixi]` in `deploy/pins.cfg` to the new version, and
   update the other pins the PR changes.  `./deploy.py` refuses to run if
   the pin and `deploy/cli_spec.json` name different versions of mache.
4. Read the release notes and PRs of each mache release since the old
   pin, for what that page's step 5 lists, and tell the requester what
   you find, above all caveats and changes that need Spack environments
   rebuilt.
5. Show the requester the diff before committing it.

If the mache the PR needs has a tag but is not on conda-forge yet, wait
for the conda-forge package, or test with its branch, as below.

### An unreleased mache

To deploy test environments with a mache branch that is not released yet,
the requester names its fork and branch.  Add them to `deploy`:

```bash
polaris_update_test.py deploy --fork <fork> --branch <branch> \
    --spack-path <test path on scratch> \
    --mache-fork <org>/mache --mache-branch <mache branch>
```

`./deploy.py` installs mache from a clone of the branch.  The report then
says the mache came "from a branch".  In the notes, name the fork and
branch, and the commit if the requester gave one.  Deploy the shared
environments only with a released mache, unless the requester says
otherwise.

## Initiator

1. Pin what to test:
   ```bash
   polaris_update_test.py init --pr <number> --baseline main
   ```
   Leave off `--baseline main` only if the requester asks for no
   baseline.  The baseline is the current `main` of E3SM-Project/polaris,
   run with its own shared environments.  If the Omega the PR pins needs
   a fix still in review on some machine, the requester may ask for
   `--merge-omega-pr <number>`.  The merge is pushed to their E3SM fork
   (`fork` in the settings), and every machine's Omega rows build it.
2. Show the requester the summary.  With permission, run the push command
   that `init` printed.
3. List each machine's rows, with its ssh host and Polaris checkout:
   ```bash
   polaris_update_test.py status --pr <number> --fork <fork> --branch <branch>
   ```
   For a machine with no `[machines]` line, such as Frontier, give the
   requester the prompt `init` printed for an agent there, as it is (see
   [Handoff](#handoff)).  Test the other rows yourself over ssh.

## Before testing on a machine

1. Work in a checkout of the PR's branch on the machine, which you can
   fetch as `refs/pull/<number>/head` from E3SM-Project/polaris.  Make it
   yourself, never using an existing checkout of the PR's branch, where
   someone may be developing.  Make it as a worktree beside the checkout
   on the `[machines]` line, on a throw-away branch named
   `polaris-pr-test/<number>`, at the PR's head.  It is yours to update or
   remove.  If it does not have this utility yet, merge the branch you
   have the utility from into the throw-away branch.  Never commit to the
   PR's own branch, and never push the throw-away branch.
2. With a baseline, you need the checkout of `main` that `polaris_main`
   names in the machine's settings, at the `main` that `init` pinned, with
   a load script for each of the machine's compilers that uses `main`'s
   shared environments.  Fast-forward it if it is behind, and run
   `./deploy.py --compiler ...` there, with no Spack flags, if a load
   script is missing.
3. Check `~/.config/polaris_pr_test.cfg` on the machine as the Omega
   utility's AGENTS.md says, including that `omega_repo` is on the same
   filesystem as `work_base`.
4. For MPAS-Ocean rows, the build initializes each checkout's
   E3SM-Project submodule, and git keeps that clone, a gigabyte or more,
   in the Polaris clone the checkout belongs to.  So the PR's checkout and
   the one in `polaris_main` must belong to a Polaris clone on the same
   filesystem as `work_base` (scratch), not one in the home directory, or
   `setup` refuses.  A checkout whose submodule is already initialized is
   fine where it is.  If one is not, make the checkouts from a clone of
   E3SM-Project/polaris beside `work_base`, and tell the requester.

## Deploying

The requester tells you whether to deploy test environments, shared ones
or none, if they are already deployed.  The PR's checkout has no load
script yet, so source one from another checkout, such as the one on the
`[machines]` line; `deploy` runs `./deploy.py` in a clean login shell.  In
the PR's checkout, see what `deploy` would run:

```bash
polaris_update_test.py deploy --fork <fork> --branch <branch> \
    [--spack-path <test path on scratch>]
```

If the requester named a mache branch, add `--mache-fork` and
`--mache-branch` (see [An unreleased mache](#an-unreleased-mache)).  With
permission, run it again with `--run`, under `nohup`, with its output in a
log under the machine's `work_base`.  It takes hours.  On Perlmutter,
one `deploy` deploys pm-cpu and then pm-gpu.  When it finishes, it says
whether each row has a load script that uses the new environments.  If
one does not, tell the requester.

## Testing a machine's rows

Ask the requester up front for permission to submit, so that each row can
be submitted as soon as it is set up.

1. For each of the machine's compilers, in a clean shell with the PR
   checkout's load script for that compiler sourced:
   ```bash
   polaris_update_test.py setup --fork <fork> --branch <branch> --submit
   ```
   This sets up every row the load script tests, with its baseline from
   the checkout in `polaris_main`, using its load script for the same
   compiler, or for a compiler the PR renames, such as Aurora's
   `oneapi-ifx`, which becomes `intel`, its load script under the old
   name.  `--baseline-load-script` names another.  If `main` cannot run a
   row, ask the requester; with their permission, use
   `--no-baseline "<why>"` instead, a lowercase clause the report prints
   after "because".
   Add `--parallel` if the requester asks for it, which runs the suites'
   steps at the same time.
   The `setup`s for different compilers may run at the same time.
   MPAS-Ocean builds inside the checkout's E3SM-Project submodule, so a
   second MPAS-Ocean build waits for the first, and says so.
2. When all of the machine's jobs have finished, write its comment, in a
   shell with one of the PR checkout's load scripts sourced:
   ```bash
   polaris_update_test.py report --fork <fork> --branch <branch> \
       --agent "<name>"
   ```
   Then read it, add notes, copy it to the requester's computer and post
   it, as the Omega utility's AGENTS.md says under Testing a row.  Post it
   with `polaris_update_test.py post --pr <number> <file>`.

If a row cannot be run, add `--not-run "<reason>"` to `report`, which
reports the rows without results as not run.  Never use it for jobs that
are still running.  If none of a machine's rows can be run, report them
from the requester's computer, naming the kind of environment:

```bash
polaris_update_test.py report --fork <fork> --branch <branch> \
    --machine <machine> --spack shared --not-run "<reason>" \
    --agent "<name>"
```

## Handoff

The prompt `init` prints is the whole handoff for an agent on a machine
itself, such as Frontier.  It reads:

```
Test Polaris PR <number> from branch <branch> on <Polaris fork>, following
utils/polaris_update_testing/AGENTS.md.
```

With a baseline, it goes on:

```
The baseline runs from a second checkout of main on E3SM-Project/polaris.
```

The requester also tells that agent which kind of environment to deploy,
if any.

## When something fails

- **A deployment fails.**  Read its log, and see
  [Troubleshooting](../../docs/developers_guide/updating_spack/testing/troubleshooting.md).
  Tell the requester rather than deploying again with other options.
- **A row has no load script after deploying.**  Tell the requester.
- **Tasks differ from the baseline.**  The environments, the submodule
  updates and Polaris changes in the PR can each cause differences.  The
  report names the commits on both sides.  Say which tasks differ and what
  you think caused it.
- Otherwise, see the Omega utility's AGENTS.md.

`status --pr <number>` lists which rows have been reported, for each kind
of environment.
