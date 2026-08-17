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

An adopted worktree is treated as **strictly read-only**.  The driver never
runs `fetch`, `checkout`, `submodule update`, `reset` or `clean` against it.
If a required submodule is not initialized, the driver stops and tells you
the command to run yourself.  This lets you benchmark the branch you are
already working in, with its existing build, without a second copy.

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
guardrail and prints the exact commands, but touches nothing.

## Configuration options

### `[benchmark]`

| Option | Description |
| --- | --- |
| `work_base` | Base directory for all benchmark output. |
| `primary_path` | The polaris clone worktrees are made from and forks are fetched into.  Defaults to the config file's directory.  Only ever fetched from. |
| `load_script` | Name of the load script to source *within each worktree*. |
| `setup_command` | A `polaris setup` or `polaris suite` command. |
| `run_command` | Usually `polaris serial`; used when `submit = False`. |
| `submit` | Submit the job script instead of running in place. |
| `polaris_config_file` | Optional config file passed on with `-f`. |

`--model`, `--branch`, `-p`, `-w`, `-b`, `-f` and the build flags are
appended automatically and **must not** appear in `setup_command`; the
driver raises an error if they do.

### `[baseline]` and `[test]`

| Option | Description |
| --- | --- |
| `source` | `worktree` or `existing`. |
| `path` | The existing worktree, when `source = existing`. |
| `polaris_fork` | A GitHub owner (e.g. `E3SM-Project`) or a full remote URL. |
| `polaris_ref` | A branch, tag or commit hash. |
| `omega_fork`, `omega_ref` | Override the Omega submodule. |
| `e3sm_fork`, `e3sm_ref` | Override the E3SM-Project submodule. |
| `mali_fork`, `mali_ref` | Override the MALI-Dev submodule. |
| `model` | The polaris `--model` value: `mpas-ocean`, `omega` or `mali`. |

A fork given as a bare owner is expanded to a URL matching the style
(ssh or https) of the existing `origin` remote.  Fork and ref options are
forbidden when `source = existing`, since the checkout's own fork and ref
are *recorded* rather than requested.

Any submodule not given a ref stays at the hash pinned by `polaris_ref`.

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

## Guardrails

The driver refuses to run, before anything is built, if:

- The two sides resolve to the **same** worktree or to identical commits
  everywhere, so there would be nothing to compare.
- They differ in **more than one** of polaris, Omega, E3SM and MALI, so a
  difference could not be attributed to a single change.
  Override with `--allow-multiple-changes`.
- They use **different load scripts**, implying a different machine,
  compiler or MPI library.  Override with `--allow-env-mismatch`.
- They use different `model` values.
- An **adopted** worktree has uncommitted or untracked changes, since the
  run could not then be reproduced from the recorded hashes.  Override
  with `--allow-dirty`; the run is recorded as `reproducible: false`, its
  directory is prefixed with `dirty-`, and its baseline is never cached
  or reused.
- An adopted worktree is missing the submodule needed for `model`, or its
  load script does not exist.  Creating the environment with `./deploy.py`
  is a developer action and is never done for you.

## Output layout

```
<work_base>/
  worktrees/<ref>-<sha7>/            provisioned polaris worktrees
  baselines/<suite>_<model>_<shas>/  reusable baseline work dirs
  runs/<date>-<base sha7>-<test sha7>/
    benchmark.log
    manifest.json
    build_baseline/  build_test/
    test/
```

A baseline work directory is keyed on the suite, model and every commit
hash, and is marked complete when it finishes.  A later benchmark with the
same key **reuses** it instead of rerunning, which is what makes iterating
on a test branch cheap.

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

By default neither is passed, so an existing build is reused — which is
usually the point of adopting an existing worktree.

## Notes

- When `submit = True`, the test job is submitted with
  `--dependency=afterok:<baseline job id>`, so the pair can be launched in
  one go.  Because completion is asynchronous, work directories are not
  marked complete (and so not reused) in this mode.
- `NO_POLARIS_REINSTALL=true` is exported before sourcing a load script, so
  one deployment can serve several worktrees.
- Collecting results and generating a report are deliberately **not** part
  of this driver yet; polaris writes its own validation output under
  `case_outputs/` in the test work directory.
