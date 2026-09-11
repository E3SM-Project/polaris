(dev-validation)=

# Validation

Tasks should typically include validation of variables and/or timers.
This validation is a critical part of running suites and comparing them
to baselines.

To set up and run both sides of a baseline comparison automatically --
resolving two source trees, initializing submodules, building each side and
passing the baseline work directory on with `-b` -- see
{ref}`dev-benchmarking`.

## Validating variables against a baseline

The easiest type of validation you can add is against a baseline if one is
provided during setup (see {ref}`dev-polaris-setup` or
{ref}`dev-polaris-suite`).  To do this, simply add a list of variables in
the keyword argument `validate_vars` to the
:py:meth:`polaris.Step.add_output_file()` method.  As an example:

```python
from polaris import Step


class Init(Step):
    def __init__(self, task):
        super().__init__(task=task, name='init')

        self.add_output_file('initial_state.nc',
                             validate_vars=['temperature', 'salinity',
                                            'layerThickness'])
```

Here, we add `initial_state.nc` as an output of the `init` step, and indicated
that the variables `temperature`, `salinity`, and `layerThickness` should
be compared against a baseline, if one is provided, after the step as run.

## Validating variables

In addition to baseline validation, it is often useful to compare files between
steps of a run.  This is done by adding later step to perform the validation.
This validation step will use the function
{py:func}`polaris.validate.compare_variables()` to compare variables in a file
with a given relative path (`filename1`) with the same variables in another
file (`filename2`).

As a compact example of creating a validate step for a restart run:

```python
from polaris import Step
from polaris.validate import compare_variables

class Validate(Step):
    def __init__(self, task):
        super().__init__(task=task, name='validate')
        self.add_input_file(filename='output_full_run.nc',
                            target=f'../full_run/output.nc')
        self.add_input_file(filename='output_restart_run.nc',
                            target=f'../restart_run/output.nc')

    def run(self):
        super().run()
        variables = ['temperature', 'salinity', 'layerThickness',
                     'normalVelocity']
        all_pass = compare_variables(variables,
                                     filename1='output_full_run.nc',
                                     filename2='output_restart_run.nc',
                                     logger=self.logger)
        if not all_pass:
            raise ValueError('Validation failed comparing outputs between '
                             'full_run and restart_run')

```

The 2 files `../full_run/output.nc` and `../restart_run/output.nc` are
symlinked locally and compared to make sure the variables `temperature`,
`salinity`, `layerThickness`, and `normalVelocity` are identical between the
two.

By default, the output is "quiet".  If you set `quiet=False`, typical output
will look like this:

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

## Norms

In circumstance where you would like to allow comparison to pass with non-zero
differences between variables, you can supply keyword arguments
`l1_norm`, `l2_norm` and/or `linf_norm` to give the desired maximum
values for these norms, above which the comparison will fail, raising a
`ValueError`.  If you do want certain norms checked, you can pass their value as
`None`.

If you want different nonzero norm values for different variables,
the easiest solution is to call {py:func}`polaris.validate.compare_variables()`
separately for each variable and with different norm values specified.
You will need to "and" together the results from calling
{py:func}`polaris.validate.compare_variables()`.  When you specify a nonzero
norm, you may want polaris to print the norm values it is using for comparison
when the results are printed.  To do so, use the optional `quiet=False`
argument.

## Datasets

In some cases, a comparison cannot be made directly between the datasets loaded
from the two files to be compared. Instead, the datasets require manipulation
for some reason. Currently, this is the case for datasets from the Omega model,
which need to have their variables renamed to the MPAS-Ocean names for use in
Polaris.  The `ds1` and `ds2` keyword arguments are used to supply datasets
corresponding to `filename1` and `filename2`, respectively, in such
circumstances.

# Property checks

For some output files, you may wish to run checks of certain properties such as
conservation of mass or energy. Currently, only conservation checks for the
ocean are available.

To run property checks, pass a list of properties as the keyword argument
`check_properties` to the {py:meth}`polaris.Step.add_output_file()` method.
As an example:

```python
from polaris import Step


class Forward(OceanModelStep):
    def __init__(self, task):
        super().__init__(task=task, name='forward')

        self.add_input_file(
            filename='mesh.nc', target='../init/culled_mesh.nc'
        )
        self.add_output_file('output.nc',
                             check_properties=['mass conservation'])
```

## Conservation checks

Mass, salt, tracer and energy conservation checks are available for ocean
model output.  A check fails if the relative error in the budget exceeds the
tolerance given in `polaris/ocean/ocean.cfg`:

```cfg
# Options related the ocean component
[ocean]

# Tolerance for mass conservation, normalized by total mass
mass_conservation_tolerance = 1e-14

# Tolerance for salt conservation, normalized by total salt
salt_conservation_tolerance = 1e-14

# Tolerance for tracer conservation, normalized by total tracer value
tracer_conservation_tolerance = 1e-14

# Tolerance for thermal energy conservation, normalized by total energy
energy_conservation_tolerance = 1e-14
```

A failed check does not currently fail its step or task.  The result is
logged and recorded, and nothing else acts on it.  Whether that should
change, and what the tolerances should be, is under discussion in
[issue #753](https://github.com/E3SM-Project/polaris/issues/753).

As shown in the previous example, we have added a mesh file with the name
'mesh.nc' because conservation checks require the area of cells.

Each call to {py:meth}`polaris.Step.add_output_file()` adds a single
conservation comparison, defined by the keyword arguments
`check_properties_baseline` (either `'init'` for the initial condition or a
time index in the output file) and `check_properties_time_index_end` (the
time index in the output file at the end of the comparison).  To check
conservation over more than one time interval of the same output file, call
{py:meth}`polaris.Step.add_property_check()` once per interval:

```python
self.add_output_file('output.nc')
# between the initial condition and the first time step
self.add_property_check('output.nc', ['mass conservation'],
                        baseline='init', time_index_end=0)
# between the last two time steps
self.add_property_check('output.nc', ['mass conservation'],
                        baseline=-2, time_index_end=-1)
```

The surface forcing fluxes are accumulated over the duration of each
comparison and used as the expected change in the corresponding budget.

The results of the checks are written to `property_check_passed.log` (which
lists the properties that passed) or `property_check_failed.log` (which lists
the properties that failed along with the relative error and the relative
error tolerance) in the step's work directory.  The full details of every
check are also written to `property_check_results.json` and stored in the
step's `property_check_results` attribute, so that other steps can summarize
them.

(dev-cf-check)=

# CF compliance checks

A step can have its output files checked for compliance with the
[CF conventions](https://cfconventions.org/) after it runs, using the
[CF checker](https://github.com/cedadev/cf-checker) (`cfchecks`).  A file
passes when the checker reports no errors; warnings and informational
messages go to the step's log but do not fail the check.  Unlike a property
check, a failed CF check fails the task, so a suite cannot pass while a
model writes non-compliant metadata.

To opt in, call {py:meth}`polaris.Step.add_cf_check()` with each file to
check.  A glob pattern stands for a series of files with the same metadata,
such as a time series from one output stream, so only its first match is
checked:

```python
self.add_cf_check('output.nc')
self.add_cf_check('restarts/rst.*.nc')
```

A step that only knows its output files at run time can opt in with no
filename and add the files in an override of
{py:meth}`polaris.Step.check_cf()` before calling the base-class method.
{py:class}`polaris.ocean.model.OceanModelStep` does this for Omega: every
step running Omega checks the first file of each stream in write mode in its
`omega.yml`.  MPAS-Ocean output is not checked.  Omega writes the model
start time as the origin of the `time` variable's units, and udunits rejects
a year-0 origin, so a task that starts in year 0 cannot pass the check.

The checker needs the CF standard-name, area-type and region-name tables.
Their versions are pinned in the `[cf]` section of `default.cfg`, so a table
update cannot change what a check reports, and each is downloaded once per
machine into the `cf/tables` database and linked into the step:

```cfg
# Options for checking netCDF files for CF compliance
[cf]

# Versions of the CF standard-name, area-type and region-name tables, pinned
# so that a table update cannot change what a check reports
standard_name_table_version = 94
area_type_table_version = 13
region_name_table_version = 5
```

The result of the check is written to `cf_check_passed.log` or
`cf_check_failed.log` (which lists the errors for each failing file) in the
step's work directory and stored in the step's `cf_check_results` attribute.
When a suite runs, each step that ran a check gets a `CF compliance` line
next to its property checks and baseline comparison, and tasks that failed
the check are listed in the suite's pull-request summary.
