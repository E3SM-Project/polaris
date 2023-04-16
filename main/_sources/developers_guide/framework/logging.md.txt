(dev-logging)=

# Logging

polaris does not have its own module for logging, instead making use of
`mpas_tools.logging`.  This is because a common strategy for logging to
either stdout/stderr or to a log file is needed between polaris and
`mpas_tools`.  To get details on how this module works in general, see
[MPAS-Tools' Logging](http://mpas-dev.github.io/MPAS-Tools/stable/logging.html)
as well as the APIs for {py:class}`mpas_tools.logging.LoggingContext` and
{py:func}`mpas_tools.logging.check_call`.

For the most part, the polaris framework handles logging for you, so
test-case developers won't have to create their own `logger` objects.  They
are attributes that belong to the step or test case.  If you run a step on its
own, no log file is created and logging happens to `stdout`/`stderr`.  If
you run a full test case, each step gets logged to its own log file within the
test case's work directory.  If you run a test suite, each test case and its
steps get logged to a file in the `case_output` directory of the suite's work
directory.

Although the logger will capture `print` statements, anywhere with a
`run()` function or the functions called inside that function, it is a good
idea to call `logger.info` instead of `print` to be explicit about the
expectation that the output may go to a log file.

Even more important, subprocesses that produce output should always be called
with {py:func}`mpas_tools.logging.check_call`, passing in the `logger` that
belongs to the step.  Otherwise, output will go to `stdout`/`stderr` even
when the intention is to write all output to a log file.  Whereas logging can
capture `stdout`/`stderr` to make sure that the `print` statements
actually go to log files when desired, there is no similar trick for
automatically capturing the output from direct calls to `subprocess`
functions.  Here is a code snippet from
{py:meth}`polaris.landice.tests.dome.setup_mesh.SetupMesh.run()`:

```python
from mpas_tools.logging import check_call


def run(self):
    ...
    section = config['dome']
    ...
    levels = section.getfloat('levels')
    args = ['create_landice_grid_from_generic_MPAS_grid.py',
            '-i', 'mpas_grid.nc',
            '-o', 'landice_grid.nc',
            '-l', levels]

    check_call(args, logger)
    ...
```

This example calls the script `create_landice_grid_from_generic_MPAS_grid.py`
from `mpas_tools` with several arguments, making use of the `logger`.
