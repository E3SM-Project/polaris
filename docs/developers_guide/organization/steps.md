(dev-steps)=

# Steps

Steps are the smallest units of work that can be executed on their own in
polaris.  All test cases are made up of 1 or more steps, and all steps
are set up into subdirectories inside of the work directory for the test case.
Typically, a user will run all steps in a test case but certain test cases may
prefer to have steps that are not run by default (e.g. a long forward
simulation or optional visualization) but which are available for a user to
manually alter and then run on their own.

A step is defined by a class that descends from {py:class}`polaris.Step`.
The child class must override the constructor and the
{py:meth}`polaris.Step.run()` method, and will sometimes also wish to override
the {py:meth}`polaris.Step.setup()` method, described below.

(dev-step-attributes)=

## Step attributes

As was the case for test cases, the base class {py:class}`polaris.Step` has a
large number of attributes that are useful at different stages (init, setup and
run) of the step.

Some attributes are available after calling the base class' constructor
`super().__init__()`.  These include:

`self.name`

: the name of the test case

`self.test_case`

: The test case this step belongs to

`self.test_group`

: The test group the test case belongs to

`self.component`

: The component the test group belongs to

`self.subdir`

: the subdirectory for the step

`self.path`

: the path within the base work directory of the step, made up of
  `component`, `test_group`, the test case's `subdir` and the
  step's `subdir`

`self.ntasks`

: the number of parallel (MPI) tasks the step would ideally use.  Too few
  cores are available on the system to run `ntasks * cpus_per_task`, the
  step will run on all available cores as long as this is not below
  `min_tasks * min_cpus_per_task`

`self.min_tasks`

: the number of MPI tasks the step requires.  If the system fewer than
  `min_tasks * min_cpus_per_task` cores, the step will fail

`self.cpus_per_task`

: The number of CPUs that each task runs with, or the total number of CPUs
  the step would ideally run with if python threading or multiprocessing is
  being used, in which case `ntasks = 1`

`self.min_cpus_per_task`

: The minimum number of CPUs that each task runs with, or the minimum total
  number of CPUs required for the step if python threading or multiprocessing
  is being used, in which case `ntasks = 1`.  If `ntasks > 1`,
  `min_cpus_per_task` much be the same as `cpus_per_task`.

`self.openmp_threads`

: the number of OpenMP threads the step will use

`self.cached`

: Whether to get all of the outputs for the step from the database of
  cached outputs for the component that this step belongs to

`self.run_as_subprocess`

: Whether to run this step as a subprocess, rather than just running
  it directly from the test case.  It is useful to run a step as a
  subprocess if there is not a good way to redirect output to a log
  file (e.g. if the step calls external code that, in turn, calls
  additional subprocesses).

  The default behavior when python code calls one of the `subprocess`
  functions is that the output goes to `stdout`/`stderr`
  (i.e. the terminal).  When python code outside of polaris
  (e.g. `jigsawpy`) calls a `subprocess` function (e.g. to call
  JIGSAW), that output goes to the terminal rather than a log file.
  For most output to `stdout`/`stderr` like `print()` statements,
  `check_call()` in MPAS-Tools employs a "trick" to redirect that
  output to a log file instead.  But that doesn't work with
  `subprocess` calls.  They continue to go to the terminal.  However,
  if we call a given polaris step as a subprocess while redirecting its
  output to a log file, we can prevent unwanted output from ending up
  in the terminal (the "outer" subprocess call gets redirected to a log
  file even when the inner one does not).

Another set of attributes is not useful until `setup()` is called by the
polaris framework:

`self.config`

: Configuration options for this test case, a combination of the defaults
  for the machine, core and configuration

`self.config_filename`

: The local name of the config file that `config` has been written to
  during setup and read from during run

`self.work_dir`

: The step's work directory, defined during setup as the combination
  of `base_work_dir` and `path`

`self.base_work_dir`

: The base work directory

These can be used to add additional input, output, namelist or streams files
based on config options that were not available during init, or which rely on
knowing the work directory.

Finally, a few attributes are available only when `run()` gets called by the
framework:

`self.inputs`

: a list of absolute paths of input files produced as part of setting up the
  step.  These input files must all exist at run time or the step will raise
  an exception

`self.outputs`

: a list of absolute paths of output files produced by this step and
  available as inputs to other test cases and steps.  These files must
  exist after the test has run or an exception will be raised

`self.logger`

: A logger for output from the step.  This gets passed on to other
  methods and functions that use the logger to write their output to the log
  file.

`self.log_filename`

: The name of a log file where output/errors from the step are being logged,
  or `None` if output is to stdout/stderr

The inputs and outputs should not be altered but they may be used to get file
names to read or write.

You can add other attributes to the child class that keeps track of information
that the step will need.

As an example,
{py:class}`polaris.landice.tests.dome.setup_mesh.SetupMesh` keeps track of the
mesh type as an attribute:

```python
from polaris.model_step import make_graph_file
from polaris.step import Step


class SetupMesh(Step):
    """
    A step for creating a mesh and initial condition for dome test cases

    Attributes
    ----------
    mesh_type : str
        The resolution or mesh type of the test case
    """
    def __init__(self, test_case, mesh_type):
        """
        Update the dictionary of step properties

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        mesh_type : str
            The resolution or mesh type of the test case
        """
        super().__init__(test_case=test_case, name='setup_mesh')
        self.mesh_type = mesh_type

        if mesh_type == 'variable_resolution':
            # download and link the mesh
            # the empty database is a trick for downloading to the root of
            # the local MALI file cache
            self.add_input_file(filename='mpas_grid.nc',
                                target='dome_varres_grid.nc', database='')

        self.add_output_file(filename='graph.info')
        self.add_output_file(filename='landice_grid.nc')
```

(dev-step-init)=

## constructor

The step's constructor (`__init__()` method) should call the base case's
constructor with `super().__init__()`, passing the name of the step, the
test case it belongs to, and possibly several optional arguments: the
subdirectory for the step (if not the same as the name), number of MPI tasks,
the minimum number of MPI tasks, the number of CPUs per task, the minimum
number of CPUs per task, the number of OpenMP threads, and (currently as
placeholders) the amount of memory the step is allowed to use.

Then, the step can add {ref}`dev-step-inputs-outputs` as well as
{ref}`dev-step-namelists-and-streams`, as described below.

As with the test case's {ref}`dev-test-case-init`, it is important that the
step's constructor doesn't perform any time-consuming calculations, download
files, or otherwise use significant resources because this function is called
quite often for every single test case and step: when test cases are listed,
set up, or cleaned up, and also when test suites are set up or cleaned up.
However, it is okay to add input, output, streams and namelist files to
the step by calling any of the following methods:

- {py:meth}`polaris.Step.add_input_file()`
- {py:meth}`polaris.Step.add_output_file()`
- {py:meth}`polaris.ModelStep.add_model_config_options()`
- {py:meth}`polaris.ModelStep.add_yaml_file()`
- {py:meth}`polaris.ModelStep.add_namelist_file()`
- {py:meth}`polaris.ModelStep.add_streams_file()`

Each of these functions just caches information about the the inputs, outputs,
namelists or streams files to be read later if the test case in question gets
set up, so each takes a negligible amount of time.

The following is from
{py:class}`polaris.ocean.tests.baroclinic_channel.forward.Forward()`:

```python
from polaris.model_step import ModelStep


class Forward(ModelStep):
    """
    A step for performing forward MPAS-Ocean runs as part of baroclinic
    channel test cases.

    Attributes
    ----------
    resolution : str
        The resolution of the test case
    """
    def __init__(self, test_case, resolution, name='forward', subdir=None,
                 ntasks=1, min_tasks=None, openmp_threads=1, nu=None):
        """
        Create a new test case

        Parameters
        ----------
        test_case : polaris.TestCase
            The test case this step belongs to

        resolution : str
            The resolution of the test case

        name : str
            the name of the test case

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use

        nu : float, optional
            the viscosity (if different from the default for the test group)
        """
        self.resolution = resolution
        if min_tasks is None:
            min_tasks = ntasks
        super().__init__(test_case=test_case, name=name, subdir=subdir,
                         ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)
        self.add_namelist_file('polaris.ocean.tests.baroclinic_channel',
                               'namelist.forward')
        self.add_namelist_file('polaris.ocean.tests.baroclinic_channel',
                               'namelist.{}.forward'.format(resolution))
        if nu is not None:
            # update the viscosity to the requested value
            options = {'config_mom_del2': '{}'.format(nu)}
            self.add_model_config_options(options)

        # make sure output is double precision
        self.add_streams_file('polaris.ocean.streams', 'streams.output')

        self.add_streams_file('polaris.ocean.tests.baroclinic_channel',
                              'streams.forward')

        self.add_input_file(filename='init.nc',
                            target='../initial_state/ocean.nc')
        self.add_input_file(filename='graph.info',
                            target='../initial_state/culled_graph.info')

        self.add_output_file(filename='output.nc')
```

Several parameters are passed into the constructor (with defaults if they
are not included) and then passed on to the base class' constructor: `name`,
`subdir`, `ntasks`, `min_tasks`, `cpus_per_task`,
`min_cpus_per_task`, and `openmp_threads`.

Then, two files with modifications to the namelist options are added (for
later processing), and an additional config option is set manually via
a python dictionary of namelist options.

Then, a file with modifications to the default streams is also added (again,
for later processing).

Finally, two input and one output file are added.

(dev-step-constrain-resources)=

## constrain_resources()

The `constrain_resources()` method is used to update the `ntasks`,
`min_tasks`, `cpus_per_task`, and `min_cpus_per_task` attributes prior to
running the step, in case the user has modified these in the config options.
These performance-related attributes affect how the step runs and must be set
prior to runtime, whereas other options can be set within `runtime_setup()`.

`constrain_resources()` is called within
{py:func}`polaris.run.serial.run_tests()`, but can be overridden if desired.
The typical reason to override this function would be to get config options for
`ntasks`, `min_tasks`, `cpus_per_task`, etc. and set the corresponding
attributes.  Another reason might be to set these attributes using an algorithm
(e.g. based on the number of cells in the mesh used in the step.)
When overriding `constrain_resources`, it is important to also call the base
class' version of the method with `super().constrain_resources()`.

(dev-step-setup)=

## setup()

The `setup()` method is called when a user is setting up the step either
as part of a call to {ref}`dev-polaris-setup` or {ref}`dev-polaris-suite`.
As in {ref}`dev-step-init`, you can add input, output, streams and namelist
files to the step by calling any of the following methods:

- {py:meth}`polaris.Step.add_input_file()`
- {py:meth}`polaris.Step.add_output_file()`
- {py:meth}`polaris.ModelStep.add_model_config_options()`
- {py:meth}`polaris.ModelStep.add_yaml_file()`
- {py:meth}`polaris.ModelStep.add_namelist_file()`
- {py:meth}`polaris.ModelStep.add_streams_file()`

Set up should not do any major computations or any time-consuming operations
other than downloading files.  Time-consuming work should be saved for
`run()` whenever possible.

As an example, here is
{py:func}`polaris.ocean.tests.global_ocean.mesh.mesh.MeshStep.setup()`:

```python
def setup(self):
    """
    Set up the test case in the work directory, including downloading any
    dependencies.
    """
    # get the these properties from the config options
    config = self.config
    self.cpus_per_task = config.getint('global_ocean',
                                       'mesh_cpus_per_task')
    self.min_cpus_per_task = config.getint('global_ocean',
                                           'mesh_min_cpus_per_task')
```

Some parts of the mesh computation (creating masks for culling) are done using
python multiprocessing, so the `cpus_per_task` and `min_cpus_per_task`
attributes are set to appropriate values based on config options.

(dev-step-runtime-setup)=

## runtime_setup()

The `runtime_setup()` method is used to modify any behaviors of the step at
runtime, in the way that {py:meth}`polaris.TestCase.run()` was previously used.
This includes things like partitioning an MPAS mesh across processors and
computing a times step based on config options that might have been modified
by the user.  It must not include modifying the `ntasks`, `min_tasks`,
`cpus_per_task`, `min_cpus_per_task` or `openmp_threads` attributes.
These attributes must be altered by overriding
{ref}`dev-step-constrain-resources`.

(dev-step-run)=

## run()

Okay, we're ready to define how the step will run!

The contents of `run()` can vary quite a lot between steps.

In the `baroclinic_channel` test group, the `run()` method for
the `initial_state` step,
{py:meth}`polaris.ocean.tests.baroclinic_channel.initial_state.InitialState.run()`,
is quite involved:

```python
import xarray
import numpy

from mpas_tools.planar_hex import make_planar_hex_mesh
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull

from polaris.ocean.vertical import generate_grid
from polaris.step import Step


class InitialState(Step):
    ...
    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger

        section = config['baroclinic_channel']
        nx = section.getint('nx')
        ny = section.getint('ny')
        dc = section.getfloat('dc')

        dsMesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc, nonperiodic_x=False,
                                      nonperiodic_y=True)
        write_netcdf(dsMesh, 'base_mesh.nc')

        dsMesh = cull(dsMesh, logger=logger)
        dsMesh = convert(dsMesh, graphInfoFileName='culled_graph.info',
                         logger=logger)
        write_netcdf(dsMesh, 'culled_mesh.nc')

        section = config['baroclinic_channel']
        use_distances = section.getboolean('use_distances')
        gradient_width_dist = section.getfloat('gradient_width_dist')
        gradient_width_frac = section.getfloat('gradient_width_frac')
        bottom_temperature = section.getfloat('bottom_temperature')
        surface_temperature = section.getfloat('surface_temperature')
        temperature_difference = section.getfloat('temperature_difference')
        salinity = section.getfloat('salinity')
        coriolis_parameter = section.getfloat('coriolis_parameter')

        ds = dsMesh.copy()

        interfaces = generate_grid(config=config)

        bottom_depth = interfaces[-1]
        vert_levels = len(interfaces) - 1

        ds['refBottomDepth'] = ('nVertLevels', interfaces[1:])
        ds['refZMid'] = ('nVertLevels', -0.5 * (interfaces[1:] + interfaces[0:-1]))
        ds['vertCoordMovementWeights'] = xarray.ones_like(ds.refBottomDepth)

        xCell = ds.xCell
        yCell = ds.yCell

        xMin = xCell.min().values
        xMax = xCell.max().values
        yMin = yCell.min().values
        yMax = yCell.max().values

        yMid = 0.5*(yMin + yMax)
        xPerturbMin = xMin + 4.0 * (xMax - xMin) / 6.0
        xPerturbMax = xMin + 5.0 * (xMax - xMin) / 6.0

        if use_distances:
            perturbationWidth = gradient_width_dist
        else:
            perturbationWidth = (yMax - yMin) * gradient_width_frac

        yOffset = perturbationWidth * numpy.sin(
            6.0 * numpy.pi * (xCell - xMin) / (xMax - xMin))

        temp_vert = (bottom_temperature +
                     (surface_temperature - bottom_temperature) *
                     ((ds.refZMid + bottom_depth) / bottom_depth))

        frac = xarray.where(yCell < yMid - yOffset, 1., 0.)

        mask = numpy.logical_and(yCell >= yMid - yOffset,
                                 yCell < yMid - yOffset + perturbationWidth)
        frac = xarray.where(mask,
                            1. - (yCell - (yMid - yOffset)) / perturbationWidth,
                            frac)

        temperature = temp_vert - temperature_difference * frac
        temperature = temperature.transpose('nCells', 'nVertLevels')

        # Determine yOffset for 3rd crest in sin wave
        yOffset = 0.5 * perturbationWidth * numpy.sin(
            numpy.pi * (xCell - xPerturbMin) / (xPerturbMax - xPerturbMin))

        mask = numpy.logical_and(
            numpy.logical_and(yCell >= yMid - yOffset - 0.5 * perturbationWidth,
                              yCell <= yMid - yOffset + 0.5 * perturbationWidth),
            numpy.logical_and(xCell >= xPerturbMin,
                              xCell <= xPerturbMax))

        temperature = (temperature +
                       mask * 0.3 * (1. - ((yCell - (yMid - yOffset)) /
                                           (0.5 * perturbationWidth))))

        temperature = temperature.expand_dims(dim='Time', axis=0)

        layerThickness = xarray.DataArray(data=interfaces[1:] - interfaces[0:-1],
                                          dims='nVertLevels')
        _, layerThickness = xarray.broadcast(xCell, layerThickness)
        layerThickness = layerThickness.transpose('nCells', 'nVertLevels')
        layerThickness = layerThickness.expand_dims(dim='Time', axis=0)

        normalVelocity = xarray.zeros_like(ds.xEdge)
        normalVelocity, _ = xarray.broadcast(normalVelocity, ds.refBottomDepth)
        normalVelocity = normalVelocity.transpose('nEdges', 'nVertLevels')
        normalVelocity = normalVelocity.expand_dims(dim='Time', axis=0)

        ds['temperature'] = temperature
        ds['salinity'] = salinity * xarray.ones_like(temperature)
        ds['normalVelocity'] = normalVelocity
        ds['layerThickness'] = layerThickness
        ds['restingThickness'] = layerThickness
        ds['bottomDepth'] = bottom_depth * xarray.ones_like(xCell)
        ds['maxLevelCell'] = vert_levels * xarray.ones_like(xCell, dtype=int)
        ds['fCell'] = coriolis_parameter * xarray.ones_like(xCell)
        ds['fEdge'] = coriolis_parameter * xarray.ones_like(ds.xEdge)
        ds['fVertex'] = coriolis_parameter * xarray.ones_like(ds.xVertex)

        write_netcdf(ds, 'ocean.nc')
```

Without going into all the details of this method, it creates a mesh that
is periodic in x (but not y), then adds a vertical grid and an initial
condition to an {py:class}`xarray.Dataset`, which is then written out to
the file `ocean.nc`.

In the example `Forward` step we've been using, there is no run method at all
because we let its superclass `ModelStep` define an `args` attribute instead.
Rather than call the `run()` method, the command given by these arguments
will be run on the commandline.  This is capability important for supporting 
task parallelism, since each such command may need to run with its own set of
MPI, threading and memory resources.

To get a feel for different types of `run()` methods, it may be best to
explore different steps.

(dev-step-inputs-outputs)=

## inputs and outputs

Currently, steps run in sequence in the order they are added to the test case
(or in the order they appear in the test case's `steps_to_run` attribute.
There are plans to allow test cases and their steps to run in parallel in the
future. For this reason, we require that each step defines a list of the
absolute paths to all input files that could come from other steps (possibly in
other test cases) and all outputs from the step that might be used by other
steps (again, possibly in other test cases).  There is no harm in including
inputs to the step that do not come from other steps (e.g. files that will be
downloaded when the test case gets set up) as long as they are sure to exist
before the step runs.  Likewise, there is no harm in including outputs from the
step that aren't used by any other steps in any test cases as long as the step
will be sure to generate them.

The inputs and outputs need to be defined during init of either the step or
the test case, or in the step's `setup()` method because they are needed
before {ref}`dev-step-run` is called (to determine which steps depend on which
other steps).  Inputs are added with {py:meth}`polaris.Step.add_input_file()`
and outputs with {py:func}`polaris.Step.add_output_file()`.  Inputs may be
symbolic links to files in polaris, from the various databases on the
[LCRC server](https://web.lcrc.anl.gov/public/e3sm/polaris/),
downloaded from another source, or from another step.

Because the inputs and outputs need to be defined before the step runs, there
can be some cases to avoid.  The name of an output file should not depend on a
config option.  Otherwise, if the user changes the config option, the file
actually created may have a different name than expected, in which case the
step will fail.  This would be true even if a subsequent step would have been
able to read in the same config option and modify the name of the expected
input file.

Along the same lines, an input or output file name should not depend on data
from an input file that does not exist during {ref}`dev-step-setup`.  Since the
file does not exist, there is no way to read the file with the dependency
within {ref}`dev-step-setup` and determine the resulting input or output file
name.

Both of these issues have arisen for the
{ref}`dev-ocean-global-ocean-files-for-e3sm` from the
{ref}`dev-ocean-global-ocean` test group.  Output files are named using the
"short name" of the mesh in E3SM, which depends both on config options and on
the number of vertical levels, which is read in from a mesh file created in a
previous step.  For now, the outputs of this step are not used by any other
steps so it is safe to simply omit them, but this could become problematic in
the future if new steps are added that depend on
{ref}`dev-ocean-global-ocean-files-for-e3sm`.

{py:class}`polaris.Step` includes several methods for adding input, output,
namelist and streams files:

(dev-step-input)=

### Input files

Typically, a step will add input files with
{py:meth}`polaris.Step.add_input_file()` during init or in its `setup()`
method.  It is also possible to add inputs in the test case's
{ref}`dev-test-case-init`.

It is possible to simply supply the path to an input file as `filename`
without any other arguments to {py:meth}`polaris.Step.add_input_file()`.  In
this case, the file name is either an absolute path or a relative path with
respect to the step's work directory:

```python
def __init__(self, test_case):
    ...
    self.add_input_file(filename='../setup_mesh/landice_grid.nc')
```

This is not typically how `add_input_file()` is used because input files are
usually not directly in the step's work directory.

(dev-step-input-symlinks)=

### Symlinks to input files

The most common type of input file is the output from another step. Rather than
just giving the file name directly, as in the example above, the preference is
to place a symbolic link in the work directory.  This makes it much easier to
see if the file is missing (because symlink will show up as broken) and allows
you to refer to a short, local name for the file rather than its full path:

```python
import xarray

def __init__(self, test_case):
    ...
    self.add_input_file(filename='landice_grid.nc',
                        target='../setup_mesh/landice_grid.nc')

...

def run(step, test_suite, config, logger):
   ...
   with xarray.open_dataset('landice_grid.nc') as ds:
       ...
```

A symlink is not actually created when {py:meth}`polaris.Step.add_input_file()`
is called.  This will not happen until the step gets set up, after calling its
{ref}`dev-step-setup` method.

Sometimes you want to create a symlink to an input file in the work directory,
but the relative path between the target and the step's work directory
isn't very convenient to determine.  This may be because the name of the
subdirectory for this step or the target's step (or both) depends on
parameters.  For such cases, there is a `work_dir_target` argument that
allows you to give the path with respect to the base work directory (which is
not yet known at init). Here is an example taken from
{py:class}`polaris.ocean.tests.global_ocean.forward.ForwardStep`:

```python
def __init__(self, test_case, mesh, init, ...):
    mesh_path = mesh.mesh_step.path

    if mesh.with_ice_shelf_cavities:
        initial_state_target = '{}/ssh_adjustment/adjusted_init.nc'.format(
            init.path)
    else:
        initial_state_target = '{}/initial_state/initial_state.nc'.format(
            init.path)
    self.add_input_file(filename='init.nc',
                        work_dir_target=initial_state_target)
    self.add_input_file(
        filename='forcing_data.nc',
        work_dir_target='{}/initial_state/init_mode_forcing_data.nc'
                        ''.format(init.path))
    self.add_input_file(
        filename='graph.info',
        work_dir_target='{}/culled_graph.info'.format(mesh_path))
```

(dev-step-input-polaris)=

### Symlink to input files from polaris

Another common need is to symlink a data file from within the test group or
test case:

```python
from polaris.io import add_input_file


def __init__(self, test_case):
    ...
    self.add_input_file(
        filename='enthA_analy_result.mat',
        package='polaris.landice.tests.enthalpy_benchmark.A')
```

Here, we supply the name of the package that the file is in.  The polaris
framework will take care of figuring out where the package is located.

(dev-step-input-download)=

### Downloading and symlinking input files

Another type of input file is one that is downloaded and stored locally.
Typically, to save ourselves the time of downloading large files and to reduce
potential problems on systems with firewalls, we cache the downloaded files in
a location where they can be shared between users and reused over time.  These
"databases" are subdirectories of the core's database root on the
[LCRC server](https://web.lcrc.anl.gov/public/e3sm/polaris/).

To add an input file from a database, call
{py:meth}`polaris.Step.add_input_file()` with the `database` argument:

```python
self.add_input_file(
    filename='topography.nc',
    target='BedMachineAntarctica_v2_and_GEBCO_2022_0.05_degree_20220729.nc',
    database='bathymetry_database')
```

In this example from
{py:class}`polaris.ocean.tests.global_ocean.init.initial_state.InitialState()`,
the file `BedMachineAntarctica_v2_and_GEBCO_2022_0.05_degree_20220729.nc` is
slated for later downloaded from the
[Ocean bathymetry database](https://web.lcrc.anl.gov/public/e3sm/polaris/ocean/bathymetry_database/).
The file will be stored in the subdirectory `ocean/bathymetry_database`
of the path in the `database_root` config option in the `paths` section of
the config file.  The `database_root` option is set either by selecting one
of the {ref}`supported-machines` or in the user's config file.

You can also specify the `database_component` parameter to choose to get
files from a database belonging to another component, e.g.:

```python
self.add_input_file(filename='icePresent_QU60km_polar.nc',
                    target='icePresent_QU60km_polar.nc',
                    database='partition',
                    database_component='seaice'
```

It is also possible to download files directly from a URL and store them in
the step's working directory:

```python
step.add_input_file(
    filename='dome_varres_grid.nc',
    url='https://web.lcrc.anl.gov/public/e3sm/polaris/landice/dome_varres_grid.nc')
```

We recommend against this practice except for very small files.

(dev-step-input-copy)=

### Copying input files

In nearly all the cases discussed above, a symlink is created to the input
file, usually either from the `polaris` package or from one of the databases.
If you wish to copy the file instead of symlinking it (e.g. so a user can make
local modifications), simply add the keyword argument `copy=True` to any call
to `self.add_input_file()`:

```python
def __init__(self, test_case):
    ...
    self.add_input_file(filename='landice_grid.nc',
                        target='../setup_mesh/landice_grid.nc', copy=True)
```

In this case, a copy of `landice_grid.nc` will be made in the step's work
directory.

(dev-step-output)=

### Output files

We require that all steps provide a list of any output files that other steps
are allowed to use as inputs.  This helps us keep track of dependencies and
will be used in the future to enable steps to run in parallel as long as they
don't depend on each other.  Adding an output file is pretty straightforward:

```python
self.add_output_file(filename='output_file.nc')
```

{py:meth}`polaris.Step.add_output_file()` can be called in a step's
{ref}`dev-step-init`: or {ref}`dev-step-setup` method or (less commonly)
in the test case's {ref}`dev-test-case-init`.

The relative path in `filename` is with respect to the step's work directory,
and is converted to an absolute path internally before the step is run.

(dev-step-cached-output)=

### Cached output files

Many polaris test cases and steps are expensive enough that it can become
time consuming to run full workflows to produce meshes and initial conditions
in order to test simulations.  Therefore, polaris provides a mechanism for
caching the outputs of each step in a database so that they can be downloaded
and symlinked rather than being computed each time.

Cached output files are be stored in the `polaris_cache` database within each
component's space on that LCRC server (see {ref}`dev-step-input-download`).
If the "cached" version of a step is selected, as we will describe below, each
of the test case's outputs will have a corresponding "input" file added with
the `target` being a cache file on the LCRC server and the `filename` being
the output file.  Polaris uses the `cached_files.json` database to know
which cache files correspond to which step outputs.

A developer can indicate that polaris test suite includes steps with cached
outputs in two ways.  First, if all steps in a test case should have cached
output, the following notation should be used:

```none
ocean/global_ocean/QU240/mesh
    cached
ocean/global_ocean/QU240/PHC/init
    cached
```

That is, the word `cached` should appear after the test case on its own line.
The indentation is for visual clarity and is not required.

Second, ff only some steps in a test case should have cached output, they need
to be listed explicitly, as follows:

```none
ocean/global_ocean/QUwISC240/mesh
    cached: mesh
ocean/global_ocean/QUwISC240/PHC/init
    cached: initial_state ssh_adjustment
```

The line can be indented for visual clarity, but must begin with `cached:`,
followed by a list of steps separated by a single space.

Similarly, a user setting up test cases has two mechanisms for specifying which
test cases and steps should have cached outputs.  If all steps in a test case
should have cached outputs, the suffix `c` can be added to the test number:

```none
polaris setup -n 90c 91c 92 ...
```

In this example, test cases 90 and 91 (`mesh` and `init` test cases from
the `SOwISC12to60` global ocean mesh, in this case) are set up with cached
outputs in all steps and 92 (`performance_test`) is not.  This approach is
efficient but does not provide any control of which steps use cached outputs
and which do not.

A much more verbose approach is required if some steps use cached outputs and
others do not within a given test case.  Each test case must be set up on its
own with the `-t` and `--cached` flags as follows:

```none
polaris setup -t ocean/global_ocean/QU240/mesh --cached mesh ...
polaris setup -t ocean/global_ocean/QU240/PHC/init --cached initial_state ...
...
```

Cache files should be generated by first running the test case as normal, then
running the {ref}`dev-polaris-cache` command-line tool at the base of the work
directory, providing the names of the steps whose outputs should be added to
the cache.  The resulting `<component>_cached_files.json` should be copied
to `polaris/<component>/cached_files.json` in a polaris branch.

Calls to `polaris cache` must be made on Chrysalis or Anvil.  If outputs were
produced on another machine, they must be transferred to one of these two
machines before calling `polaris cache`.  File can be added manually to the
LCRC server and the `cached_files.json` databases but this is not
recommended.

More details on cached outputs are available in the compass design document
[Caching outputs from compass steps](https://mpas-dev.github.io/compass/latest/design_docs/cached_outputs.html).

(dev-step-dependencies)=

### Adding other steps as dependencies

In some circumstances, it is not feasible to know the output filenames at
when a step gets set up.  For example, the filename may depend on config
options that a user could change before running the step.  Or the filename
could depend on data read in from files or computed at runtime.  In such
circumstances, it is not feasible to specify the output filename with
{py:meth}`polaris.Step.add_output_file()`.  Nor can other steps that depend
on that output file as an input use {py:meth}`polaris.Step.add_input_file()`.

Under these circumstances, it is useful to be able to specify that a step
is a dependency of another (dependent) step.  This is accomplished by passing 
the  dependency to the step's {py:meth}`polaris.Step.add_dependency()` method 
either  during the creation of the dependent step, within the `configure()` 
method of  the parent test case, or in the `setup()` method of the dependent
step.  The  dependency does not need to belong to the same test case as the
dependent step.  But the dependent step will fail to run if the dependency
has not run.  Also all dependencies must be set up along with dependent steps
(even if they are not run by default, because they are added to the test case
with `run_by_default=False`).  This is because a user could modify which steps
they wish to run and all dependencies should be available if they do so.

When a step is added as a dependency, after it runs, its state will be stored
in a pickle file (see {ref}`dev-setup`) that contains any modifications to its
state during the run.  When the dependent step is run, the the state of
each dependency is "unpickled" along with the state of the step itself so that
the dependent step can make use of runtime updates to its dependencies.

```{note}
There is some non-negligible overhead involved in pickling and unpickling
dependencies so it is preferable to use file-based dependencies where possible.
```
