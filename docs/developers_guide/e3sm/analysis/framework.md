(dev-e3sm-analysis-framework)=

# Framework

## Reading an E3SM case

{py:class}`polaris.e3sm.analysis.case.E3smCase` reads a case's variables
from the `env_*.xml` files in its case directory, without CIME. References
to other case variables (`$CASE`, `${CASE}`) and to environment variables
(`$ENV{USER}`) are expanded, so `RUNDIR` and `DOUT_S_ROOT` come back as
paths:

```python
from polaris.e3sm.analysis.case import E3smCase

case = E3smCase('/home/user/e3sm_cases/misomip/my_case')
files = case.find_stream_files('mpaso', 'timeSeriesStatsMonthlyOutput')
logs = case.find_logs('cpl')
```

A model's output is found from the streams file it read in the run
directory, `streams.ocean` for `mpaso` and `streams.landice` for `mali`,
through {py:func}`polaris.streams.find_stream_files`. Files are looked for
in the short-term archive (`<DOUT_S_ROOT>/ocn/hist` or `glc/hist`) and then
in the run directory, and a file in both is taken from the archive. Logs are
found the same way, in `<DOUT_S_ROOT>/logs` and the run directory.

## The runs being compared

{py:class}`polaris.e3sm.analysis.runs.E3smRun` is one model's output in an
E3SM case, and {py:class}`polaris.e3sm.analysis.runs.StandaloneRun` is a
standalone MPAS-Ocean run in the work directory of a Polaris forward step.
Both give the run's initial condition, which holds the mesh, the files of a
stream, and an option from the namelist the model read, so an analysis step
reads either through the same calls.
{py:func}`polaris.e3sm.analysis.runs.select_months` selects the monthly
means in a range of years and makes a missing month an error, and
{py:func}`polaris.e3sm.analysis.runs.month_range_key` names the months
found, for step directories.

## Coupler budgets

With `BUDGETS=TRUE`, the coupler writes net budgets of area, heat, water and
salt to its log for each period: `inst`, `daily`, `monthly`, `annual` and
`all_time`, at the levels the driver's namelist sets.
{py:func}`polaris.e3sm.analysis.budgets.read_budget_tables` reads every
table from a list of logs, compressed or not, and
{py:func}`polaris.e3sm.analysis.budgets.budget_time_series` gathers one
budget and period into a time series:

```python
from polaris.e3sm.analysis.budgets import (
    budget_time_series,
    read_budget_tables,
)

tables = read_budget_tables(case.find_logs('cpl'))
ds = budget_time_series(tables, budget='WATER', period='monthly')
exchanged = ds.budget.sel(row='wpolar', component=['ocn', 'glc', '*SUM*'])
```

The coupler prints global means over the sphere, scaled for printing, with
8 decimals. They are converted back to totals with E3SM's radius: kg s⁻¹
for water and salt, and W for heat. Values are read by position, as the
Fortran format writes them, since a value that fills its field touches the
one before it. A field the coupler could not fit, printed as asterisks, is
NaN. A date in more than one table, as when a run restarts, takes the last.

## Performance

{py:mod}`polaris.e3sm.analysis.performance` reads what CIME and the driver
write for each segment of a run, the job that runs one stretch of model
time.  Each segment's files end in its LID, `<job ID>.<date>-<time>`:

- {py:func}`polaris.e3sm.analysis.performance.find_timing_files` finds the
  timing summary and timer statistics in the case's `timing` directory, in
  the order the segments ran;
- {py:func}`polaris.e3sm.analysis.performance.read_segment` reads a
  segment's throughput, cost, start-up, run and finishing times, each
  component's run time and the largest time of each timer, and takes the
  segment's model period from its coupler log;
- {py:func}`polaris.e3sm.analysis.performance.read_wall_clock_stamps`
  reads the coupler's daily wall-clock stamps, as wall-clock seconds per
  model day;
- {py:func}`polaris.e3sm.analysis.performance.read_root_memory` reads the
  memory of the coupler's root task from the coupler's logs, and
  {py:func}`polaris.e3sm.analysis.performance.read_node_memory` reads the
  memory of a root task's node from the driver's profiles at level 3;
- {py:func}`polaris.e3sm.analysis.performance.read_slurm_jobs` reads each
  job's queue wait and largest task memory from `sacct`, where Slurm's
  accounting is available.

```python
from polaris.e3sm.analysis.performance import (
    find_lid,
    find_timing_files,
    read_segment,
)

logs = {find_lid(path): path for path in case.find_logs('cpl')}
segments = [
    read_segment(summary, stats, logs[lid])
    for lid, (summary, stats) in find_timing_files(case.case_dir).items()
]
```

Each segment starts new processes, so memory records are kept for every
segment, even where the last record of one and the first of the next share
a model time.  A model day that a later segment runs again takes the later
segment's wall-clock stamp.

## Provenance

{py:class}`polaris.e3sm.analysis.provenance.CaseProvenance` is a
{py:class}`polaris.analysis.page.PageStep` that records what made a case's
run on a page of its own, which the footer of every gallery page links to:

- the code, from the `GIT_*` files and `build_environment.txt` CIME writes
  in the build directory, including where Albany and Trilinos were found;
- the commands that created and changed the case, from its `replay.sh`,
  and the current value of each case variable an `xmlchange` set;
- the options set in each `user_nl_*` file, with the namelist group each
  is in, and the files under `SourceMods`;
- copies of the namelists, streams files, `drv_in`, `seq_maps.rc` and
  Albany's input from the run directory, published with a `.txt` suffix so
  a browser shows them.

The options are those set explicitly, whether or not they differ from the
defaults.  The files are copied when the step runs, so they are those of the
run's most recent job, and the page gives the date of its latest restart.
