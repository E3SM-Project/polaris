# Benchmarking a branch against a baseline

The `utils/benchmark` directory contains a driver that benchmarks a
**polaris**, **Omega** or **E3SM** branch against a baseline using a polaris
task or suite.  It is designed to be run either by a developer or by an AI
agent, and to produce a run that can be reproduced from the recorded commit
hashes.

The idea is simple:

1. Resolve two *sides* of the benchmark, a **baseline** and a **test**.
2. Set up the same task or suite for each.
3. Give the test side the baseline work directory with `-b`, so that
   polaris' own validation compares the two (see {ref}`dev-validation`).

Because the comparison is done by polaris itself, this driver only has to
get the source trees, the environment and the paths right.

## The two source modes

Each side is resolved in one of two ways:

| `source` | Behavior |
| --- | --- |
| `worktree` (default) | Resolve a fork and ref to a commit, create a detached `git worktree` under `work_base`, initialize submodules, and optionally check out a different fork/ref for one submodule. |
| `existing` | Adopt a polaris worktree that already exists, exactly as it is found. |

The **driver** never runs `fetch`, `checkout`, `submodule update`, `reset`
or `clean` against an adopted worktree.  If a required submodule is not
initialized, the driver stops and tells you the command to run yourself.
This lets you benchmark the branch you are already working in without a
second copy.

That is not the same as the worktree being left untouched, *if* a build is
requested.  Polaris builds the component from `--branch`, and for
MPAS-Ocean that is an in-source `make` in the branch directory; both build
templates also run `git submodule update --init --recursive` there.  So
`--rebuild` or `--clean-build` on an adopted worktree writes into it.
Without those flags, and always with `model = none`, nothing is built and
the worktree really is only read.

Both sections take exactly the same options, so *which* repository is being
benchmarked is just a matter of which refs differ between them.

## Quick start

1. Copy the example config to the root of a polaris branch:

   ```bash
   cp utils/benchmark/example.cfg benchmark.cfg
   ```

2. Edit `benchmark.cfg` to set `work_base`, `load_script`, `setup_command`
   and the `[baseline]` and `[test]` sections.

3. Resolve everything and see the plan without building anything:

   ```bash
   ./utils/benchmark/benchmark.py -f benchmark.cfg --dry-run
   ```

4. When the plan looks right, run it:

   ```bash
   ./utils/benchmark/benchmark.py -f benchmark.cfg
   ```

Always start with `--dry-run`.  It resolves every commit hash, applies every
guardrail and prints the exact commands.  It creates no worktrees and
builds and runs nothing, but resolving a fork does add a remote to
`primary_path` and fetch into it.

## Before your first run

Four things have to be true of the source trees before the driver will do
anything, and none of them are done for you.  Each is a guardrail below,
but they are quicker to settle up front than one dry run at a time:

1. **A load script exists.**  `load_*.sh` is git-ignored and is written
   by `./deploy.py`, which is a developer action.  Either run it once in
   each worktree, or set `load_script` to the *absolute* path of one
   existing script so that a single deployment serves both sides.
2. **`model` matches what the suite runs**, per
   [Choosing `model`](#choosing-model) below.  `model = none` needs no
   submodule and no build.
3. **The submodule the model is built from is initialized**, on the side
   that builds.  Without a `component_path` that is both sides:

   ```bash
   git -C <worktree> submodule update --init e3sm_submodules/Omega
   ```

   With a shared `component_path` it is the baseline only, and the test
   side needs nothing.
4. **Adopted worktrees have nothing uncommitted.**  Notes and scratch
   files at the root are fine and are simply recorded, but an uncommitted
   change to a tracked file, or an untracked file inside `polaris`, stops
   the run: the benchmark could not then be reproduced from the recorded
   hashes.  Commit it, move it aside, or decide up front to pass
   `--allow-dirty`.

## Configuration options

### `[benchmark]`

| Option | Description |
| --- | --- |
| `work_base` | Base directory for all benchmark output. |
| `primary_path` | The polaris clone worktrees are made from and forks are fetched into.  Defaults to the config file's directory.  Only ever fetched from. |
| `load_script` | Name of the load script to source within each worktree, or an absolute path to a single shared one. |
| `setup_command` | A `polaris setup` or `polaris suite` command.  A `polaris setup` command must name its suite with `--suite_name`. |
| `run_command` | Usually `polaris serial`; used when `submit = False`. |
| `submit` | Submit the job script instead of running in place. |
| `component_path` | Optional build directory shared by both sides, passed on with `-p`. |
| `wall_time` | Optional wall-clock time for both sides' job scripts. |
| `polaris_config_file` | Optional config file passed on with `-f`. |

Both of the last two shape what polaris is given with `-f`.  `wall_time`
sets `[job] wall_time`, which otherwise defaults to `1:00:00`; since
`polaris setup` takes a single config file, the driver merges it with
`polaris_config_file` into `polaris_benchmark.cfg` in the run directory
and passes that on.  A `wall_time` here wins over one in
`polaris_config_file`, and both sides always get the same file.

Changing `wall_time` does **not** invalidate a cached baseline, since it
cannot change results.  Changing `polaris_config_file` does.

Any environment variable can be substituted as `${NAME}` anywhere in the
config file.  A name that a config option already defines wins, and one
that is neither an option nor set in the environment is an error, so a
typo is reported rather than silently expanding to nothing.

`--model`, `--branch`, `-p`, `-w`, `-b`, `-f` and the build flags are
appended automatically and **must not** appear in `setup_command`; the
driver raises an error if they do.  `--model` and `--branch` are left off
entirely when `model = none`.

### The suite name identifies the benchmark

**The suite name is what makes one benchmark distinct from another.**  It
names the cached baseline directory, the run directory and the job script,
so two benchmarks with the same suite name are, as far as the driver is
concerned, the same benchmark:

```
baselines/<suite>_<model>_opts-<key>_polaris-<sha7>[_<repo>-<sha7>]/
runs/<date>-<suite>-polaris-<sha7>-<sha7>[-<repo>-<sha7>-<sha7>]/
job_script.<suite>.sh
```

Two benchmarks of the *same* pair of commits are therefore told apart by
their suite names.  Benchmarking one branch two ways — one suite that
runs the model and one task that does not, say — needs two different suite
names and nothing else.  The `opts-<key>` on the baseline is a hash of the
setup command, the config file, the load script and any shared
`component_path`.  It is not something you choose; it is there so that a
cached baseline is never reused by a benchmark it is not comparable with,
which is why it appears on the baseline and not on the run directory.

Where the name comes from depends on the command:

| command | the name is |
| --- | --- |
| `polaris suite` | the value of `-t`, e.g. `-t omega_pr` → `omega_pr` |
| `polaris setup` | the value of `--suite_name`, which is **required** |

`--suite_name` is the one flag the driver requires rather than forbids.
Polaris would otherwise call the suite `custom`, so every benchmark set up
that way would collide with every other.

### `[baseline]` and `[test]`

| Option | Description |
| --- | --- |
| `source` | `worktree` or `existing`. |
| `path` | The existing worktree, when `source = existing`. |
| `polaris_fork` | A GitHub owner (e.g. `E3SM-Project`) or a full remote URL. |
| `polaris_ref` | A branch, tag or commit hash. |
| `omega_fork`, `omega_ref` | Override the Omega submodule. |
| `e3sm_fork`, `e3sm_ref` | Override the E3SM-Project submodule. |
| `model` | The polaris `--model` value: `mpas-ocean` or `omega`, or `none` for a task or suite that runs no model. |

A fork given as a bare owner is expanded to a URL matching the style
(ssh or https) of the existing `origin` remote.  Fork and ref options are
forbidden when `source = existing`, since the checkout's own fork and ref
are *recorded* rather than requested.

Any submodule not given a ref stays at the hash pinned by `polaris_ref`.

### Choosing `model`

`model` says which component polaris builds, not which component the task
belongs to.  A `model` of `mpas-ocean` or `omega` means the driver passes
`--model` and `--branch` on to `polaris setup`, and requires the matching
submodule to be initialized on that side.

Many tasks build nothing at all: everything under `e3sm/init`, `mesh` and
`seaice` is pure Python, and so are some `ocean` tasks.  Use `model = none`
for those.  The driver then omits `--model` and `--branch`, and neither
side needs `e3sm_submodules/Omega` or `e3sm_submodules/E3SM-Project` to be
initialized.  `--clean-build` and `--rebuild` are refused, since there is
nothing to build.

Both sides must use the same `model`, `none` included.

#### Telling which one you need

The component usually settles it: `e3sm/init`, `mesh` and `seaice` run no
model, so those are always `none`.  Only `ocean` is mixed.

What decides it there is whether any step is an `OceanModelStep`, which is
what `Ocean.configure()` tests before it looks for a build.  So read the
tasks rather than the suite name: `polaris/suites/ocean/<suite>.txt` lists
one task path per line, and

```bash
grep -rl OceanModelStep polaris/tasks/ocean/<task>
```

says whether that task forward-runs the model.  A suite named for a PR or
nightly test almost certainly does; a task that only builds a mesh, remaps
a field or checks convergence against an analytic solution may well not.

Guessing wrong is cheap and loud, not silent.  `model = none` on a suite
that does run the model fails during `polaris setup` with *"Could not
detect ocean model; neither MPAS-Ocean nor Omega appear to be
available"*.  The opposite mistake costs a build that is never used, and
the driver asks for a submodule you did not need.

## Command-line overrides

Every fork and ref can be set on the command line, which is convenient for
scripted or agent-driven use:

```bash
./utils/benchmark/benchmark.py -f benchmark.cfg \
    --test-polaris-fork cbegeman \
    --test-polaris-ref add-surface-forcing-to-vmix

./utils/benchmark/benchmark.py -f benchmark.cfg \
    --test-omega-fork cbegeman --test-omega-ref my-omega-feature

./utils/benchmark/benchmark.py -f benchmark.cfg \
    --test-existing /path/to/my/polaris/worktree
```

For example prompts to hand to an AI agent, see the "Example prompts for an
AI agent" section of the developer's guide page on benchmarking
(`docs/developers_guide/benchmarking.md`).

## Guardrails

The driver refuses to run, before anything is built, if:

- The two sides resolve to the **same** worktree or to identical commits
  everywhere, so there would be nothing to compare.
- They differ in **more than one** of polaris, Omega and E3SM, so a
  difference could not be attributed to a single change.
  Override with `--allow-multiple-changes`.
- They use **different load scripts**, implying a different machine,
  compiler or MPI library.  Override with `--allow-env-mismatch`.
- They use different `model` values.
- An **adopted** worktree has changes that are not in a commit, since the
  run could not then be reproduced from the recorded hashes.  Override
  with `--allow-dirty`; the run is recorded as `reproducible: false`, its
  directory is prefixed with `dirty-`, and its baseline is never cached
  or reused.

An untracked file **outside** the `polaris` package does not count.  A
worktree in use normally carries notes, plan documents and scratch output
at its root, and nothing a task runs imports, registers or reads them, so
they cannot change a result.  They are listed in the summary and recorded
in the manifest as `untracked`, but the run stays reproducible, keeps its
undecorated directory name and caches its baseline as usual.

Inside `polaris` an untracked file *can* change a result: a new module is
importable and a new task directory is discovered, both without any
tracked file changing.  Those are dirty, as is any uncommitted change to
a tracked file anywhere.

`--allow-dirty` is about source that is not in a commit.  A submodule
built in place is not dirty: build products are regenerable from the
recorded hashes, and building in place is the normal state of a polaris
worktree.  A submodule checked out at a commit other than the pinned one
*is* dirty, as is edited source in the submodule the model is built from.

Untracked files in that submodule are ignored only for `mpas-ocean`,
whose in-source `make` leaves them behind.  Omega is built out of source,
so an untracked file there is source rather than a build product, and its
CMakeLists globs `*.cpp`, so a new one would be compiled in without any
tracked file changing.
- An adopted worktree is missing the submodule needed for `model`, or its
  load script does not exist.  Creating the environment with `./deploy.py`
  is a developer action and is never done for you.  A benchmark that
  builds nothing should use `model = none`, which needs no submodule.

## Output layout

```
<work_base>/
  worktrees/<ref>-<sha7>/            provisioned polaris worktrees
  baselines/<suite>_<model>_opts-<key>_polaris-<sha7>[_<repo>-<sha7>]/
                                     reusable baseline work dirs
  runs/<date>-<suite>-polaris-<base sha7>-<test sha7>[-<repo>-<sha7>-<sha7>]/
                                     one benchmark run
    benchmark.log
    manifest.json
    polaris_benchmark.cfg            written only when wall_time is set
    build_baseline/  build_test/
    test/
```

A run directory is keyed on the suite, so that two benchmarks of the
*same* pair of commits on the same day do not share one.  Every repository
that differs follows.  It carries no `opts-<key>`: that hash is there to
stop a *baseline* being reused when it is not comparable, and a run
directory is not a cache.

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

`manifest.json` records both sides in full — mode, path, fork, ref, commit
hashes, pinned versus actual submodule hashes, any overrides, the dirty
flag and the load script — along with the commands, the directories and
which repositories differ.

## Other flags

| Flag | Description |
| --- | --- |
| `--dry-run` | Resolve and print, but do not build or run. |
| `--clean-build` | Start from a clean build directory on both sides. |
| `--rebuild` | Force a build even if the component is already built. |

Neither flag is needed for a first build.  `[build] build` defaults to
`False` in `polaris/default.cfg` and the driver passes `--build` or
`--clean_build` only when one of these flags is given, but
`Ocean.configure()` turns the option on by itself whenever it does not
find the model at `-p`.  Use `--rebuild` to force a build over one that
is already there, and `--clean-build` to throw that one away first.

## Sharing one build between the two sides

By default `-p` is `build_baseline` or `build_test` inside the run
directory, so each side builds its own copy and a run on a new day builds
both again from scratch.

When only polaris differs, that is two builds of the same source.  Set
`component_path` in `[benchmark]` to a directory both sides should use
instead:

```ini
[benchmark]
component_path = ${work_base}/build_omega
```

Since polaris builds only what it cannot find at `-p`, the side that is
set up first builds the model there and the other one finds it and skips.
Nothing else has to be passed: no `--rebuild`, and no build flag at all.

The baseline is that side, so `--branch` points at the **baseline's**
submodule for both.  The test side is therefore never built from and does
not need `e3sm_submodules/Omega` or `e3sm_submodules/E3SM-Project`
initialized at all — a provisioned test worktree does not clone it, and
an adopted one is not asked for it.  That is usually several GB of source
that nothing would read.

The driver refuses a `component_path` when the two sides pin **different**
commits of the submodule the model is built from, since one side would
then run the other's model — with `submit = True` both sides are set up
before either runs, so whichever built last would win for both.  It also
refuses `--clean-build`, which would delete a directory the benchmark
does not own and then build it twice over; clean it yourself instead.

`component_path` is part of the key the cached baseline is named from, so
pointing it somewhere else starts a new baseline rather than reusing one
built against a different executable.  The driver cannot check what was
actually built there: the baseline directory names the submodule hash the
baseline *pins*, and keeping the build at that hash is yours to manage.

## Notes

- A baseline is reused when its work directory looks complete.  Two
  things can say so: the `.polaris_benchmark_complete` marker the driver
  writes when it ran polaris in place and saw it return, or the
  `<suite>_output_for_pr.md` that polaris writes at the end of its own
  run.  The second is what makes reuse work for `submit = True`, where
  the driver exits as soon as `sbatch` accepts the job and never learns
  the outcome.

  Polaris writes that file immediately before the pass/fail exit, so it
  means the run *finished*, not that it passed — which is the right test,
  for the same reason the test job depends on `afterany`.  Renaming or
  removing it in polaris would quietly stop baselines from being reused;
  it fails safe, since an unrecognized baseline is simply run again, but
  the driver says so when it re-runs a baseline directory that already
  exists, so the regression is visible rather than silent.
- When `submit = True`, the test job is submitted with
  `--dependency=afterany:<baseline job id>`, so the pair can be launched
  in one go.  It is `afterany` rather than `afterok` because a polaris
  suite exits non-zero when *any* task in it fails.  A baseline should
  not have failures, and one that does is worth investigating — but a
  single failed task does not invalidate the others, whose baseline
  output is on disk and is exactly what the test side needs.  Under
  `afterok`, one failure cost the entire comparison and left no way
  forward but to run both sides again.  The job is also submitted with
  `--kill-on-invalid-dep=yes`, so that a dependency that genuinely
  cannot be satisfied removes the job rather than stranding it as
  `DependencyNeverSatisfied`.  Because the driver exits as soon as
  `sbatch` accepts the job, it never sees the run return and so never
  writes the marker itself; a submitted baseline is recognized as
  complete from polaris' own end-of-run file instead, as above.
- A load script is **never created for you**; `./deploy.py` is a developer
  action.  A freshly provisioned worktree therefore has no load script of
  its own, since `load_*.sh` is git-ignored.  Either run `./deploy.py` in
  the provisioned worktree once, or set `load_script` to the *absolute*
  path of an existing load script.  In the latter case
  `NO_POLARIS_REINSTALL=true`, which is exported before the load script is
  sourced, lets one deployment serve several worktrees.  A `--dry-run`
  says so when it cannot yet check a load script.
- Collecting results and generating a report are deliberately **not** part
  of this driver yet; polaris writes its own validation output under
  `case_outputs/` in the test work directory.
