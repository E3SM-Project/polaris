(dev-validation)=

# Validation

Test cases should typically include validation of variables and/or timers.
This validation is a critical part of running test suites and comparing them
to baselines.

## Validating variables

The function {py:func}`polaris.validate.compare_variables()` can be used to
compare variables in a file with a given relative path (`filename1`) with
the same variables in another file (`filename2`) and/or against a baseline.

As a simple example:

```python
variables = ['temperature', 'salinity', 'layerThickness', 'normalVelocity']
compare_variables(variables, config, work_dir=testcase['work_dir'],
                  filename1='forward/output.nc')
```

In this case, comparison will only take place if a baseline run is provided
when the test case is set up (see {ref}`dev-polaris-setup` or
{ref}`dev-polaris-suite`), since the keyword argument `filename2` was not
provided.  If a baseline is provided, the 4 prognostic variables are compared
between the file `forward/output.nc` and the same file in the corresponding
location within the baseline.

Here is a slightly more complex example:

```python
variables = ['temperature', 'salinity', 'layerThickness', 'normalVelocity']
compare_variables(variables, config, work_dir=testcase['work_dir'],
                  filename1='4proc/output.nc',
                  filename2='8proc/output.nc')
```

In this case, we compare the 4 prognostic variables in `4proc/output.nc`
with the same in `8proc/output.nc` to make sure they are identical.  If
a baseline directory was provided, these 4 variables in each file will also be
compared with those in the corresponding files in the baseline.

By default, the comparison will only be performed if both the `4proc` and
`8proc` steps have been run (otherwise, we cannot be sure the data we want
will be available).  If one of the steps was not run (if the user is running
steps one at a time or has altered the `steps_to_run` config option to remove
some steps), the function will skip validation, logging a message that
validation was not performed because of the missing step(s).  You can pass
the keyword argument `skip_if_step_not_run=False` to force validation to run
(and possibly to fail because the output is not available) even if the user did
not run the step involved in the validation.

In any of these cases, if comparison fails, the failure is stored in the
`validation` attribute of the test case, and a `ValueError` will be raised
later by the framework, terminating execution of the test case.

If `quiet=False`, typical output will look like this:

```none
Beginning variable comparisons for all time levels of field 'temperature'. Note any time levels reported are 0-based.
    Pass thresholds are:
       L1: 0.00000000000000e+00
       L2: 0.00000000000000e+00
       L_Infinity: 0.00000000000000e+00
0:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
1:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
2:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
 ** PASS Comparison of temperature between /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc and
    /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc
Beginning variable comparisons for all time levels of field 'salinity'. Note any time levels reported are 0-based.
    Pass thresholds are:
       L1: 0.00000000000000e+00
       L2: 0.00000000000000e+00
       L_Infinity: 0.00000000000000e+00
0:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
1:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
2:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
 ** PASS Comparison of salinity between /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc and
    /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc
Beginning variable comparisons for all time levels of field 'layerThickness'. Note any time levels reported are 0-based.
    Pass thresholds are:
       L1: 0.00000000000000e+00
       L2: 0.00000000000000e+00
       L_Infinity: 0.00000000000000e+00
0:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
1:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
2:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
 ** PASS Comparison of layerThickness between /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc and
    /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc
Beginning variable comparisons for all time levels of field 'normalVelocity'. Note any time levels reported are 0-based.
    Pass thresholds are:
       L1: 0.00000000000000e+00
       L2: 0.00000000000000e+00
       L_Infinity: 0.00000000000000e+00
0:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
1:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
2:  l1: 0.00000000000000e+00  l2: 0.00000000000000e+00  linf: 0.00000000000000e+00
 ** PASS Comparison of normalVelocity between /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc and
    /home/xylar/data/mpas/test_nightly_latest/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc
```

If `quiet=True` (the default), there is only an indication that the
comparison passed for each variable:

```none
temperature          Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

salinity             Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

layerThickness       Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

normalVelocity       Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

temperature          Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

salinity             Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

layerThickness       Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

normalVelocity       Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/1thread/output.nc

temperature          Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

salinity             Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

layerThickness       Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

normalVelocity       Time index: 0, 1, 2
  PASS /home/xylar/data/mpas/test_20210616/further_validation/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc

       /home/xylar/data/mpas/test_20210616/baseline/ocean/baroclinic_channel/10km/threads_test/2thread/output.nc
```

By default, the function checks to make sure `filename1` and, if provided,
`filename2` are output from one of the steps in the test case.  In general,
validation should be performed on outputs of the steps in this test case that
are explicitly added with {py:meth}`polaris.Step.add_output_file()`.  This
check can be disabled by setting `check_outputs=False`.

## Norms

In the unlikely circumstance that you would like to allow comparison to pass
with non-zero differences between variables, you can supply keyword arguments
`l1_norm`, `l2_norm` and/or `linf_norm` to give the desired maximum
values for these norms, above which the comparison will fail, raising a
`ValueError`.  These norms only affect the comparison between `filename1`
and `filename2`, not with the baseline (which always uses 0.0 for these
norms).  If you do want certain norms checked, you can pass their value as
`None`.

If you want different nonzero norm values for different variables,
the easiest solution is to call {py:func}`polaris.validate.compare_variables()`
separately for each variable and  with different norm values specified.
{py:func}`polaris.validate.compare_variables()` can safely be called multiple
times without clobbering a previous result.  When you specify a nonzero norm,
you may want polaris to print the norm values it is using for comparison
when the results are printed.  To do so, use the optional `quiet=False`
argument.

## Validating timers

Timer validation is qualitatively similar to variable validation except that
no errors are raised, meaning that the user must manually look at the
comparison and make a judgment call about whether any changes in timing are
large enough to indicate performance problems.

Calls to {py:func}`polaris.validate.compare_timers()` include a list of MPAS
timers to compare and at least 1 directory where MPAS has been run and timers
for the run are available.

Here is a typical call:

```python
timers = ['time integration']
compare_timers(timers, config, work_dir, rundir1='forward')
```

Typical output will look like:

```none
Comparing timer time integration:
             Base: 0.92264
          Compare: 0.82317
   Percent Change: -10.781019682649793%
          Speedup: 1.1208377370409515
```
