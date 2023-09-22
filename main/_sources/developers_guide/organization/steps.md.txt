(dev-steps)=

# Steps

Steps are the smallest units of work that can be executed on their own in
polaris.  All tasks are made up of 1 or more steps, and all steps
are set up into subdirectories inside of the work directory for the component.
Shared steps should reside somewhere in the work directory above (or possibly
inside of) all tasks that share the steps.  Steps that belong to only one
task should be inside of that task's work directory. Typically, a user will run
all steps in a task but certain tasks may prefer to have steps that are not run
by default (e.g. a long forward simulation or optional visualization) but which
are available for a user to manually alter and then run on their own.

A step is defined by a class that descends from {py:class}`polaris.Step`.
The child class must override the constructor and must also either override the
{py:meth}`polaris.Step.run()` method or define the `args` attribute.  It will 
sometimes also wish to override the {py:meth}`polaris.Step.setup()` method, 
described below.

(dev-step-attributes)=

## Step attributes

As was the case for tasks, the base class {py:class}`polaris.Step` has a
large number of attributes that are useful at different stages (init, setup and
run) of the step.

Some attributes are available after calling the base class' constructor
`super().__init__()`.  These include:

`self.name`

: the name of the step

`self.component`

: The component the step belongs to

`self.subdir`

: the subdirectory for the step within the component

`self.path`

: the path within the base work directory of the step, made up of
  the name of the component and the step's `subdir`

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

`self.max_memory`

: An aspirational attribute that will be used in the future to indicate the 
  amount of memory that the step is allowed to use in MB

`self.cached`

: Whether to get all of the outputs for the step from the database of
  cached outputs for the component that this step belongs to

`self.run_as_subprocess`

: Whether to run this step as a subprocess, rather than just running
  it directly from the task.  It is useful to run a step as a
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

`self.dependencies`

: A dictionary of steps that this step depends on (i.e. it can't run until they
  have finished). Dependencies are used when the names of the files produced by
  the dependency aren't known at setup (e.g. because they depend on config 
  options or data read in from files). If the names of this step's input files
  are known at setup, it is sufficient (and preferable) to indicate that an 
  output file from another step is an input of this step to establish a 
  dependency.

`self.is_dependency`

: Whether this step is the dependency of one or more other steps

`self.args`

: A list of command-line arguments to call in parallel.  This attribute should
  be defined as an alternative to overriding the `run()`.  `args` should not
  include calls to a parallel executable like `srun` or the associated flags
  for number of MPI tasks, nodes, etc., since these will be added internally by
  Polaris.

Another set of attributes is not useful until `setup()` is called by the
polaris framework:

`self.config`

: Configuration options for this task, a combination of the defaults
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
  available as inputs to other tasks and steps.  These files must
  exist after the test has run or an exception will be raised

`self.logger`

: A logger for output from the step.  This gets passed on to other
  methods and functions that use the logger to write their output to the log
  file.

`self.log_filename`

: The name of a log file where output/errors from the step are being logged,
  or `None` if output is to stdout/stderr

`self.machine_info`

: Information about E3SM supported machines

The inputs and outputs should not be altered but they may be used to get file
names to read or write.

Some attributes are also used by the framework to validate variables in
output files against a baseline in one is provided:

`self.baseline_dir`

: Location of the same step within the baseline work directory, for use in 
  comparing variables and timers

`self.validate_vars`

: A list of variables for each output file for which a baseline comparison 
  should be performed if a baseline run has been provided. The baseline 
  validation is performed after the step has run.

You can add other attributes to the child class that keeps track of information
that the step will need.

As an example,
{py:class}`polaris.landice.tasks.dome.setup_mesh.SetupMesh` keeps track of the
mesh type as an attribute:

```python
from polaris import Step


class SetupMesh(Step):
    """
    A step for creating a mesh and initial condition for dome tasks

    Attributes
    ----------
    mesh_type : str
        The resolution or mesh type of the task
    """
    def __init__(self, component, mesh_type):
        """
        Update the dictionary of step properties

        Parameters
        ----------
        component : polaris.Component
            The component this step belongs to

        mesh_type : str
            The resolution or mesh type of the task
        """
        super().__init__(component=component, name='setup_mesh')
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

The step's constructor (`__init__()` method) should call the base class'
constructor with `super().__init__()`, passing the name of the step, the
task it belongs to, and possibly several optional arguments: the
subdirectory for the step (if not the same as the name), number of MPI tasks,
the minimum number of MPI tasks, the number of CPUs per task, the minimum
number of CPUs per task, the number of OpenMP threads, and (currently as
placeholders) the amount of memory the step is allowed to use.

Then, the step can add {ref}`dev-step-inputs-outputs` as well as
{ref}`dev-step-namelists-and-streams`, as described below.

As with the task's {ref}`dev-task-init`, it is important that the
step's constructor doesn't perform any time-consuming calculations, download
files, or otherwise use significant resources because this function is called
quite often for every single task and step: when tasks are listed,
set up, or cleaned up, and also when suites are set up or cleaned up.
However, it is okay to add input, output, streams and namelist files to
the step by calling any of the following methods:

- {py:meth}`polaris.Step.add_input_file()`
- {py:meth}`polaris.Step.add_output_file()`
- {py:meth}`polaris.ModelStep.add_model_config_options()`
- {py:meth}`polaris.ModelStep.add_yaml_file()`
- {py:meth}`polaris.ModelStep.add_namelist_file()`
- {py:meth}`polaris.ModelStep.add_streams_file()`

Each of these functions just caches information about the the inputs, outputs,
namelists, streams or YAML files to be read later if the task in question gets
set up, so each takes a negligible amount of time.

The following is from
{py:class}`polaris.ocean.tasks.baroclinic_channel.forward.Forward()`:

```python
from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward ocean component runs as part of baroclinic
    channel tasks.

    Attributes
    ----------
    resolution : float
        The resolution of the task in km

    dt : float
        The model time step in seconds

    btr_dt : float
        The model barotropic time step in seconds

    run_time_steps : int or None
        Number of time steps to run for
    """
    def __init__(self, component, resolution, name='forward', subdir=None,
                 indir=None, ntasks=None, min_tasks=None, openmp_threads=1,
                 nu=None, run_time_steps=None):
        """
        Create a new task

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the task in km

        name : str
            the name of the task

        subdir : str, optional
            the subdirectory for the step.  If neither this nor ``indir``
             are provided, the directory is the ``name``

        indir : str, optional
            the directory the step is in, to which ``name`` will be appended

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
            the viscosity (if different from the default for baroclinic channel
            tests)

        run_time_steps : int, optional
            Number of time steps to run for
        """
        self.resolution = resolution
        self.run_time_steps = run_time_steps
        super().__init__(component=component, name=name, subdir=subdir,
                         indir=indir, ntasks=ntasks, min_tasks=min_tasks,
                         openmp_threads=openmp_threads)

        if nu is not None:
            # update the viscosity to the requested value
            self.add_model_config_options(options=dict(config_mom_del2=nu))

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_input_file(filename='initial_state.nc',
                            target='../../init/initial_state.nc')
        self.add_input_file(filename='graph.info',
                            target='../../init/culled_graph.info')

        self.add_yaml_file('polaris.ocean.tasks.baroclinic_channel',
                           'forward.yaml')

        self.add_output_file(
            filename='output.nc',
            validate_vars=['temperature', 'salinity', 'layerThickness',
                           'normalVelocity'])

        self.dt = None
        self.btr_dt = None
```

Several parameters are passed into the constructor (with defaults if they
are not included) and then passed on to the base class' constructor: `name`,
`subdir`, `indir`, `ntasks`, `min_tasks`, `cpus_per_task`,
`min_cpus_per_task`, and `openmp_threads`.  Additional parameters `nu` and
`run_time_steps` are used to determine settings for running the model.

Then, two yaml files with modifications to the model config options are added 
(for later processing).  An additional model config option, `config_mom_del2` 
is set manually via a python dictionary of namelist options.

Additionally, two input and one output file are added.  By providing
`validate_vars` to {py:meth}`polaris.Step.add_output_file()`, validation of
these 4 variables in the `output.nc` output file will automatically be
performed after the step has run if a baseline was provided as part of the call
to {ref}`dev-polaris-setup`.

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
{py:func}`polaris.ocean.tasks.global_ocean.mesh.mesh.MeshStep.setup()`:

```python
def setup(self):
    """
    Set up the task in the work directory, including downloading any
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

(dev-step-constrain-resources)=

## constrain_resources()

The `constrain_resources()` method is used to update the `ntasks`,
`min_tasks`, `cpus_per_task`, and `min_cpus_per_task` attributes prior to
running the step, in case the user has modified these in the config options.
These performance-related attributes affect how the step runs and must be set
prior to runtime, whereas other options can be set within `runtime_setup()`.

The framework calls `constrain_resources()` within
{py:func}`polaris.run.serial.run_tasks()`, and a step can override this method
if desired, typically to get `ntasks`, `min_tasks`, `cpus_per_task`, etc. from 
config options or compute them using an algorithm and set the corresponding 
attributes. When overriding `constrain_resources`, it is important to also call
the base class' version of the method with `super().constrain_resources()`.

The names of the resources are related to the
[Slurm](https://slurm.schedmd.com/srun.html) naming conventions:

`ntasks`

: The target number of MPI tasks that a step will use if the resources 
  are available.

`min_tasks`

: The minimum number of MPI tasks for a step.  If too few resources are
  available, the step will not run.

`cpus_per_task`

: If `ntasks > 1`, this is typically a number of threads used by each
  MPI task (e.g. with OpenMP threading).  If `ntasks == 1`, this may
  be the number of target cores used in on-node parallelism like python or
  c++ threading, or python multiprocessing.  `cpus_per_task` will
  automatically be constrained to be less than or equal to the number of cores on a node
  (and the total available cores).  So it may be appropriate to set it to a
  high value appropriate for machines with large nodes, knowing that it will
  be constrained to fit on one node.

For MPI applications without threading, `cpus_per_task` will always be
`1`, the default.

`min_cpus_per_task`
: The minimum number of cores for on-node parallelism (threading,
  multiprocessing, etc.).  If too few resources are available, the step
  will fail with an error message.

(dev-step-runtime-setup)=

## runtime_setup()

The `runtime_setup()` method is used to modify any behaviors of the step at
runtime. This includes things like partitioning an MPAS mesh across processors
and computing a times step based on config options that might have been 
modified by the user.  It must not include modifying the `ntasks`, `min_tasks`,
`cpus_per_task`, `min_cpus_per_task` or `openmp_threads` attributes.
These attributes must be altered by overriding
{ref}`dev-step-constrain-resources`.

Typically, `runtime_setup()` will only be needed when the `args` attribute is
being defined instead of a `run()` method.  This lets you run a small amount
of python code before launching an command, often using MPI parallelism.

(dev-step-run)=

## run()

This method defines how the step will run. The contents of `run()` can vary 
quite a lot between steps.

In the baroclinic channel's `Init` step, the `run()` method,
{py:meth}`polaris.ocean.tasks.baroclinic_channel.init.Init.run()`,
is quite involved:

```python
import cmocean  # noqa: F401
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.vertical import init_vertical_coord
from polaris.viz import plot_horiz_field


class Init(Step):
    ...
    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger

        section = config['baroclinic_channel']
        resolution = self.resolution

        lx = section.getfloat('lx')
        ly = section.getfloat('ly')

        # these could be hard-coded as functions of specific supported
        # resolutions but it is preferable to make them algorithmic like here
        # for greater flexibility
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        dc = 1e3 * resolution

        ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc,
                                       nonperiodic_x=False,
                                       nonperiodic_y=True)
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, graphInfoFileName='culled_graph.info',
                          logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        section = config['baroclinic_channel']
        use_distances = section.getboolean('use_distances')
        gradient_width_dist = section.getfloat('gradient_width_dist')
        gradient_width_frac = section.getfloat('gradient_width_frac')
        bottom_temperature = section.getfloat('bottom_temperature')
        surface_temperature = section.getfloat('surface_temperature')
        temperature_difference = section.getfloat('temperature_difference')
        salinity = section.getfloat('salinity')
        coriolis_parameter = section.getfloat('coriolis_parameter')

        ds = ds_mesh.copy()
        x_cell = ds.xCell
        y_cell = ds.yCell

        bottom_depth = config.getfloat('vertical_grid', 'bottom_depth')

        ds['bottomDepth'] = bottom_depth * xr.ones_like(x_cell)
        ds['ssh'] = xr.zeros_like(x_cell)

        init_vertical_coord(config, ds)

        x_min = x_cell.min().values
        x_max = x_cell.max().values
        y_min = y_cell.min().values
        y_max = y_cell.max().values

        y_mid = 0.5 * (y_min + y_max)
        x_perturb_min = x_min + 4.0 * (x_max - x_min) / 6.0
        x_perturb_max = x_min + 5.0 * (x_max - x_min) / 6.0

        if use_distances:
            perturb_width = gradient_width_dist
        else:
            perturb_width = (y_max - y_min) * gradient_width_frac

        y_offset = perturb_width * np.sin(
            6.0 * np.pi * (x_cell - x_min) / (x_max - x_min))

        temp_vert = (bottom_temperature +
                     (surface_temperature - bottom_temperature) *
                     ((ds.refZMid + bottom_depth) / bottom_depth))

        frac = xr.where(y_cell < y_mid - y_offset, 1., 0.)

        mask = np.logical_and(y_cell >= y_mid - y_offset,
                              y_cell < y_mid - y_offset + perturb_width)
        frac = xr.where(mask,
                        1. - (y_cell - (y_mid - y_offset)) / perturb_width,
                        frac)

        temperature = temp_vert - temperature_difference * frac
        temperature = temperature.transpose('nCells', 'nVertLevels')

        # Determine y_offset for 3rd crest in sin wave
        y_offset = 0.5 * perturb_width * np.sin(
            np.pi * (x_cell - x_perturb_min) / (x_perturb_max - x_perturb_min))

        mask = np.logical_and(
            np.logical_and(y_cell >= y_mid - y_offset - 0.5 * perturb_width,
                           y_cell <= y_mid - y_offset + 0.5 * perturb_width),
            np.logical_and(x_cell >= x_perturb_min,
                           x_cell <= x_perturb_max))

        temperature = (temperature +
                       mask * 0.3 * (1. - ((y_cell - (y_mid - y_offset)) /
                                           (0.5 * perturb_width))))

        temperature = temperature.expand_dims(dim='Time', axis=0)

        normal_velocity = xr.zeros_like(ds_mesh.xEdge)
        normal_velocity, _ = xr.broadcast(normal_velocity, ds.refBottomDepth)
        normal_velocity = normal_velocity.transpose('nEdges', 'nVertLevels')
        normal_velocity = normal_velocity.expand_dims(dim='Time', axis=0)

        ds['temperature'] = temperature
        ds['salinity'] = salinity * xr.ones_like(temperature)
        ds['normalVelocity'] = normal_velocity
        ds['fCell'] = coriolis_parameter * xr.ones_like(x_cell)
        ds['fEdge'] = coriolis_parameter * xr.ones_like(ds_mesh.xEdge)
        ds['fVertex'] = coriolis_parameter * xr.ones_like(ds_mesh.xVertex)

        ds.attrs['nx'] = nx
        ds.attrs['ny'] = ny
        ds.attrs['dc'] = dc

        write_netcdf(ds, 'initial_state.nc')

        plot_horiz_field(ds, ds_mesh, 'temperature',
                         'initial_temperature.png')
        plot_horiz_field(ds, ds_mesh, 'normalVelocity',
                         'initial_normal_velocity.png', cmap='cmo.balance',
                         show_patch_edges=True)
```

Without going into all the details of this method, it creates a mesh that
is periodic in x (but not y), then adds a vertical grid and an initial
condition to an {py:class}`xarray.Dataset`, which is then written out to
the file `ocean.nc`.

In the example `Forward` step we showed above, there is no run method at all
because we let its superclass `ModelStep` define an `args` attribute instead.
Rather than call the `run()` method, the command given by these arguments
will be run on the commandline.  This is capability important for supporting 
task parallelism, since each such command may need to run with its own set of
MPI, threading and memory resources.

To get a feel for different types of `run()` methods, it may be best to
explore different steps that are already implemented in Polaris.

(dev-step-inputs-outputs)=

## inputs and outputs

Currently, steps run in sequence in the order they are added to the task
(or in the order they appear in the task's `steps_to_run` attribute).
There are plans to allow tasks and their steps to run in parallel in the
future. For this reason, we require that each step defines a list of the
absolute paths to all input files that could come from other steps (possibly in
other tasks) and all outputs from the step that might be used by other
steps (again, possibly in other tasks).  There is no harm in including
inputs to the step that do not come from other steps (e.g. files that will be
downloaded when the task gets set up) as long as they are sure to exist
before the step runs.  Likewise, there is no harm in including outputs from the
step that aren't used by any other steps as long as the step will be sure to 
generate them.

The inputs and outputs need to be defined during init of either the step or
the task, or in the step's `setup()` method because they are needed
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
{ref}`dev-ocean-global-ocean-files-for-e3sm` from
{ref}`dev-ocean-global-ocean` tasks.  Output files are named using the
"short name" of the mesh in E3SM, which depends both on config options and on
the number of vertical levels, which is read in from a mesh file created in a
previous step.  For now, the outputs of this step are not used by any other
steps so it is safe to simply omit them, but this could become problematic in
the future if new steps are added that depend on
{ref}`dev-ocean-global-ocean-files-for-e3sm`.  These steps would need to add
the appropriate shared step from `files_for_e3sm` as a dependency using
{py:meth}`polaris.Step.add_dependency()`.

{py:class}`polaris.Step` includes several methods for adding input, output,
namelist and streams files:

(dev-step-input)=

### Input files

Typically, a step will add input files with
{py:meth}`polaris.Step.add_input_file()` during init or in its `setup()`
method.  It is also possible to add inputs in the task's
{ref}`dev-task-init`.

It is possible to simply supply the path to an input file as `filename`
without any other arguments to {py:meth}`polaris.Step.add_input_file()`.  In
this case, the file name is either an absolute path or a relative path with
respect to the step's work directory:

```python
def __init__(self, task):
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

def __init__(self, task):
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
{py:class}`polaris.ocean.tasks.global_ocean.forward.ForwardStep`:

```python
def __init__(self, component, mesh, init):
    mesh_path = mesh.mesh_step.path

    if mesh.with_ice_shelf_cavities:
        initial_state_target = f'{init.path}/ssh_adjustment/adjusted_init.nc'
    else:
        initial_state_target = f'{init.path}/init/initial_state.nc'
    self.add_input_file(filename='init.nc',
                        work_dir_target=initial_state_target)
    self.add_input_file(
        filename='forcing_data.nc',
        work_dir_target=f'{init.path}/init/init_mode_forcing_data.nc')
    self.add_input_file(
        filename='graph.info',
        work_dir_target=f'{mesh_path}/culled_graph.info')
```

(dev-step-input-polaris)=

### Symlink to input files from polaris

Another common need is to symlink a data file from within the task or its
shared framework:

```python
def __init__(self, component):
    ...
    self.add_input_file(
        filename='enthA_analy_result.mat',
        package='polaris.landice.tasks.enthalpy_benchmark.A')
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
{py:class}`polaris.ocean.tasks.global_ocean.init.init.Init()`,
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
                    database_component='seaice')
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
def __init__(self, task):
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
{ref}`dev-step-init` or {ref}`dev-step-setup` method or (less commonly)
in the task's {ref}`dev-task-init`.

The relative path in `filename` is with respect to the step's work directory,
and is converted to an absolute path internally before the step is run.

You can specify a list of variables to validate against a baseline (if one
is provided) using the `validate_vars` attribute:

```python
self.add_output_file(
    filename='output.nc',
    validate_vars=['temperature', 'salinity', 'layerThickness',
                   'normalVelocity'])
```

If a baseline is provided during {ref}`dev-polaris-setup`, then after the step 
runs, the variables `temperature`, `salinity`, `layerThickness`, and
`normalVelocity` in the file `output.nc` will be checked against the same
variables in the same file in the baseline run to make sure they are identical.

(dev-step-cached-output)=

### Cached output files

Many polaris tasks and steps are expensive enough that it can become
time consuming to run full workflows to produce meshes and initial conditions
in order to test simulations.  Therefore, polaris provides a mechanism for
caching the outputs of each step in a database so that they can be downloaded
and symlinked rather than being computed each time.

Cached output files are be stored in the `polaris_cache` database within each
component's space on that LCRC server (see {ref}`dev-step-input-download`).
If the "cached" version of a step is selected, as we will describe below, each
of the task's outputs will have a corresponding "input" file added with
the `target` being a cache file on the LCRC server and the `filename` being
the output file.  Polaris uses the `cached_files.json` database to know
which cache files correspond to which step outputs.

A developer can indicate that polaris suite includes steps with cached
outputs in two ways.  First, if all steps in a task should have cached
output, the following notation should be used:

```none
ocean/global_ocean/QU240/mesh
    cached
ocean/global_ocean/QU240/PHC/init
    cached
```

That is, the word `cached` should appear after the task on its own line.
The indentation is for visual clarity and is not required.

Second, ff only some steps in a task should have cached output, they need
to be listed explicitly, as follows:

```none
ocean/global_ocean/QUwISC240/mesh
    cached: mesh
ocean/global_ocean/QUwISC240/PHC/init
    cached: init ssh_adjustment
```

The line can be indented for visual clarity, but must begin with `cached:`,
followed by a list of steps separated by a single space.

Similarly, a user setting up tasks has two mechanisms for specifying which
tasks and steps should have cached outputs.  If all steps in a task
should have cached outputs, the suffix `c` can be added to the test number:

```none
polaris setup -n 90c 91c 92 ...
```

In this example, tasks 90 and 91 (`mesh` and `init` tasks from
the `SOwISC12to60` global ocean mesh, in this case) are set up with cached
outputs in all steps and 92 (`performance_test`) is not.  This approach is
efficient but does not provide any control of which steps use cached outputs
and which do not.

A much more verbose approach is required if some steps use cached outputs and
others do not within a given task.  Each task must be set up on its
own with the `-t` and `--cached` flags as follows:

```none
polaris setup -t ocean/global_ocean/QU240/mesh --cached mesh ...
polaris setup -t ocean/global_ocean/QU240/PHC/init --cached init ...
...
```

Cache files should be generated by first running the task as normal, then
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
method of  the parent task, or in the `setup()` method of the dependent
step.  The  dependency does not need to belong to the same task as the
dependent step.  But the dependent step will fail to run if the dependency
has not run.  Also all dependencies must be set up along with dependent steps
(even if they are not run by default, because they are added to the task
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
