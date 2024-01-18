(dev-ocean-framework)=

# Ocean framework

The `ocean` component contains an ever expanding set of shared framework code.

(dev-ocean-model)=

## Model

### Running an E3SM component

Steps that run either Omega or MPAS-Ocean should descend from the
{py:class}`polaris.ocean.model.OceanModelStep` class.  This class descends
from {py:class}`polaris.ModelStep`, so there is a lot of relevant
discussion in {ref}`dev-model`.

#### YAML files vs. namelists and streams

In order to have the same tasks support Omega or MPAS-Ocean, we want
to be able to produce either the YAML config files used by Omega or the
namelists and streams files used by MPAS-Ocean.  To support both, we decided
that polaris would use Omega-style YAML files to configure all ocean tasks
and convert to MPAS-Ocean's namelists and streams files if needed when steps
get set up.

As a result, the `add_namelist_file()` and `add_streams_file()` methods should
not be used for ocean model steps (they will raise errors).

#### Mapping from Omega to MPAS-Ocean config options

As the Omega component is in very early stages of development, we don't yet
know whether Omega's config options will always have the same names as the
corresponding namelist options in MPAS-Ocean.  To support the possibility
that they are different, the 
{py:meth}`polaris.ocean.model.OceanModelStep.map_yaml_to_namelist()` method
can be used to translate names of Omega config options to their MPAS-Ocean
counterparts.

#### Setting MPI resources

The target and minimum number of MPI tasks (`ntasks` and `min_tasks`, 
respectively) are set automatically if `ntasks` and `min_tasks` have not
already been set explicitly.  In such cases, a subclass of `OceanModelStep`
must override the
{py:meth}`polaris.ocean.model.OceanModelStep.compute_cell_count()` method
to approximate the number of cells in the mesh, using a simple heuristic.

The algorithm for determining the resources is:

```python
# ideally, about 200 cells per core
self.ntasks = max(1, round(cell_count / goal_cells_per_core + 0.5))
# In a pinch, about 2000 cells per core
self.min_tasks = max(1, round(cell_count / max_cells_per_core + 0.5))
```

The config options `goal_cells_per_core` and `max_cells_per_core` in the
`[ocean]` seciton can be used to control how resources scale with the size of 
the planar mesh.  By default,  the number of MPI tasks tries to apportion 200 
cells to each core, but it will allow as many as 2000. 

### Setting time intervals in model config options

It is often useful to be able to convert a `float` time interval in days or
seconds to a model config option in the form `DDDD_HH:MM:SS.S`.  The
{py:func}`polaris.ocean.model.get_time_interval_string()` function will do this
for you.  For example, if you have `resolution` in km and a config `section`
with options `dt_per_km` (in s/km) and `run_duration` (in days), you can use
the function to get appropriate strings for filling in a template model config
file:
```python
from polaris.ocean.model import get_time_interval_string


dt_per_km = section.getfloat('dt_per_km')
dt_str = get_time_interval_string(seconds=dt_per_km * resolution)

run_duration = section.getfloat('run_duration')
run_duration_str = get_time_interval_string(days=run_duration)

output_interval = section.getfloat('output_interval')
output_interval_str = get_time_interval_string(days=output_interval)

replacements = dict(
    dt=dt_str,
    run_duration=run_duration_str,
    output_interval=output_interval_str
)

self.add_yaml_file(package, yaml_filename,
                   template_replacements=replacements)
```
where the YAML file might include:
```
omega:
  time_management:
    config_run_duration: {{ run_duration }}
  time_integration:
    config_dt: {{ dt }}
  streams:
    output:
      type: output
      filename_template: output.nc
      output_interval: {{ output_interval }}
      clobber_mode: truncate
      reference_time: 0001-01-01_00:00:00
      contents:
      - xtime
      - normalVelocity
      - layerThickness
```

(dev-ocean-framework-config)=

## Model config options and streams

The module `polaris.ocean.config` contains yaml files for setting model
config options and configuring streams.  These include things like setting
output to double precision, adjusting sea surface height in ice-shelf cavities, 
and outputting variables related to frazil ice and land-ice fluxes.


(dev-ocean-spherical-meshes)=

## Quasi-uniform and Icosahedral Spherical Meshes

Many ocean tasks support two types of meshes: `qu` meshes created with the 
{py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` step and `icos` meshes 
created with {py:class}`polaris.mesh.IcosahedralMeshStep`.  In general, the 
`icos` meshes are more uniform but the `qu` meshes are more flexible.  The 
`icos` meshes only support a fixed set of resolutions described in
{ref}`dev-spherical-meshes`.

The function {py:func}`polaris.ocean.mesh.spherical.add_spherical_base_mesh_step()`
returns a step for for a spherical `qu` or `icos` mesh of a given resolution 
(in km).  The step can be shared between tasks.

(dev-ocean-convergence)=

## Convergence Tests

Several tests that are in Polaris or which we plan to add are convergence
tests on {ref}`dev-ocean-spherical-meshes` and planar meshes.
The ocean framework includes shared config options and base classes for
forward and analysis steps that are expected to be useful across these tests.

The shared config options are:
```cfg
# config options for spherical convergence tests
[spherical_convergence]

# a list of icosahedral mesh resolutions (km) to test
icos_resolutions = 60, 120, 240, 480

# a list of quasi-uniform mesh resolutions (km) to test
qu_resolutions = 60, 90, 120, 150, 180, 210, 240

[convergence]

# Evaluation time for convergence analysis (in hours)
convergence_eval_time = 24.0

# Convergence threshold below which a test fails
convergence_thresh = 1.0

# Type of error to compute
error_type = l2

# config options for convergence forward steps
[convergence_forward]

# time integrator: {'split_explicit', 'RK4'}
time_integrator = RK4

# RK4 time step per resolution (s/km), since dt is proportional to resolution
rk4_dt_per_km = 3.0

# split time step per resolution (s/km), since dt is proportional to resolution
split_dt_per_km = 30.0

# the barotropic time step (s/km) for simulations using split time stepping,
# since btr_dt is proportional to resolution
btr_dt_per_km = 1.5

# Run duration in hours
run_duration = ${convergence:convergence_eval_time}

# Output interval in hours
output_interval = ${run_duration}
```
The first 2 are the default resolutions for icosahedral and quasi-uniform
base meshes, respectively.

The `convergence_eval_time` will generally be modified by each test case. The
`convergence_thresh` will also be modified by each test case, and will depend
on the numerical methods being tested. The `error_type` is the L2 norm by
default. The L-infty norm, `inf`, is also supported.

`time_integrator` will typically be overridden by the specific convergence
task's config options, and indicates which time integrator to use for the
forward run.  Depending on the time integrator, either `rk4_dt_per_km` or
`split_dt_per_km` will be used to determine an appropriate time step for each
mesh resolution (proportional to the cell size). For split time integrators,
`btr_dt_per_km` will be used to compute the barotropic time step in a similar
way.  The `run_duration` and `output_interval` are typically the same, and
they are given in hours.

Each convergence test can override these defaults with its own defaults by 
defining them in its own config file.  Convergence tests should bring in this
config file in their constructor or by adding them to a shared `config`.  The
options from the shared infrastructure should be added first, then those from 
its own config file to make sure they take precedence, e.g.:

```python
from polaris.config import PolarisConfigParser


def add_cosine_bell_tasks(component):
    for icosahedral, prefix in [(True, 'icos'), (False, 'qu')]:

        filepath = f'spherical/{prefix}/cosine_bell/cosine_bell.cfg'
        config = PolarisConfigParser(filepath=filepath)
        config.add_from_package('polaris.ocean.convergence',
                                'convergence.cfg')
        config.add_from_package('polaris.ocean.convergence.spherical',
                                'spherical.cfg')
        config.add_from_package('polaris.ocean.tasks.cosine_bell',
                                'cosine_bell.cfg')
```

In addition, the {py:class}`polaris.ocean.convergence.spherical.SphericalConvergenceForward`
step can serve as a parent class for forward steps in convergence tests.  This
parent class takes care of setting the time step based on the `dt_per_km`
config option and computes the approximate number of cells in the mesh, used
for determining the computational resources required. When convergence tests
are run on spherical meshes,
the {py:class}`polaris.ocean.convergence.spherical.SphericalConvergenceForward`
should be invoked and overrides the `compute_cell_count` method with a
heuristic appropriate for approximately uniform spherical meshes.  A
convergence test's `Forward` step should descend from this class like in this
example:

```python
from polaris.ocean.convergence.spherical import SphericalConvergenceForward


class Forward(SphericalConvergenceForward):
    """
    A step for performing forward ocean component runs as part of the cosine
    bell test case
    """

    def __init__(self, component, name, subdir, resolution, mesh, init):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        resolution : float
            The resolution of the (uniform) mesh in km

        mesh : polaris.Step
            The base mesh step

        init : polaris.Step
            The init step
        """
        package = 'polaris.ocean.tasks.cosine_bell'
        validate_vars = ['normalVelocity', 'tracer1']
        super().__init__(component=component, name=name, subdir=subdir,
                         resolution=resolution, mesh=mesh,
                         init=init, package=package,
                         yaml_filename='forward.yaml',
                         output_filename='output.nc',
                         validate_vars=validate_vars)
```
Each convergence test must define a YAML file with model config options, called
`forward.yaml` by default.  The `package` parameter is the location of this
file within the Polaris code (using python package syntax).  Although it is
not used here, the `options` parameter can be used to pass model config options
as a python dictionary so that they are added to with 
{py:meth}`polaris.ModelStep.add_model_config_options()`. The
`output_filename` is an output file that will have fields to validate and
analyze.  The `validate_vars` are a list of variables to compare against a
baseline (if one is provided), and can be `None` if baseline validation should
not be performed.

The `mesh` step should be created with the function described in
{ref}`dev-ocean-spherical-meshes`, and the `init` step should produce a file
`init.nc` that will be the initial condition for the forward run.

The `forward.yaml` file should be a YAML file with Jinja templating for the 
time integrator, time step, run duration and output interval, e.g.:
```
omega:
  time_management:
    config_run_duration: {{ run_duration }}
  time_integration:
    config_dt: {{ dt }}
    config_time_integrator: {{ time_integrator }}
  split_explicit_ts:
    config_btr_dt: {{ btr_dt }}
  streams:
    mesh:
      filename_template: init.nc
    input:
      filename_template: init.nc
    restart: {}
    output:
      type: output
      filename_template: output.nc
      output_interval: {{ output_interval }}
      clobber_mode: truncate
      reference_time: 0001-01-01_00:00:00
      contents:
      - xtime
      - normalVelocity
      - layerThickness
```
`ConvergenceForward` takes care of filling in the template based
on the associated config options (first at setup and again at runtime in case
the config options have changed).

In addition, the {py:class}`polaris.ocean.convergence.ConvergenceAnalysis`
step can serve as a parent class for analysis steps in convergence tests.  This
parent class computes the error norm for the output from each resolution's
forward step. It also produces the convergence plot.

This is an example of how a task's analysis step can descend from the parent
class:

```python
class Analysis(ConvergenceAnalysis):
    """
    A step for analyzing the output from the cosine bell test case
    """
    def __init__(self, component, resolutions, subdir, dependencies):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        convergence_vars = [{'name': 'tracer1',
                             'title': 'tracer1',
                             'zidx': 0}]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars)
```

Many tasks will also need to override the 
{py:meth}`polaris.ocean.convergence.ConvergenceAnalysis.exact_solution()` 
method. If not overridden, the analysis step will compute the difference of the 
output from the initial state.

In some cases, the child class will also need to override the 
{py:meth}`polaris.ocean.convergence.ConvergenceAnalysis.get_output_field()`
method if the requested field is not available directly from the output put
rather needs to be computed.  The default behavior is to read the requested
variable (the value associate the `'name'` key) at the time index closest to
the evaluation time specified by the `convergence_eval_time` config option.

(dev-ocean-framework-ice-shelf)=

## Ice Shelf Tasks

The `polaris.ocean.ice_shelf` module provides support for ice shelf tasks.

The {py:class}`polaris.ocean.ice_shelf.IceShelf` class can serve as a parent
class for ice shelf tests, such as
{py:class}`polaris.ocean.tasks.ice_shelf_2d.IceShelf2d`.

The {py:meth}`polaris.ocean.ice_shelf.IceShelf.setup_ssh_adjustment_steps()`
sets up `ssh_forward` and `ssh_adjustment` steps from the classes
{py:class}`polaris.ocean.ice_shelf.ssh_forward.SshForward`
{py:class}`polaris.ocean.ice_shelf.ssh_adjustment.SshAdjustment`.
The `ssh_adjustment` section of the config file sets the parameters for these
steps, as described in {ref}`ocean-ssh-adjustment`. It returns the last
`ssh_adjustment` step, which is typically used as the
initial state for subsequent forward steps.

(dev-ocean-framework-vertical)=

## Vertical coordinate

The `polaris.ocean.vertical` module provides support for computing general
vertical coordinates for MPAS-Ocean tasks.

The `polaris.ocean.vertical.grid_1d` module provides 1D vertical
coordinates.  To create 1D vertical grids, tasks should call
{py:func}`polaris.ocean.vertical.grid_1d.generate_1d_grid()` with the desired
config options set in the `vertical_grid` section (as described in
the User's Guide under {ref}`ocean-vertical`).

The z-level and z-star coordinates are also controlled by config options from
this section of the config file. The function
{py:func}`polaris.ocean.vertical.init_vertical_coord()` can be used to compute
`minLevelCell`, `maxLevelCell`, `cellMask`, `layerThickness`, `zMid`,
and `restingThickness` variables for {ref}`ocean-z-level` and
{ref}`ocean-z-star` coordinates using the `ssh` and `bottomDepth` as well
as config options from `vertical_grid`. The function
{py:func}`polaris.ocean.vertical.update_layer_thickness` can be used to update
`layerThickness` when either or both of `bottomDepth` and `ssh` have been
changed.

(dev-ocean-rpe)=

## reference (resting) potential energy (RPE)

The module `polaris.ocean.rpe` is used to compute the reference (or 
resting) potential energy for an entire model domain.  The RPE as given in
[Petersen et al. 2015](https://doi.org/10.1016/j.ocemod.2014.12.004) is:

$$
RPE = g \int_\Omega z \rho^*\left(z\right) dV
$$

where $\Omega$ is the domain and $\rho^*\left(z\right)$ is the sorted
density, which is horizontally constant and increases with depth.

The {py:func}`polaris.ocean.rpe.compute_rpe()` is used to compute the RPE as
a function of time in a series of one or more output files.  The RPE is stored
in `rpe.csv` and also returned as a numpy array for plotting and analysis.

## Visualization

The `polaris.ocean.viz` module provides functions for making plots that are
specific to the ocean component.

The `polaris.ocean.viz.transect` modules includes functions for computing
({py:func}`polaris.ocean.viz.compute_transect()`) and plotting
({py:func}`polaris.ocean.viz.plot_transect()`) transects through the ocean
from a sequence of x-y or latitude-longitude coordinates.  Currently, only
transects on xarray data arrays with dimensions `nCells` by `nVertLevels` are
supported.
