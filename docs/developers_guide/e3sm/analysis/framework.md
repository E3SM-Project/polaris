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
