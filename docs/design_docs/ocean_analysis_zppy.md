(design-ocean-analysis-zppy)=

# Running the Ocean Analysis from zppy

Creation date: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

## Summary

This design makes the Polaris analysis of Omega simulations a built-in zppy
task, so that it runs as part of the standard E3SM post-processing workflow,
as MPAS-Analysis does today. It is part of Phase 2 of
{ref}`design-ocean-analysis`.

A user adds a `[polaris]` section to their zppy configuration, naming the
Polaris suite to run, `omega_analysis`, and the year ranges to analyze (D5).
For each pair of ranges, zppy renders a Polaris config file and submits a
job. The job sets up and runs the suite inside its allocation, then copies
the gallery to the web portal. Every job of a case and suite shares one
Polaris work directory, so a later job reuses what an earlier one computed
(D3).

The design follows zppy as it stands, with the reorganization in progress
there. zppy renders each package's config file from a template beside the
job script ([E3SM-Project/zppy#914](https://github.com/E3SM-Project/zppy/pull/914)),
and a built-in task is a module like `zppy/mpas_analysis.py` with a template
in `zppy/templates/`. A later zppy change, a shared job loop with a task
registry, will change how a built-in task is added. This design moves with it.

Polaris needs four things from its side:

- to be installable in E3SM-Unified, through the conda-forge package
  ([conda-forge/staged-recipes#35840](https://github.com/conda-forge/staged-recipes/pull/35840)).
  E3SM-Unified 1.15.0 is to be the first release to carry it;
- to accept more than one config file at setup, so that zppy's options win
  over the user's (D4);
- the cached observational products of
  {ref}`design-ocean-analysis-observations` staged on each supported
  machine, so that a job downloads nothing (D6);
- a documented, stable set of the config options zppy sets.

Success is that a zppy user analyzes an Omega case with a few lines of zppy
configuration, gets one gallery per case on the web portal, and pays only for
the new years when the case is extended.

Out of scope:

- comparing two runs, which zppy's MPAS-Analysis task supports and Polaris's
  analysis does not yet;
- MPAS-Ocean output, which Polaris's analysis does not read;
- the zppy tasks that take ocean results from MPAS-Analysis. In an Omega run,
  `global_time_series` cannot take its ocean plots from MPAS-Analysis, and
  MPAS-Seaice analysis through MPAS-Analysis has to run without MPAS-Ocean.
  These are zppy and MPAS-Analysis work.

### Open questions

1. **Paths after short-term archiving.** Omega's history files move to
   `archive/ocn/hist`, while `omega.yml` stays in `run/`. Do all the paths in
   `omega.yml` still resolve, in particular the mesh file?
2. **Default resources.** How many nodes and how much walltime should a job
   ask for by default? This waits on measurement under task parallelism.
3. **Changed options and versions.** Polaris never reruns a completed step,
   so a changed option or a new Polaris version reaches only ranges not yet
   analyzed. Should Polaris notice a completed step whose config or version
   has changed, and rerun it? That would serve analyses run by hand too.

## Requirements

### Requirement: zppy runs the Omega analysis of a case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A zppy user shall be able to analyze an Omega case by adding one section to
their zppy configuration, naming the year ranges to analyze. zppy shall
submit the jobs, report their status, and publish the results on the web
portal, as it does for MPAS-Analysis.

### Requirement: Polaris is a built-in zppy task

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The analysis shall be a task built into zppy, not a zppy plugin (D1).

### Requirement: Extending a case costs only the new years

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Each job shall analyze one climatology range and one time-series range. A job
whose ranges overlap an earlier job's shall reuse what that job computed,
under the rules of {ref}`design-ocean-analysis` for inherited caches.

### Requirement: Starting over is explicit

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A user shall be able to redo every range of a case with one option. Short of
that, a job shall not recompute a range that is already complete. A changed
Polaris option or Polaris version shall apply to the ranges analyzed after
it.

### Requirement: One gallery per case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

All the ranges analyzed for a case shall appear in one gallery on the web
portal, which grows with each job. Everything published shall be readable by
anyone who can read the portal.

### Requirement: A job is self-contained

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A job shall do all its work inside its own allocation. It shall need no
network access and no write access outside the case's output and the
portal. It shall not submit batch jobs of its own.

### Requirement: Failures reach zppy

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A failed job shall record the failure in its zppy status file, and its log
shall name the Polaris step that failed.

### Requirement: The job uses its whole allocation

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A job shall spread the analysis over every node of its allocation, through
Polaris's task parallelism, including Phase C's pieces once
[polaris#892](https://github.com/E3SM-Project/polaris/pull/892) merges.

### Requirement: Polaris options pass through zppy

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A user shall be able to set any Polaris analysis option from their zppy
configuration, except the ones zppy itself sets.

### Requirement: zppy's options are a stable interface

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The Polaris config options zppy sets shall be documented in Polaris's User's
Guide. A change to them shall be made together with the matching change in
zppy.

## Algorithm Design

### Algorithm Design: zppy runs the Omega analysis of a case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A minimal zppy configuration:

```cfg
[polaris]
active = True
suite = omega_analysis
ts_years = "1-50",
climo_years = "21-50",
```

Every option of the section means the same for any suite, so `default.ini`
validates it once (D5):

| Option | Meaning |
| --- | --- |
| `suite` | the Polaris suite to run, from those zppy knows |
| `ts_years`, `climo_years` | the time-series and climatology ranges (D8) |
| `input_subdir` | where the case's history files are, relative to `input` |
| `polaris_cfg` | a Polaris config file of the user's |
| `purge` | start the suite's analysis of the case over |
| `nodes`, `walltime`, `partition` | the job's resources |

`ts_years` and `climo_years` are zipped into jobs, as `[mpas_analysis]` zips
them. Each job's prefix is `polaris_<suite>_ts_<y1>-<y2>_climo_<y1>-<y2>`,
with years padded to four digits and the subsection's name after the suite
when there is one, as for `[mpas_analysis]`. Two subsections asking for the
same ranges of the same suite therefore get different prefixes.

What differs between suites is in a template for each suite. zppy renders
`<prefix>.cfg` from the suite's template, with the options zppy owns. For
`omega_analysis`:

```cfg
[ocean]
model = omega

[ocean_analysis]
omega_config_filename = {{ input }}/run/omega.yml
simulation_path = {{ input }}/{{ input_subdir }}
simulation_name = {{ case }}
output_path = {{ output }}/post/analysis/polaris/{{ suite }}/gallery

[ocean_analysis_climatology]
start_year = {{ climo_year1 }}
end_year = {{ climo_year2 }}

[ocean_analysis_time_series]
start_year = {{ ts_year1 }}
end_year = {{ ts_year2 }}
```

`omega.yml` is the file Omega's `buildnml` writes in the run directory, so it
needs no option. `input_subdir` is zppy's existing option. In `[polaris]` it
defaults to `archive/ocn/hist`, as in `[global_time_series]`, and a case that
was not short-term archived sets it to `run`.

The job script then runs, from the work directory:

```bash
polaris suite -c ocean -t {{ suite }} -w ${workdir} \
    -f ${user_cfg} -f {{ scriptDir }}/{{ prefix }}.cfg \
    --model omega -m {{ machine }}
polaris parallel
```

The component and model, here `ocean` and `omega`, come from a table in the
zppy module that gives each suite its template, Polaris component and model.

Polaris reads zppy's rendered file where zppy wrote it. The user's config file
comes first so that zppy's options win (D4). The machine is named rather than
detected, since detection from a compute node's hostname can fail. The task
runs on the machines both zppy and Polaris support: Chrysalis, pm-cpu and
pm-gpu. On any other machine zppy reports this when it submits.

### Algorithm Design: Extending a case costs only the new years

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Every job of a case and suite uses one Polaris work directory,
`<output>/post/analysis/polaris/<suite>/work`, which persists between zppy
runs. Each job depends on every earlier job of the same suite, so they run
one at a time, in the order of the configuration (D3). Jobs of different
suites have different work directories and need not wait for each other.
Within the work directory, the analysis's own rules decide what is reused:

- a range already analyzed is complete, and costs nothing;
- a new range creates new step directories;
- an accumulator for an overlapping range inherits the months an earlier
  range reduced.

A failed job holds back every later range of its suite, as with
`[mpas_analysis]`.

### Algorithm Design: Starting over is explicit

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A completed Polaris step is never rerun, and a zppy job whose status is `OK`
is never resubmitted. A changed option or a new Polaris version therefore
reaches only ranges not yet analyzed. Every page of the gallery records the
Polaris version and options that made it, so a gallery that spans a change
says so.

`purge` starts the suite's analysis of the case over:

- zppy resubmits every range of the suite, whatever its status file says;
- the first job removes the suite's work directory and portal directory
  before its setup, and later jobs remove nothing;
- zppy refuses `purge` while a job of the suite is waiting or running;
- zppy warns that it is purging, since `purge` is meant for one zppy run and
  redoes the whole suite on every run it is left on for.

Purging in every job would delete the ranges the earlier jobs had just made,
and `rsync --delete` would then remove them from the portal.

### Algorithm Design: One gallery per case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Polaris publishes every range into one staging tree, the work directory's
`output_path`, with the range in every file name. After `polaris parallel`
succeeds, the job copies the whole staging tree to
`${www}/${case}/polaris/<suite>/` with `rsync -a --delete` and makes it world
readable, as the MPAS-Analysis template does (D7). The staging tree holds
copies rather than links, so `rsync` needs no option to follow links.

### Algorithm Design: A job is self-contained

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Setup and run both happen in the job. Setup downloads nothing, because the
cached observational products are already in the Polaris database on each
supported machine (D6). Polaris links to them there, so the job needs only
read access to the database. `polaris parallel` runs inside the job's
allocation and submits nothing.

### Algorithm Design: Failures reach zppy

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Each command is checked, and a failure writes a numbered error to the status
file:

| Failure | Status |
| --- | --- |
| `polaris suite` | `ERROR (1)` |
| `polaris parallel` | `ERROR (2)` |
| creating the portal directory | `ERROR (3)` |
| `rsync` to the portal | `ERROR (4)` |

`polaris parallel` exits non-zero when a step fails and names the step in its
output, which the job log captures.

### Algorithm Design: The job uses its whole allocation

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

zppy asks for nodes and walltime, and `polaris parallel` schedules the suite's
steps over all of them. Once polaris#892 merges, it also starts a resident on
each node and hands out the comparisons as pieces. The job needs nothing more
from zppy for that: the residents' network interface comes from Polaris's
machine config.

### Algorithm Design: Polaris options pass through zppy

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The option `polaris_cfg` names a Polaris config file of the user's. The job
passes it to `polaris suite` before zppy's own file. An option in both takes
zppy's value.

## Implementation

### Implementation: zppy runs the Omega analysis of a case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

In zppy:

- `zppy/polaris.py`, modeled on `zppy/mpas_analysis.py` but much smaller,
  with no reference-run modes and an identifier function of its own. A table
  in it gives each suite its template, Polaris component and model. It does
  not otherwise branch on `suite`.
- `zppy/templates/polaris.bash`, the job script.
- `zppy/templates/polaris/omega_analysis.cfg.jinja`, the suite's Polaris
  config template. #914 gives templates a `.jinja` suffix so that linters and
  packaging leave them alone. The module loads it through the environment
  `initialize_template()` returns and writes it with `write_rendered_file()`,
  both from #914.
- A `[polaris]` section in `zppy/defaults/default.ini`, with `suite`,
  `ts_years`, `climo_years`, `input_subdir`, `polaris_cfg` and `purge`.
  `suite` is `option("omega_analysis", default="omega_analysis")`, so zppy
  rejects an unknown suite before rendering any job. Adding a suite adds it
  to that list, to the table and as a template. The section also sets
  `nodes`, `walltime` and `partition`, with the comment `[mpas_analysis]`
  uses for options that always override `[default]`, since `[default]` has
  `nodes = 1`.
- A call right after `mpas_analysis` in zppy's task order, a `print_url()`
  call for the suite's portal path, and a page in zppy's User's Guide.

When zppy's task registry lands, the module becomes a registered task through
whatever interface that defines.

### Implementation: Extending a case costs only the new years

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The chaining follows the intent of `mpas_analysis.py`, which makes each job
depend on every earlier status file of the section, but not its code:

- the chain is kept per suite;
- every job joins it, including bundled and dry-run jobs, so jobs split
  across bundles keep their order;
- each job gets its own list of dependencies, rather than all sharing one
  list that keeps changing;
- `input_subdir` and the other options are read from the job's own section
  or subsection.

When zppy's task registry lands, "run this task's jobs in order" should become
a property the task declares, rather than code each task copies.

### Implementation: Starting over is explicit

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The module handles `purge` at submission. It refuses if any status file of
the suite says `WAITING` or `RUNNING`. Otherwise it warns that it is purging,
removes the suite's status files and passes a flag to the first job's
template only. The User's
Guide pages in zppy and Polaris state the rule that changes reach only new
ranges.

### Implementation: One gallery per case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The copy and the permission fixes use zppy's shared bash helper for
publishing to the portal if it has merged, and the same block as
`mpas_analysis.bash` if it has not. The helper does the same `rsync` and
permission fixes, so the design is the same either way.

### Implementation: A job is self-contained

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Staging the observational products on each supported machine becomes part of
releasing Polaris into E3SM-Unified. The Polaris version and its products are
staged together, so a job never finds a product missing.

### Implementation: The job uses its whole allocation

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

When polaris#892 merges, `distributed` and `cryptography` become Polaris
dependencies, so the conda-forge recipe gains them.

### Implementation: Polaris options pass through zppy

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

`polaris setup` and `polaris suite` take `-f` more than once, each file
overriding those before it. Today they take one.

### Implementation: zppy's options are a stable interface

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A "running under zppy" section of the analysis page in the User's Guide lists
the options zppy sets. A unit test in Polaris sets up the suite from a config
file with exactly those options, so a rename fails there first.

### Implementation: order of work

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

1. Polaris: `-f` taken more than once, and the "running under zppy" page.
2. Polaris: the conda-forge package, and Polaris in E3SM-Unified 1.15.0.
   Until a user has that release, `environment_commands` points at a Polaris
   environment.
3. zppy: the module, templates and defaults, after zppy#914.
4. Both: an end-to-end test on Chrysalis.
5. zppy: move the module onto the task registry when it lands.

## Decisions

Alternatives considered and set aside, cited from the sections they affect.

### D1: A built-in task

Xylar, 2026/11/26.

Set aside: zppy's `plugins` option, which needs a module from the package
to be importable in zppy's own environment.

### D2: zppy renders a Polaris config file

Proposed, 2026/11/26. This is the pattern zppy#914 sets for MPAS-Analysis and
E3SM Diags, and the rendered file stays beside the job script as a record.

Set aside: a Polaris command that takes zppy's values as arguments and writes
the config itself. That would let Polaris rename options without a matching
zppy change, but it adds a command to maintain for one caller, and it hides
the config from zppy users.

### D3: One work directory per case, with jobs run in order

Proposed, 2026/11/26. Reuse across ranges happens only within one work
directory. `polaris suite` rewrites the suite file at the work directory's
root, and every range publishes into one staging tree, so two jobs in one
work directory cannot run at once. Running them in order also lets each
inherit everything the earlier ones computed.

Set aside: a work directory per job, which reuses nothing, and concurrent
jobs in one work directory.

### D4: Polaris takes several config files, and zppy's comes last

Proposed, 2026/11/26.

Set aside: zppy merging the user's file into its own, which puts Polaris's
config semantics into zppy, and writing both into one file, which repeats
sections that Polaris's config parser does not merge.

### D5: One `[polaris]` section, with a `suite` option and a template per suite

Xylar, 2026/11/26, open to change in review.

- It names the tool, as `e3sm_diags`, `ilamb` and `livvkit` do. A later
  Polaris analysis adds a suite and its template, not a section.
- zppy validates each section once against `default.ini`, so every option
  of the section means the same for any suite. `ts_years` and `climo_years`
  are concepts throughout zppy and apply to any analysis (D8).
- What differs between suites, such as the Omega configuration file and the
  model, is in the suite's template and its row of a table in the module,
  which does not otherwise branch on `suite`.
- The suite's name is in the job and status-file prefixes and in the portal
  path, `${www}/${case}/polaris/<suite>/`, which tells someone browsing
  diagnostics what they are looking at.

Set aside:

- `[omega_analysis]`, a section per analysis. It names what is analyzed, as
  `tc_analysis` and `global_time_series` do, but each later Polaris analysis
  would need a section of its own.
- A `[polaris]` section whose options depend on `suite`, such as an
  `omega_config` option. `default.ini` cannot validate those per suite, and
  the module would branch on `suite`.

### D6: Observational products are staged in advance

Proposed, 2026/11/26. A compute node may have no network access, and a
zppy user cannot be assumed to have write access to the shared Polaris
database.

Set aside: downloading at setup, which works for Polaris's own developers
but can fail in a zppy job.

### D7: zppy copies Polaris's staging tree to the portal

Proposed, 2026/11/26. Permission fixes stay in zppy, which already knows each
machine's portal, and the portal never shows a half-published gallery.

Set aside: pointing `output_path` at the portal directly.

### D8: `ts_years` and `climo_years`, as for MPAS-Analysis

Xylar, 2026/11/26. These are concepts throughout zppy and are assumed to
apply to any Polaris analysis. The Omega analysis has independent
time-series and climatology ranges, as MPAS-Analysis does, and zppy users
know these options.

Set aside: zppy's generic `years`, which gives one range per job.

## Testing

### Testing and Validation: zppy runs the Omega analysis of a case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- zppy's snapshot tests of rendered scripts
  ([E3SM-Project/zppy#908](https://github.com/E3SM-Project/zppy/pull/908))
  cover the new job script and config file. `[polaris]` is added to
  `tests/rendering/comprehensive.cfg` with two ranges, so that the chain and
  the shared work directory show, and to `machines.cfg`. An unknown `suite`
  is rejected when zppy reads the configuration.
- An end-to-end run on Chrysalis analyzes a short Omega coupled case.
- zppy's weekly integration tests gain the task. That needs an Omega case
  staged on Chrysalis and the task activated in `tests/integration/utils.py`
  and the weekly template configs.

### Testing and Validation: Extending a case costs only the new years

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

In the end-to-end run, a second zppy run adds a longer time-series range. The
second job's log reports months inherited from the first.

### Testing and Validation: Starting over is explicit

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

With two ranges and `purge` set, both ranges are recomputed and both appear
on the portal. With a job of the suite still waiting, zppy refuses
`purge`.

### Testing and Validation: One gallery per case

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

After both jobs, the portal's gallery shows both ranges, and every file and
directory in it is world readable.

### Testing and Validation: A job is self-contained

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The setup log of the end-to-end run shows no downloads.

### Testing and Validation: Failures reach zppy

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A job pointed at a missing `omega.yml` writes `ERROR (1)`. A job whose step
fails writes `ERROR (2)` and names the step in its log.

### Testing and Validation: The job uses its whole allocation

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A two-node job reports work on both nodes in Polaris's summary of handed-out
work.

### Testing and Validation: Polaris options pass through zppy

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A Polaris unit test sets up with two config files and checks that the second
file's values win.

### Testing and Validation: zppy's options are a stable interface

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The unit test under the implementation sets up the suite from exactly the
options zppy sets.
