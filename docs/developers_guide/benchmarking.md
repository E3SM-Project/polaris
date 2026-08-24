(dev-benchmarking)=

# Benchmarking a branch against a baseline

Polaris can compare a run against a baseline work directory with the `-b`
flag (see {ref}`dev-validation`).  Doing that by hand means resolving two
source trees, initializing submodules, sourcing the right load script,
setting up and building each side, and finally wiring the baseline work
directory into the test setup.  The driver in `utils/benchmark` automates
that bookkeeping so that the only thing left to do is interpret polaris'
own validation output.

The driver is designed to be run either by a developer or by an AI coding
agent.  Every run is recorded in a `manifest.json` with the resolved commit
hashes of polaris and of each submodule, so a benchmark can be reproduced
later.

## Concepts

A benchmark has two *sides*:

- the **baseline**, which is usually a released or `main` state, and
- the **test**, which is the branch under evaluation.

Each side is resolved with one of two `source` modes:

| `source` | Behavior |
| --- | --- |
| `worktree` (default) | Resolve a fork and ref to a commit, create a detached `git worktree` under `work_base`, initialize submodules, and optionally override the fork/ref of a single submodule. |
| `existing` | Adopt a polaris worktree that already exists, exactly as it is found. |

The driver never runs `fetch`, `checkout`, `submodule update`, `reset` or
`clean` against an adopted worktree.  If a required submodule is not
initialized, the driver stops and prints the command for the developer to
run.  This makes it cheap to benchmark the branch you are already working
in without a second copy.

Polaris' own build is a separate matter.  It builds only when asked
(`--rebuild` or `--clean-build`); `[build] build` defaults to `False`.
When it does build, it builds the component from `--branch`, which for
MPAS-Ocean is an in-source `make` in the branch directory, and both build
templates run `git submodule update --init --recursive` there.  An adopted
worktree is therefore built in place rather than left untouched whenever a
build is requested.

Because the `[baseline]` and `[test]` sections take exactly the same
options, the same driver benchmarks a polaris change, an Omega change or
an E3SM change; the only difference is which refs differ between the two
sides.

## Quick start

1. Copy the example config to the root of a polaris branch:

   ```bash
   cp utils/benchmark/example.cfg benchmark.cfg
   ```

2. Edit `benchmark.cfg` to set `work_base`, `load_script`, `setup_command`
   and the `[baseline]` and `[test]` sections.  A `polaris setup` command
   has to name its suite with `--suite_name`, since polaris would
   otherwise call it `custom`.

3. Resolve the plan without building anything:

   ```bash
   ./utils/benchmark/benchmark.py -f benchmark.cfg --dry-run
   ```

4. When the plan looks right, run it:

   ```bash
   ./utils/benchmark/benchmark.py -f benchmark.cfg
   ```

Always start with `--dry-run`.  It resolves every commit hash, applies
every guardrail and prints the exact commands.  It creates no worktrees
and builds and runs nothing, but resolving a fork does add a remote to
`primary_path` and fetch into it.

Every fork and ref can also be given on the command line, which is
convenient for scripted or agent-driven use:

```bash
./utils/benchmark/benchmark.py -f benchmark.cfg \
    --test-polaris-fork cbegeman \
    --test-polaris-ref add-surface-forcing-to-vmix
```

Full option tables are in `utils/benchmark/README.md`.

## Before your first run

Four things have to be true of the source trees before the driver will do
anything, and none of them are done for you.  Each is a guardrail below,
but settling them up front is quicker than meeting them one dry run at a
time:

1. **A load script exists.**  `load_*.sh` is git-ignored and written by
   `./deploy.py`, which is always a developer action.  Run it once in
   each worktree, or set `load_script` to the absolute path of one
   existing script so that a single deployment serves both sides.
2. **`model` matches what the suite runs.**  `model = none` needs no
   submodule and no build; see the note under Guardrails on how to tell.
3. **The submodule the model is built from is initialized**, on the side
   that builds — both sides normally, the baseline only when a
   `component_path` is shared:
   `git -C <worktree> submodule update --init e3sm_submodules/Omega`.
4. **Adopted worktrees have nothing uncommitted.**  Notes and scratch
   files at the root are fine and are simply recorded, but an uncommitted
   change to a tracked file, or an untracked file inside `polaris`, stops
   the run.  Commit it, move it aside, or decide up front to pass
   `--allow-dirty`.

## Guardrails

The driver refuses to run, *before* anything is built, if:

- the two sides resolve to the same worktree or to identical commits
  everywhere, so there would be nothing to compare;
- they differ in more than one of polaris, Omega and E3SM, so a
  difference could not be attributed to a single change
  (`--allow-multiple-changes`);
- they use different load scripts, implying a different machine, compiler
  or MPI library (`--allow-env-mismatch`);
- they use different `model` values (`mpas-ocean`, `omega` or `none`);
- an adopted worktree has changes that are not in a commit, so the run
  could not be reproduced from the recorded hashes (`--allow-dirty`, which
  records the run as `reproducible: false` and never caches its baseline).
  An untracked file outside the `polaris` package does *not* count: notes,
  plan documents and scratch output at the root of a worktree in use are
  never imported, registered or read by a task, so they are listed and
  recorded as `untracked` while the run stays reproducible and caches its
  baseline as usual.  Inside `polaris` an untracked file does count, since
  a new module is importable and a new task directory is discovered
  without any tracked file changing.  A submodule built in place does
  *not* count; edited source in the submodule the model is built from, or
  a submodule checked out at a commit other than the pinned one, does.  Untracked files in that
  submodule are ignored only for `mpas-ocean`, whose in-source `make`
  leaves them behind, and not for the out-of-source Omega build;
- an adopted worktree is missing the submodule needed for `model`, or its
  load script does not exist.  Creating the environment with `./deploy.py`
  is always a developer action.  A task or suite that runs no model
  (anything under `e3sm/init`, `mesh` or `seaice`, and some `ocean` tasks)
  should use `model = none`, which builds nothing and so needs no
  submodule on either side.

Each override makes the result harder to interpret, so it should be used
deliberately and noted when reporting results.

To tell which `model` a suite needs, read its tasks rather than its name.
`e3sm/init`, `mesh` and `seaice` never run a model; within `ocean`, what
decides it is whether any step is an `OceanModelStep`, which is what
`Ocean.configure()` tests before it goes looking for a build.  The suite
file `polaris/suites/ocean/<suite>.txt` lists one task path per line, and
`grep -rl OceanModelStep polaris/tasks/ocean/<task>` answers the question
for each of them.  Getting it wrong is loud rather than silent: a
`model = none` benchmark of a suite that does run the model stops during
`polaris setup`, unable to detect an ocean model.

## Output layout

```
<work_base>/
  worktrees/<ref>-<sha7>/            provisioned polaris worktrees
  baselines/<suite>_<model>_opts-<key>_polaris-<sha7>[_<repo>-<sha7>]/
                                     reusable baseline work dirs
  runs/<date>-polaris-<base sha7>-<test sha7>[-<repo>-<sha7>-<sha7>]/
                                     one benchmark run
    benchmark.log
    manifest.json
    polaris_benchmark.cfg            written only when wall_time is set
    build_baseline/  build_test/
    test/
```

Polaris' job scripts default to a one-hour wall-clock time, which many
tasks and most suites outgrow.  Set `wall_time` in the `[benchmark]`
section to change it for both sides at once; the driver merges it with
`polaris_config_file` into `polaris_benchmark.cfg` in the run directory,
because `polaris setup` takes only one config file.

A baseline work directory is keyed on the suite, the model, the polaris
commit, the commit of the submodule the model is built from, and a short
`opts-<key>` hashed from the setup command, the polaris config file and
the load script.  Every hash is labelled, so the directory reads without
knowing the order.

A submodule that is never built cannot change the results, so its hash is
left out; with `model = none` the polaris commit is the only one.  The
manifest still records every hash, and the one-variable guardrail still
compares all of them.

A baseline is marked complete when it finishes, and a later benchmark with
the same name **reuses** it instead of rerunning, which is what makes
iterating on a test branch cheap.

## Sharing one build between the two sides

Each side is given `build_baseline` or `build_test` inside the run
directory as its `-p`, so it builds its own copy of the model.  When only
polaris differs between the two sides, that builds the same Omega or
MPAS-Ocean source twice.  Setting `component_path` in the `[benchmark]`
section points both sides at one directory:

```ini
[benchmark]
component_path = ${work_base}/build_omega
```

Polaris builds the model only when it does not already find one at `-p`,
so the side that is set up first builds it there and the other finds it
and skips.  No build flag is needed.

That side is the baseline, so `--branch` points at the baseline's
submodule for both sides.  The test side is never built from, and so does
not need the submodule initialized at all: a provisioned test worktree
skips cloning it, and an adopted one is not asked for it.

The driver refuses a `component_path` when the two sides pin different
commits of the submodule the model is built from, since one side would
then run the other's model, and it refuses `--clean-build`, which would
delete a directory the benchmark does not own.  The path is part of the
key the cached baseline is named from, but what was built there is the
developer's to keep in step with the recorded hashes.

Validation results themselves are written by polaris under `case_outputs/`
in the test work directory; collecting and reporting them is deliberately
not part of the driver.

## Why this matters for agent-driven workflows

Orchestrating a baseline comparison by hand is dominated by the *number of
tool calls* an agent has to make and by the size of the output each one
returns — build logs in particular.  Because an agent resends its
accumulated context on every turn, that cost grows roughly quadratically
with the number of steps.

Consolidating the whole workflow into a single, guardrailed driver replaces
roughly twenty exploratory shell turns with a `--dry-run` and a run, and
replaces raw build-log output with a compact resolved plan and a
`manifest.json`.  In the estimate recorded with this driver, that reduces
the cumulative context of a single baseline comparison by close to an order
of magnitude, and it removes the retry loops that dominate the cost when a
build or setup step fails.

The agent-facing rules live in `.github/instructions/benchmark.instructions.md`
and apply automatically to work under `utils/benchmark`.

## Example prompts for an AI agent

The driver is meant to be handed to an agent as a *single* tool, rather
than having the agent reinvent the git and build steps.  The prompts below
are examples that work well in practice.  In each case the agent should
come back with the resolved commit hashes from `--dry-run` and wait for
your approval before running for real.

### Benchmark the branch you are working in

The most common case: you have a branch checked out with a working build,
and you want to compare it to `main`.

> Benchmark my current worktree against `E3SM-Project/main` using
> `utils/benchmark`.  Adopt this worktree as the test side with
> `--test-existing` so my existing build is reused, and provision the
> baseline from `main`.  Use the `ocean/single_column` suite with
> `--model omega`.  Run `--dry-run` first and show me the resolved
> hashes before running for real.

### Compare two polaris branches

> Set up a benchmark config in `utils/benchmark` that compares
> `E3SM-Project/main` as the baseline against `cbegeman/add-surface-forcing-to-vmix`
> as the test side, for the `ocean/single_column/vmix` task on Chrysalis
> with GNU.  Start from `example.cfg`, don't hard-code paths, and show me
> the `--dry-run` plan.

### Benchmark an Omega submodule change

Here polaris is held fixed on both sides and only the Omega submodule
differs, which is exactly what the "only one repository may differ"
guardrail is designed to enforce:

> Using `utils/benchmark`, benchmark an Omega change: keep `polaris_ref`
> the same on both sides and override only the test side's Omega with
> `--test-omega-fork cbegeman --test-omega-ref my-omega-feature`.  Confirm
> from the dry run that polaris and the other submodules resolve to
> identical hashes.

### Iterate after pushing a fix

Because a completed baseline is keyed on the commit hashes and reused, the
follow-up run only builds and runs the test side:

> I pushed a fix to `cbegeman/add-surface-forcing-to-vmix`.  Re-run the
> same benchmark with `--rebuild` on the test side and tell me whether the
> baseline work directory was reused or rebuilt.

### Interpret the results

> The benchmark finished.  Read `manifest.json` and the validation output
> under `case_outputs/` in the test work directory, and summarize which
> variables differ from the baseline and by how much.  Include the
> baseline and test commit hashes in the summary.

### Diagnose a failure

> The benchmark failed.  Report the failing step and the path to its log,
> show me the last 50 lines, and stop — don't retry with different flags.
