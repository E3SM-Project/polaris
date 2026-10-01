# Omega Pull Request Testing

date: 2026/09/29

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

The Omega
[pull request template](https://github.com/E3SM-Project/Omega/blob/develop/.github/pull_request_template.md)
asks for the CTests and the Polaris `omega_pr` suite to pass on six machine
and compiler combinations, with the results recorded in a `Testing`
comment. For Omega#481, agents on four machines did this from a handoff
written for that pull request alone. This design turns that process into a
Polaris utility, `utils/omega/pr_testing`, that any developer can use.

The developer who wants the results, the requester, starts two kinds of
agent. An initiator runs on any supported machine and pins the commits under
test in a branch on the requester's fork, then reports on linting and the
documentation build. A tester on each machine builds and runs both sides
against that pin, then reports its rows, including any new compiler
warnings. Scripts do the steps whose mistakes would pass unnoticed: choosing
the commits and producing the reports. Agent instructions cover the order of
setup and what to do when something fails, using the tools Polaris already
has.

Success means that a reviewer can check each item of the checklist from the
`Testing` comments alone: what was tested, against which baseline, and with
what result.

## Requirements

### Requirement: Any developer can request testing.

Nothing depends on one person's paths, fork, accounts or allocations.

### Requirement: Testing can start from any supported machine.

### Requirement: Every machine tests the same commits.

### Requirement: The baseline is Polaris' Omega submodule unless the requester chooses otherwise.

Any other baseline is stated in every report, with the reason.

### Requirement: Each report carries its own provenance.

A report names the machine, compiler and build directories. It identifies
the Polaris commit and the baseline and pull request Omega commits, each
with a few commits of recent history.

### Requirement: Results are reported as Polaris and CTest write them.

Anything an agent adds is kept apart from them.

### Requirement: The requester controls every outward-facing action.

Pushing the test branch, submitting jobs and posting comments each need the
requester's permission.

### Requirement: Testers do not tick the checklist.

The requester ticks the boxes from the posted results.

### Requirement: Progress across machines is visible.

The requester can see which rows have results, which were not run and why,
and which results are for commits that are no longer current.

### Requirement: A matching baseline is reused wherever it was run.

Before building a baseline, the tester looks for an existing `omega_pr`
run that matches, whether or not this utility made it. A reused baseline is
reported with its own provenance, like any other.

### Requirement: Linting and the documentation build are checked once.

They do not depend on the machine, so they are checked once per pull
request head rather than once per row. A result is posted only if Omega's
CI does not already show it on the pull request.

### Requirement: Each row reports new compiler warnings.

A report lists the warnings from the pull request build that the baseline
build does not have. It says which of them are in files the pull request
changes.

## Algorithm Design

### Algorithm Design: Any developer can request testing.

The requester is usually the pull request's assignee, but may be its author
or another reviewer. They run each agent in their own Polaris checkout on
that machine, with an existing load script. Per-machine settings come from a
config file the requester writes once per machine, and the agent asks for
any that are missing.

The agent instructions are committed in Polaris and reviewed like code. The
test branch carries data, not instructions.

### Algorithm Design: Testing can start from any supported machine.

The initiator only does git work, so any machine with an Omega clone will
do. The initiator may also be the tester for its own machine.

### Algorithm Design: Every machine tests the same commits.

The initiator makes the test commit by merging the pull request head into
the head of its base branch, as GitHub's test merge does. Any extra merges
the requester names, such as a build fix still in review, go on top. It
pushes two branches to the requester's fork:

```
omega-pr-test/<pr>-<head sha7>            test commit, then manifest commit
omega-pr-test/<pr>-<head sha7>-baseline   baseline commit
```

The tip of the first branch adds a single file, the manifest
`omega_pr_test.yaml`. Testers build its parent, so the manifest is not part
of the tested tree. Before building anything, a tester checks that the
parent contains the recorded pull request head and base branch head.

```yaml
schema_version: 1
requester: <GitHub user>
pull_request: 553
pr_head: <sha>
base_branch: develop
base_head: <sha>
test_commit: <sha>
baseline:
  commit: <sha>
  source: polaris-submodule   # or the ref the requester chose
  reason: null                # required unless polaris-submodule
  polaris_commit: <sha>       # polaris_commit by default
polaris_commit: <sha>
extra_merges:
  - {pull_request: 574, commit: <sha>, sides: [test]}
rows:
  - {machine: chrysalis, compiler: intel, mpi: openmpi,
     template: "chrysalis, oneapi-ifx, openmpi"}
notes: <free text for the requester>
```

Testers act only on the structured fields. `notes` is repeated in reports
and never followed.

An Omega pull request may need Polaris changes that the baseline Omega
cannot run, such as renamed config options. Then `polaris_commit` is a test
merge of the Polaris pull request, and the baseline runs from a second
Polaris checkout at `baseline.polaris_commit`, without those changes.

### Algorithm Design: The baseline is Polaris' Omega submodule unless the requester chooses otherwise.

By default, the baseline commit is the `e3sm_submodules/Omega` pin at
`baseline.polaris_commit`, which is normally Polaris `main` when the branch
is made. That pin states which Omega the Polaris code supports. So the
Polaris checkout the baseline runs from must pin the same Omega commit,
although it may be at a different Polaris commit, which is recorded.

The pin can lag far enough behind that differences would be hard to blame on
the pull request, as happened for Omega#481. In that case the requester can
choose another baseline, usually `base_head`. The reason goes in the
manifest and in each report.

### Algorithm Design: Each report carries its own provenance.

The Omega commit is recorded when Omega is built, not when a suite is set
up. Otherwise a suite set up with `-p` on an existing build reports the
source tree's HEAD at setup time, which may have moved since the build (the
gap noted in #823, filed as #827 and fixed by #829).

`<suite>_output_for_pr.md` gains the full hash and the last five
first-parent commits of the Polaris checkout and of both Omega builds. The
baseline's come from the baseline work directory's `provenance` file. The
CTest utility writes a matching `ctest_output_for_pr.md` with the build
directory and Omega commit.

Human testers get this too, whether or not they use the utility.

### Algorithm Design: Results are reported as Polaris and CTest write them.

Code builds each report from the two `.md` files, which are pasted
unchanged. The one-line summary at the top is generated from
`<suite>_results.json` and the CTest counts. After the results, the agent
may add a single `Notes` section for qualifications such as an extra merge
or a known failure. When an agent writes the report, it ends with the
signature that `AGENTS.md` prescribes. History and paths go in collapsed
`<details>` blocks, which keeps the visible comment short.

### Algorithm Design: The requester controls every outward-facing action.

Each outward-facing step prints what it would do, and acts only when given
a flag: `init --push`, `setup --submit`, and `--post` for `lint` and
`report`. The agent passes one of these only when the requester has allowed
it in that session.
A manifest or any other document cannot grant permission.

Building on the login node is not outward-facing. `polaris suite --build`
initializes the submodules and builds. The two builds run one after the
other, because concurrent CIME configures race.

### Algorithm Design: Progress across machines is visible.

Each report starts with a hidden marker:

```
<!-- omega-pr-test {"schema": 1, "pr": 553, "pr_head": "<sha>",
     "test": "<sha>", "baseline": "<sha>",
     "row": "chrysalis/intel", "status": "complete", "result": "pass"} -->
```

The report heading uses the template's label for the row, so the requester
can match it to a box. If a tester cannot run a row, for example because
the machine is down, it posts a report with `"status": "not-run"` and gives
the reason in `Notes`.

### Algorithm Design: A matching baseline is reused wherever it was run.

The tester searches the roots the requester lists, and always the utility's
own `<work_base>/baselines`. A candidate is any directory with both a
`provenance` file and an `omega_pr_results.json`. A candidate matches only
if all of the following hold:

- It has the same machine, compiler and build type.
- Its Omega commit, as recorded at build time, is the baseline commit.
- Its Polaris commit is that of the checkout the baseline runs from, and
  neither tree was dirty.
- It was set up as the `omega_pr` suite, with no extra config file.
- Its results are complete, and no task failed or is pending.

A run whose Omega commit was recorded only at setup never matches. The
matcher lists the near misses and the test each one failed, so the agent
can tell the requester what almost matched.

If nothing matches, `setup` makes a new baseline in `<work_base>/baselines`.
A baseline there whose job is still queued or running becomes the pull
request suite's dependency. With the submodule as the default baseline,
pull requests tested against the same Polaris commit share one baseline per
row.

The warnings comparison needs only a build log. It can use the log from any
complete build of the baseline commit with the same machine, compiler and
build type, even when no suite run matches. A build is complete if it
started from an empty build directory, which the build-time record notes.

### Algorithm Design: Linting and the documentation build are checked once.

Omega's `omega-pr` workflow already runs pre-commit on the changed files and
`make html-strict` on each pull request, in its "lint and test docs" job.
When that job has passed on `pr_head`, the initiator tells the requester
and posts nothing, since the pull request's checks already show the
result. If the job has not run for `pr_head`, or has not passed, the
initiator runs the same two commands on the test commit, in an `omega_dev`
environment. It then posts a `Testing` comment that gives pre-commit and the
documentation build each its own result, passing or failing. The comment's
marker has `lint` as its `row`.

Checking that the rendered documentation "looks as expected" still needs a
person.

### Algorithm Design: Each row reports new compiler warnings.

The baseline and pull request builds each leave a complete build log. A
warning is identified by its source path relative to the Omega tree, its
message and its warning flag, but not by its line number. A pull request
that adds lines above an existing warning therefore does not make that
warning look new. The report lists each identity that occurs more often in
the pull request build than in the baseline build. It marks the ones whose
file is in `git diff --name-only <base_head>...<pr_head>`.

With the submodule as the baseline, warnings added on `develop` since the
pin also appear as new. The mark separates those from the pull request's
own warnings.

Only complete build logs can be compared. When a build directory has to be
reused because an earlier build failed, `setup` rebuilds it with
`--clean_build` rather than building on top of the partial build.

## Implementation

### Implementation: Any developer can request testing.

`utils/omega/pr_testing/` holds:

- `AGENTS.md`: instructions for the initiator and tester roles, and the
  prompts the requester gives each one.
- `README.md`: the same workflow, written for people running the commands.
- `omega_pr_test.py`: the subcommands `init`, `lint`, `setup`, `report`
  and `status`, with the modules they use in `pr_test_*.py`.  The script's
  directory is on `sys.path`, so the prefix keeps a module from shadowing
  a standard one, such as `warnings`.
- `pr_test_warnings.py`: the build log parser.
- `example.cfg`: the per-machine settings. Copy it to
  `~/.config/omega_pr_test.cfg`, or pass another path with `-f`.

```ini
[omega_pr_test]
work_base = /path/to/scratch/omega_pr_test
omega_repo = /path/to/a/clone/of/E3SM-Project/Omega
# needed by the initiator only
fork = git@github.com:<user>/E3SM.git
# needed by the initiator only if Omega's CI has not passed
omega_dev_env = /path/to/conda/envs/omega_dev
# other places to look for a baseline to reuse, besides work_base
baseline_search_roots = /path/to/earlier/test/dirs
```

`init` ends by printing the prompt for each tester:

```
Test Omega PR 553 for pm-cpu/gnu from branch omega-pr-test/553-54456ec on
git@github.com:xylar/E3SM.git, following utils/omega/pr_testing/AGENTS.md.
```

### Implementation: Testing can start from any supported machine.

```
omega_pr_test.py init --pr 553 [--baseline <ref> --reason <text>]
                      [--merge-pr <n>]... [--baseline-merge-pr <n>]...
                      [--polaris-ref <ref>] [--baseline-polaris-ref <ref>]
                      [--rows <machine>/<compiler>,...] [--push]
```

`init` uses `gh` to find the pull request head and base branch, fetches them
from E3SM-Project/Omega, and makes the merges in a scratch worktree of
`omega_repo`. `polaris_commit` is the current `main` of
E3SM-Project/polaris, fetched rather than taken from the initiator's
checkout, unless `--polaris-ref` names another. `baseline.polaris_commit`
is `polaris_commit` unless `--baseline-polaris-ref` names another. If a
merge conflicts, `init`
stops, and the pull request's author must update the branch. The default
rows are the six in the template.

### Implementation: Every machine tests the same commits.

```
omega_pr_test.py setup --fork <fork> --branch <branch> [--submit]
                       [--baseline-dir <dir>]
                       [--baseline-load-script <script>]
```

`setup` fetches both branches and reads the manifest. It stops with a
message unless all of these hold:

- it knows the manifest's schema version;
- the test commit is the tip's parent, and it contains `pr_head` and
  `base_head`;
- the Polaris checkout has no uncommitted changes to tracked files (not
  counting submodule checkouts, which the utility never builds from), and
  it contains `polaris_commit`;
- the Polaris checkout the baseline runs from pins `baseline.commit`, if
  the baseline is the submodule;
- if `baseline.polaris_commit` differs from `polaris_commit`, the tester
  gave the load script of a second checkout, which is clean, contains
  `baseline.polaris_commit` and does not contain `polaris_commit`;
- the loaded Polaris environment belongs to this checkout
  (`POLARIS_BRANCH`), and its machine, compiler and MPI library give the
  row.

Omega worktrees are made from `omega_repo` at `<work_base>/omega/<sha12>`.
They are keyed by commit, so baselines and pull requests share them. Each
row gets its own directories:

```
<work_base>/pr<N>-<head sha7>/<machine>_<compiler>/
    build/       pull request build (-p)
    omega_pr/    pull request suite (-w, with -b <baseline>)
    ctest/       the CTest job script
    setup.json   what setup did, which report reads
    report.md
<work_base>/baselines/<machine>_<compiler>_polaris-<sha7>_omega-<sha7>/
    build/
    omega_pr/
```

`setup` runs `polaris suite -c ocean -t omega_pr --model omega --build`
for the baseline if needed, then for the pull request. A baseline from a
second checkout is set up in a clean login shell with that checkout's load
script sourced, so its job script loads that checkout too. It then runs
`omega_ctest.py -p <pull request build>`. Last, it prints or submits three
jobs: the baseline suite, the pull request suite (`afterany` on the
baseline) and the CTests. It submits them with `polaris.job.submit_job()`,
which handles Slurm and PBS dependencies. On Frontier it adds
`--qos=normal`: the `omega_pr` suite asks for each machine's debug target,
and Frontier allows only one debug job at a time. On Aurora it adds
`-q capacity`, Aurora's queue for 1 to 16 nodes, and each job waits for the
one before, because Aurora limits how many jobs a user may have queued, and
a job held on a dependency does not count. `utils/benchmark` keeps its own
copy of that code, because its driver runs outside any Polaris
environment.

A small table in the utility maps each template label to a Polaris machine,
compiler and MPI library. For now, it maps the Chrysalis `oneapi-ifx` row
to `intel` (see [Decisions](#decisions)).

### Implementation: Each report carries its own provenance.

#829, which fixed #827, provides the record. The Omega build template
writes `omega_source.txt` to the build directory before it runs `cmake`.
Both `polaris suite --build` and the CTest utility build through that
template. `polaris.build.source_record.read_source_record()` reads the
file. `provenance` gained `polaris git hash`, `polaris git log`,
`component git hash` and `component git log` entries. The component entries
are marked `(at setup, not build)` when the build has no record (see
{ref}`dev-provenance`).

On this branch, `_write_output_for_pull_request()` adds three lines, for
Polaris, the baseline Omega and the pull request Omega. It also adds a
`<details>` block with their logs.

`utils/omega/ctest/run_command.template` writes its summary to
`ctest_output_for_pr.md` as well as to standard output. It adds the build
directory and the Omega commit from `omega_source.txt`.

### Implementation: Results are reported as Polaris and CTest write them.

```
omega_pr_test.py report --row <machine>/<compiler> [--notes <file>]
                        [--not-run <reason>] [--agent <name>] [--post]
```

```markdown
## Testing: chrysalis, oneapi-ifx, openmpi (Polaris `intel`)
<!-- omega-pr-test {...} -->

CTests: 50 of 50 passed. `omega_pr`: 25 of 25 tasks passed against the
Polaris submodule baseline.

<omega_pr_output_for_pr.md>

<ctest_output_for_pr.md>

### Build warnings

<generated by pr_test_warnings.py>

### Notes

<agent text, if any>

---

*Posted by <agent> on @<requester>'s behalf. ...*
```

`--post` runs `gh pr comment <pr> -R E3SM-Project/Omega --body-file
report.md`. Without it, `report` prints the text for the requester to
paste.

### Implementation: The requester controls every outward-facing action.

`AGENTS.md` lists these flags. It says an agent passes one only when
the requester has allowed it in that session, and the same applies to any
`sbatch` or `qsub` the agent runs by hand. No command edits the pull request
body, and `AGENTS.md` tells testers not to edit it either.

### Implementation: Progress across machines is visible.

```
omega_pr_test.py status --pr 553
```

`status` reads the pull request's comments with `gh api` and parses the
markers. It prints one line per row and one for `lint`, each with its
result, and marks as stale any
row whose `pr_head` is not the pull request's current head.

### Implementation: A matching baseline is reused wherever it was run.

The matcher lives in `polaris/baselines.py`, so that `utils/benchmark` can
later use it in place of its directory-name cache. `find_baseline()` takes
the search roots and the criteria. It returns the matching directories and
the near misses, each near miss with its reasons. `find_build_log()` does
the same for build logs. Candidates are looked for up to three levels below
each root. The suite and any config file are read from the `command` line
in `provenance`.

The config file gains `baseline_search_roots`. `setup --baseline-dir <dir>`
names a candidate directly, and the matcher still checks it. A build log
counts as complete when the source record's `clean_build` is true, which
means the build started from an empty build directory.

When `setup` submits a job, it records the job's id in a `job_id` file in
that job's work directory. For a baseline in `<work_base>/baselines` that
is not complete, `setup` looks the id up with `squeue` or `qstat`. The
answer decides whether to depend on the job or to stop.

### Implementation: Linting and the documentation build are checked once.

```
omega_pr_test.py lint --fork <fork> --branch <branch> [--notes <file>]
                      [--agent <name>] [--post]
```

`lint` reads the manifest, then finds the "lint and test docs" check run
on `pr_head`, whose id is its Actions job's. It reads the conclusions of
the job's "Run pre-commit" and "Build Sphinx Docs" steps from the Actions
API. If the job has not passed, `lint` puts `omega_dev_env` first on `PATH`
in a worktree of its own at the test commit, since the checks can change
files. It runs `pre-commit run --files <changed files>` at the root and
`make html-strict` in `components/omega/doc`, keeping both logs. `--post`
posts only results from such a local run.

The comment is headed `## Testing: lint and docs`, with one line each for
pre-commit and the documentation build. Each line says `passed` or `failed`
and whether it came from CI (with the job link) or from a local run (with
the log path).

### Implementation: Each row reports new compiler warnings.

Polaris already writes each build's output to `<build>/build_omega.log`.
`pr_test_warnings.py` reads three forms of warning:

```
<path>:<line>:<col>: warning: <message> [-W<flag>]    GCC, Clang, oneAPI
<path>(<line>): warning #<n>: <message>               NVCC, ifx
<path>:<line>:<col>:  ...  Warning: <message>         gfortran
```

It also reads `CMake Warning at <path>:<line>` blocks, using the first line
of the message. Each path is made relative to the Omega tree named in the
build's source record. Lines from `make` itself, such as
`jobserver unavailable`, are ignored.

The report's `Build warnings` section gives the count of new warnings and
how many are in files the pull request changes, then lists them in a
`<details>` block. It also gives both log paths. The marker gains
`"new_warnings": <n>`.

## Testing

### Testing and Validation: Any developer can request testing.

The first trial is Omega#553 on all four machines. A second requester then
repeats it, on at least one machine, from their own accounts.

The second trial is Omega#524, tested with a Polaris test merge of
polaris#731 and a baseline run from a second checkout without it.

### Testing and Validation: Every machine tests the same commits.

Unit tests build small git repositories in a temporary directory, with a
base branch, a pull request branch and an extra-merge branch. They run
`init` and the `setup` checks against these repositories. The cases include
a conflict, a tip whose parent is not the test commit, a Polaris
checkout that pins a different Omega, and a baseline checkout that is
missing or contains `polaris_commit`.

### Testing and Validation: Each report carries its own provenance.

Unit tests of `_write_output_for_pull_request()` use fixture `provenance`
files for a pull request work directory and a baseline work directory. A run
of `omega_pr` against a baseline checks the file from a real suite.

### Testing and Validation: Results are reported as Polaris and CTest write them.

Unit tests build reports from fixture `.md` files and check that both files
appear byte for byte.

### Testing and Validation: Progress across machines is visible.

Unit tests parse markers from fixture comments, including a stale report
and a not-run report.

### Testing and Validation: A matching baseline is reused wherever it was run.

Unit tests search fixture work directories containing an exact match, one
near miss for each test, a run whose Omega commit was recorded only at
setup, and a run with incomplete results. They look up build logs from a
clean build and from an incremental one. The #553 trial reuses a baseline
on at least one machine.

### Testing and Validation: Linting and the documentation build are checked once.

Unit tests mock the check runs for a passed check, a failed check and a
missing check, and verify which path `lint` takes and that results from CI
are never posted. The #553 trial runs `lint` for real.

### Testing and Validation: Each row reports new compiler warnings.

Unit tests parse fixture logs taken from real builds with GCC, Clang,
oneAPI and NVCC. They check three cases: a warning that only moves lines is
not new, a second instance of an existing warning is new, and a warning in
a changed file is marked. The #553 trial checks the section on every row.

## Decisions

- **Scripts do the pinning and reporting, and agent instructions do the
  rest.** The tools that build and run, `polaris suite --build` and
  `omega_ctest.py`, are already scripts. The problems on Omega#481 were of
  two kinds. Mistakes in the handoff, such as initializing submodules by
  hand and building inside jobs, are fixed by instructions that are
  reviewed. Problems in the environment, such as Omega#572 and the
  out-of-date CTest mesh, needed judgment that a wrapper script could not
  supply. The mistakes that would go unnoticed, such as testing the wrong
  commits or retyping a result, are the ones that are scripted.
- **The test commit is the merge into the base branch, not the pull request
  head**, because the merge is what lands.
- **The test branch lives on the requester's fork.** Recreating the merge
  on each machine would avoid a push, but it could not carry conflict
  resolutions or extra merges.
- **Each row gets its own comment.** Rows finish at different times on
  different machines, and separate comments need no coordination.
- **Baselines are found from provenance, not from `utils/benchmark`'s
  cache or by an agent.** The cache sees only directories that `benchmark`
  named itself, and most existing baselines were set up some other way. An
  agent reading provenance by hand can miss a field that matters, such as a
  dirty tree or a commit recorded at setup rather than at build time.
- **Linting and the documentation build come from Omega's CI when it has
  passed, and are then not posted.** Running them locally every time would
  repeat the same commands on nearly the same tree, and would need an
  `omega_dev` environment on every initiator's machine. A comment repeating
  CI's passing checks adds nothing the pull request does not already show.
- **Polaris changes an Omega pull request needs are a Polaris test merge,
  and the baseline runs without them.** Omega#524 renamed the options
  every task writes, so its Polaris changes (polaris#731) cannot run the
  baseline Omega. Testing the pull request with Polaris `main` is not
  possible either.
- **The template's compiler names are mapped, not fixed.** E3SM has renamed
  its compilers to `intel`, and Omega has not caught up yet. The template
  should be fixed once, after the names settle.
