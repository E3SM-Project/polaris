(dev-ocean-framework)=

# Ocean framework

The `ocean` component contains an ever expanding set of shared framework code.

(dev-ocean-model)=

## Model

### Input and output from an E3SM component

Steps that write input files for or read output files from either Omega or
MPAS-Ocean should descend from the {py:class}`polaris.ocean.model.OceanIOStep`
class.  Methods in this class facilitate mapping between MPAS-Ocean variable
names (used in Polaris) and Omega variable names for tasks that will run Omega.

To map a dataset between MPAS-Ocean variable names and those appropriate for
the model being run, use the methods
{py:meth}`polaris.ocean.model.OceanIOStep.map_to_native_model_vars()` and
{py:meth}`polaris.ocean.model.OceanIOStep.map_from_native_model_vars()`. These
methods should be called in Polaris immediatly before writing out input files
and immediately after opening in output files, respectively. To make opening
and writing easier, we also provide
{py:meth}`polaris.ocean.model.OceanIOStep.write_model_dataset()` and
{py:meth}`polaris.ocean.model.OceanIOStep.open_model_dataset()`, which take
care of of the mapping in addition to writing and opening a dataset,
respectively. The `open_model_dataset()` method also supports reconstructing
normal vector components to their zonal and meridional equivalents by passing
a list of variable names to
{py:func}`mpas_tools.vector.reconstruct.reconstruct_variable()`, along with
the mesh and reconstruction coefficient files. On planar meshes, the "zonal"
and "meridional" components are the x and y components, respectively,
following the convention MPAS-Ocean uses for its own reconstruction (as of
`mpas_tools` 2.1.0, `reconstruct_variable()` follows this convention itself
when the mesh has `on_a_sphere = 'NO'`). In addition,
`open_model_dataset()` derives `PseudoThickness` from the ocean state when it
is not present in the dataset. This provides a way of using the same initial
conditions for MPAS-Ocean and Omega when the geometric thickness is the state
variable for MPAS-Ocean and the pseudo-thickness is the state variable for
Omega. It can also convert `temperature` and `salinity` to a requested
convention, so that analysis and visualization do not have to care which model
ran (see {ref}`dev-ocean-framework-tracer-conventions-on-read`). Similarly,
{py:meth}`polaris.ocean.model.OceanIOStep.write_initial_state_dataset()`
ensures that `SurfacePressure` is present in initial conditions written for
Omega, adding a spatially uniform field from the
`vertical_grid:surface_pressure` config option (zero by default) if it is not
already set.  `SurfacePressure` is a relative (gauge) surface pressure that is
required by Omega but not by MPAS-Ocean, so it is added only when the model is
Omega.  It is an Omega-only field with no MPAS-Ocean equivalent (MPAS-Ocean's
`surfacePressure` is an absolute pressure supplied by the coupler), so it is
deliberately not included in the
[mpaso_to_omega.yaml](https://github.com/E3SM-Project/polaris/blob/main/polaris/ocean/model/mpaso_to_omega.yaml)
variable map and keeps its Omega name.  Tasks that prescribe a spatially
varying surface pressure should set `SurfacePressure` themselves, in which case
it is left as-is.  As new variables that do have an MPAS-Ocean equivalent are
added to Omega, they should be added to the `variables` section in the
`mpaso_to_omega.yaml` file.

For standalone conversion of an existing MPAS-Ocean initial-condition file to
Omega format outside a Polaris task, see
{ref}`dev-ocean-convert-mpaso-ic-to-omega`.

#### Canonical staged files

The three files that flow through the ocean pipeline — horizontal mesh,
vertical coordinate, and initial state — have canonical local filenames
defined in the `[ocean_staged_files]` config section (in
`polaris/ocean/ocean.cfg`):

```ini
[ocean_staged_files]
horiz_mesh_filename = mesh.nc
vert_coord_filename = vert_coord.nc
init_filename = init.nc
```

These filenames are shared by all pipeline stages: init steps write them as
outputs, model steps link them as inputs, and viz/analysis steps also link
from upstream using the same names.

Both {py:class}`polaris.ocean.model.OceanIOStep` and
{py:class}`polaris.ocean.model.OceanModelStep` inherit these conveniences from
{py:class}`polaris.ocean.model.OceanModelFilesMixin`:

- **Getters** — `get_horiz_mesh_filename()`, `get_vert_coord_filename()`,
  `get_init_filename()` — read the current values from config.
- **Input-file registration** — `add_horiz_mesh_input_file(**kwargs)`,
  `add_vert_coord_input_file(filename=None, **kwargs)`,
  `add_init_input_file(**kwargs)` — all safe to call from `__init__()`.
  The model check is deferred to `process_inputs_and_outputs()`, so no
  `if model == 'omega':` guards are needed in `__init__()`.
  `add_vert_coord_input_file()` is a no-op for MPAS-Ocean when the default
  placeholder is used.  When an explicit `filename=` is given (for
  per-resolution files such as `'vert_coord_r04.nc'`), it must be called
  from `setup()` or later because `self.config` is required.

A typical viz or analysis step that reads vert-coord variables:

```python
class Viz(OceanIOStep):
    def __init__(self, component, indir, init):
        super().__init__(component=component, name='viz', indir=indir)
        self.add_input_file(filename='mesh.nc',
                            work_dir_target=f'{init.path}/culled_mesh.nc')
        self.add_input_file(filename='init.nc',
                            work_dir_target=f'{init.path}/init.nc')
        # registers vert_coord.nc for Omega; no-op for MPAS-Ocean
        self.add_vert_coord_input_file(
            work_dir_target=f'{init.path}/vert_coord.nc')
        self.add_input_file(filename='output.nc', target='../forward/output.nc')

    def run(self):
        ds_init = self.open_model_dataset('init.nc', self.config)
        # returns ds_init for MPAS-Ocean; opens vert_coord.nc for Omega
        ds_vert_coord = self.open_vert_coord_dataset(ds_init)
        ...
        compute_transect(
            ...,
            bottom_depth=ds_vert_coord.bottomDepth,
            min_level_cell=ds_vert_coord.minLevelCell - 1,
            max_level_cell=ds_vert_coord.maxLevelCell - 1,
        )
```

`open_vert_coord_dataset(ds_init, vert_coord_filename=None)` returns
the subset of variables associated with the veritcal coordinate taken from
`ds_init` for MPAS-Ocean (the vert-coord variables live in `init.nc`) and
opens the separate `vert_coord.nc` file for Omega, mapping
Omega variable names to MPAS-Ocean equivalents via `open_model_dataset()`.
Pass an explicit `vert_coord_filename=` when using per-resolution files
(e.g. from a `ConvergenceAnalysis` subclass).

### Running an E3SM component

Steps that run either Omega or MPAS-Ocean should descend from the
{py:class}`polaris.ocean.model.OceanModelStep` class.  This class descends
from {py:class}`polaris.ModelStep`, so there is a lot of relevant
discussion in {ref}`dev-model`.

If the graph partition file has been constructed prior to the ocean model step,
the path to the graph file should be provided in the `graph_target` argument
to the constructor {py:class}`polaris.ocean.model.OceanModelStep()`.

#### YAML files vs. namelists and streams

In order to have the same tasks support Omega or MPAS-Ocean, we want
to be able to produce either the YAML config files used by Omega or the
namelists and streams files used by MPAS-Ocean.  To support both, we decided
that polaris would use Omega-style YAML files to configure all ocean tasks
and convert to MPAS-Ocean's namelists and streams files if needed when steps
get set up.

As a result, the `add_namelist_file()` and `add_streams_file()` methods should
not be used for ocean model steps (they will raise errors).

#### Mapping from MPAS-Ocean to Omega config options

As the Omega component is in very early stages of development, it has far
fewer config options than MPAS-Ocean at present.  To complicate things further,
it is already clear that there will be config options in Omega without a
corresponding option in MPAS-Ocean (just as there are clearly many MPAS-Ocean
config options that don't exist in Omega).  As a result, we need a way to
support three categories of config options:

1. `ocean` config options available in both models (we use the MPAS-Ocean names
   for these and map to the Omega names),
2. `mpas-ocean` config options that only exist in MPAS-Ocean,
3. `omega` config options that only exist in Omega.

YAML files can have root-level sections with 1, 2 or all 3 of these
so-called `config_models`, as in the following example:

```
ocean:
  time_management:
    config_run_duration: {{ run_duration }}
  time_integration:
    config_dt: {{ dt }}
    config_time_integrator: {{ time_integrator }}

mpas-ocean:
  bottom_drag:
    config_bottom_drag_mode: implicit
    config_implicit_bottom_drag_type: constant
    config_implicit_constant_bottom_drag_coeff: 0.0
  manufactured_solution:
     config_use_manufactured_solution: true
  debug:
    config_disable_vel_hmix: true

Omega:
  Tendencies:
    VelDiffTendencyEnable: false
    VelHyperDiffTendencyEnable: false
```

When model config options are set in code, it is also important to specify
which `config_model` they apply to (`ocean`, `mpas-ocean` or `Omega`):
```python
self.add_model_config_options(options=dict(config_mom_del2=nu),
                              config_model='ocean')
```

We implement a mapping from the MPAS-Ocean names to the corresponding Omega
names for the `ocean` config options in the methods
{py:meth}`polaris.ocean.model.OceanModelStep.map_yaml_options()` and
{py:meth}`polaris.ocean.model.OceanModelStep.map_yaml_configs()`.
As new config options are added to Omega, they should be added to the
`config` section in the
[mpaso_to_omega.yaml](https://github.com/E3SM-Project/polaris/blob/main/polaris/ocean/model/mpaso_to_omega.yaml)
file. Note that `config_model='Omega'` must be capitalized since this is the
convention on the model name in Omega's own YAML files.

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
cpu_ntasks = max(1, 4 * round(cell_count / (4 * goal_cells_per_core)))
# In a pinch, about 2000 cells per core
cpu_min_tasks = max(1, 4 * round(cell_count / (4 * max_cells_per_core)))
```

The config options `goal_cells_per_core` and `max_cells_per_core` in the
`[ocean]` seciton can be used to control how resources scale with the size of
the planar mesh.  By default, the number of MPI tasks tries to apportion 200
cells to each core, but it will allow as many as 2000.

For Omega on GPU-capable parallel configs (`gpus_per_node > 0`), dynamic
sizing switches to GPU-based targets and sets one GPU per MPI task:

```python
self.gpus_per_task = 1
self.min_gpus_per_task = 1
# ideally, about 8000 cells per GPU
self.ntasks = max(1, 4 * round(cell_count / (4 * goal_cells_per_gpu)))
# In a pinch, about 80000 cells per GPU
self.min_tasks = max(1, 4 * round(cell_count / (4 * max_cells_per_gpu)))
```

The corresponding `[ocean]` config options are `goal_cells_per_gpu` and
`max_cells_per_gpu`.

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
ocean:
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


(dev-ocean-framework-eos)=

## Equations of state (EOS)

Polaris ocean tasks use EOS utilities from the `polaris.ocean.eos` package.

The high-level APIs are {py:func}`polaris.ocean.eos.compute_density()` and
{py:func}`polaris.ocean.eos.compute_specvol()`.  These functions dispatch
based on `eos_type` in the `[ocean]` config section.

- `eos_type = constant` uses the linear EOS and calls
  {py:func}`polaris.ocean.eos.constant.compute_constant_density()`.
- `eos_type = linear` uses the linear EOS and calls
  {py:func}`polaris.ocean.eos.linear.compute_linear_density()`.
- `eos_type = teos-10` uses TEOS-10 and calls
  {py:func}`polaris.ocean.eos.teos10.compute_specvol()`, with density computed
  as the inverse of specific volume.

The constant EOS density is set by the config option `eos_constant_rhoref`.
The linear EOS coefficients and reference values are set with ocean config
options such as `eos_linear_alpha`, `eos_linear_beta`, `eos_linear_rhoref`,
`eos_linear_Tref`, and `eos_linear_Sref`.  TEOS-10 requires pressure to be
provided when calling the high-level EOS functions.

Tasks select an EOS by adding one of the shared config files from the
`polaris.ocean.eos` package to their shared config parser:

- `constant.cfg` sets `eos_type = constant` along with linear-EOS options
  that make the linear EOS constant.
- `linear.cfg` sets `eos_type = linear` along with default linear-EOS
  coefficients.
- `teos10.cfg` sets `eos_type = teos-10` and defines no linear-EOS
  options.

Forward steps created with `update_eos=True` call
{py:meth}`polaris.ocean.model.OceanModelStep.update_namelist_eos()`, which
translates `eos_type` (and, for the linear and constant EOS, the
`eos_linear_*` options) into model config options.  For `teos-10`,
MPAS-Ocean has no TEOS-10 option, so `config_eos_type` is set to `jm`
(Jackett-McDougall), the closest available nonlinear EOS; Omega receives
`teos-10` unchanged.  For `constant`, MPAS-Ocean similarly falls back to
its linear EOS with constant coefficients.

The two models also disagree about what the `temperature` and `salinity`
tracers mean under TEOS-10: Omega expects conservative temperature (CT)
and absolute salinity (SA) while MPAS-Ocean expects potential temperature
(PT) and practical salinity (SP).  For any other `eos_type` the models
apply the same algebraic formula, so the distinction is meaningless.

{py:func}`polaris.ocean.eos.convert_tracers()` converts between the two
conventions in either direction: `gsw.pt_from_CT()` and `gsw.SP_from_SA()`
going to the MPAS-Ocean convention, `gsw.CT_from_pt()` and
`gsw.SA_from_SP()` coming back.  It takes the pressure and the lon/lat
(in degrees) at which to convert, does not modify the dataset it is given,
and takes a `tracer_pairs` argument for converting variables other than
`temperature` and `salinity` (surface restoring fields, for example).
Cells where either tracer is NaN, such as those below the bathymetry, stay
NaN.  {py:func}`polaris.ocean.eos.convert_tracer_pair()` does the same for
tracers that are in hand rather than in a dataset.

Steps do not normally call either function themselves.  The framework
converts the tracers as it writes the initial state and, if asked, as it
opens a dataset (see {ref}`dev-ocean-framework-init-state` and
{ref}`dev-ocean-framework-tracer-conventions-on-read`).

Because TEOS-10 requires CT and SA,
{py:func}`polaris.ocean.eos.compute_density()` takes a
`tracer_convention` argument saying which convention its `temperature`
and `salinity` are in.  It defaults to `'teos-10'`; pass
`tracer_convention='mpas-ocean'`, along with `lon` and `lat`, for tracers
straight out of MPAS-Ocean.


(dev-ocean-spherical-meshes)=

## Quasi-uniform and Icosahedral Spherical Meshes

Many ocean tasks support two types of meshes: `qu` meshes created with the
{py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` step and `icos` meshes
created with {py:class}`polaris.mesh.IcosahedralMeshStep`.  In general, the
`icos` meshes are more uniform but the `qu` meshes are more flexible.  The
`icos` meshes only support a fixed set of resolutions described in
{ref}`dev-spherical-meshes`.

The function {py:func}`polaris.mesh.base.add_uniform_spherical_base_mesh_step()`
returns a step for for a spherical `qu` or `icos` mesh of a given resolution
(in km).  The step can be shared between tasks.

(dev-ocean-convergence)=

## Convergence Tests

Several tests that are in Polaris or which we plan to add are convergence
tests on {ref}`dev-ocean-spherical-meshes` and planar meshes.
The ocean framework includes shared config options and base classes for
forward and analysis steps that are expected to be useful across these tests.

The key config options that control the convergence test are `base_resolution`
and `refinement_factors`. The `base_resolution` is multipled by the
`refinement_factors` to determine which resolutions to test when the
convergence is being tested in space (or space and time together). The
`base_resolution` is applied to all steps when convergence in time is tested.
`base_resolution` times `dt_per_km` determines the base timestep in that case
and is then multiplied by the `refinement_factors` to determine which time steps
to test. When spherical meshes are being tested, the values in the
`convergence` section are overridden by their values in the
`spherical_convergence` section with a prefix indicating the mesh type.

The shared config options are:
```cfg
# config options for spherical convergence tests
[spherical_convergence]

# The base resolution for the icosahedral mesh to which the refinement
# factors are applied
icos_base_resolution = 60.

# a list of icosahedral mesh resolutions (km) to test
icos_refinement_factors = 8., 4., 2., 1.

# The base resolution for the quasi-uniform mesh to which the refinement
# factors are applied
qu_base_resolution = 120.

# a list of quasi-uniform mesh resolutions (km) to test
qu_refinement_factors = 0.5, 0.75, 1., 1.25, 1.5, 1.75, 2.

[convergence]

# Evaluation time for convergence analysis (in hours)
convergence_eval_time = 24.0

# Convergence threshold below which a test fails
convergence_thresh = 1.0

# Type of error to compute
error_type = l2

# the base mesh resolution (km) to which refinement_factors
# are applied if refinement is 'space' or 'both' on a planar mesh
# base resolutions for spherical meshes are given in section spherical_convergence
base_resolution = 120

# refinement factors for a planar mesh applied to either space or time
# refinement factors for a spherical mesh given in section spherical_convergence
refinement_factors = 4., 2., 1., 0.5

# config options for convergence forward steps
[convergence_forward]

# time integrator: {'RK4', 'split_explicit', 'unsplit_explicit'}
time_integrator = RK4

# RK4 time step per resolution (s/km), since dt is proportional to resolution
rk4_dt_per_km = 3.0

# unsplit time step per resolution (s/km), since dt is proportional to
# resolution
unsplit_dt_per_km = 3.0

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
default. The L-infinity norm, `inf`, is also supported.

`time_integrator` will typically be overridden by the specific convergence
task's config options, and indicates which time integrator to use for the
forward run.  Depending on the time integrator, `rk4_dt_per_km`,
`unsplit_dt_per_km` or `split_dt_per_km` will be used to determine an
appropriate time step for each mesh resolution (proportional to the cell
size). For split time integrators, `btr_dt_per_km` will be used to compute the
barotropic time step in a similar way; the unsplit scheme
(`unsplit_explicit`, which Omega calls `UnsplitRK2`) sets the split factor to
zero and skips the barotropic subcycle, so it does not read this value.
The `run_duration` and `output_interval` are typically the same and are
specified in hours.

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
        config.add_from_package('polaris.tasks.ocean.cosine_bell',
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

    def __init__(self, component, name, subdir, mesh, init,
                 refinement_factor, refinement='both'):
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

        refinement_factor : float
            The factor by which to scale space, time or both
        """
        package = 'polaris.tasks.ocean.cosine_bell'
        validate_vars = ['normalVelocity', 'tracer1']
        super().__init__(component=component, name=name, subdir=subdir,
                         resolution=resolution, mesh=mesh,
                         init=init, package=package,
                         yaml_filename='forward.yaml',
                         output_filename='output.nc',
                         validate_vars=validate_vars,
                         graph_target=f'{init.path}/graph.info',
                         refinement_factor=refinement_factor,
                         refinement=refinement)
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
ocean:
  time_management:
    config_run_duration: {{ run_duration }}
  time_integration:
    config_dt: {{ dt }}
    config_time_integrator: {{ time_integrator }}
  split_explicit_ts:
    config_btr_dt: {{ btr_dt }}
mpas-ocean:
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

In addition, the {py:class}`polaris.ocean.convergence.analysis.ConvergenceAnalysis`
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
    def __init__(self, component, subdir, dependencies, refinement='both'):
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

        refinement : str, optional
            Whether to refine in space, time or both space and time
        """
        convergence_vars = [{'name': 'tracer1',
                             'title': 'tracer1',
                             'zidx': 0}]
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions,
                         dependencies=dependencies,
                         convergence_vars=convergence_vars,
                         refinement=refinement)
```

Many tasks will also need to override the
{py:meth}`polaris.ocean.convergence.analysis.ConvergenceAnalysis.exact_solution()`
method. If not overridden, the analysis step will compute the difference of the
output from the initial state.

In some cases, the child class will also need to override the
{py:meth}`polaris.ocean.convergence.analysis.ConvergenceAnalysis.get_output_field()`
method if the requested field is not available directly from the output put
rather needs to be computed.  The default behavior is to read the requested
variable (the value associate the `'name'` key) at the time index closest to
the evaluation time specified by the `convergence_eval_time` config option.

(dev-ocean-framework-ice-shelf)=

## Ice Shelf Tasks

The `polaris.ocean.ice_shelf` module provides support for ice shelf tasks.

The {py:class}`polaris.ocean.ice_shelf.IceShelf` class can serve as a parent
class for ice shelf tests, such as
{py:class}`polaris.tasks.ocean.ice_shelf_2d.IceShelf2d`.

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
{ref}`ocean-z-star` coordinates (including the `z-tilde` option handled
through z-star infrastructure) using the `ssh` and `bottomDepth` as well
as config options from `vertical_grid`. The function
{py:func}`polaris.ocean.vertical.update_layer_thickness()` can be used to update
`layerThickness` when either or both of `bottomDepth` and `ssh` have been
changed.  After thicknesses are updated, tasks can call
{py:func}`polaris.ocean.vertical.compute_zint_zmid_from_layer_thickness()` to
recover `zInterface` and `zMid` from the resulting layer thickness.

For workflows that need pseudo-height/pressure conversion, the
`polaris.ocean.vertical.ztilde` module provides utilities:

- {py:func}`polaris.ocean.vertical.ztilde.z_tilde_from_pressure()` and
  {py:func}`polaris.ocean.vertical.ztilde.pressure_from_z_tilde()` convert
  between pseudo-height and pressure.
- {py:func}`polaris.ocean.vertical.ztilde.pressure_from_geom_thickness()` and
  {py:func}`polaris.ocean.vertical.ztilde.pressure_and_spec_vol_from_state_at_geom_height()`
  compute hydrostatic gauge pressure (and specific volume) from geometric
  layer thickness and state variables.
- {py:func}`polaris.ocean.vertical.ztilde.geom_height_from_pseudo_height()`
  reconstructs geometric layer-interface and midpoint heights from
  pseudo-thickness and specific volume.

For the p-star coordinate — Omega's ALE pseudo-compressible variant of
z-tilde — two additional modules are provided.

The function
{py:func}`polaris.ocean.vertical.pstar.init_pstar_vertical_coord()` builds the
p-star coordinate for one outer iteration.  It expects ``BottomPressure`` and
``SurfacePressure`` (both in Pa with dimension ``nCells``) to already be
present in the mesh dataset, and adds ``RefPseudoThickness``,
``PseudoThickness``, ``ZTildeInterface``, ``ZTildeMid``, ``cellMask``,
``minLevelCell``, ``maxLevelCell``, and ``vertCoordMovementWeights``.
``BottomPressure`` is updated in place to the post-partial-cell-snap value.
The reference 1-D grid (in pseudo-height) is controlled by the same
``vertical_grid`` config options used by the z-star and z-level coordinates.
Unlike those coordinates, the p-star coordinate cannot be constructed via
{py:func}`polaris.ocean.vertical.init_vertical_coord()`; tasks must call
``init_pstar_vertical_coord()`` directly (or rely on the base class below).

The {py:class}`polaris.ocean.vertical.pstar_init.PStarInitStep` class
implements the fixed-point iteration that determines ``BottomPressure``
(and therefore the p-star coordinate) such that the recovered geometric
water-column thickness matches a target bathymetric depth within a
configurable tolerance.  At each outer step the iteration scales
``BottomPressure`` by the ratio of the target to the recovered geometric
water-column thickness.

Subclasses of ``PStarInitStep`` must implement the abstract method
{py:meth}`polaris.ocean.vertical.pstar_init.PStarInitStep.init_tracers()`,
which receives the current p-star dataset (containing ``ZTildeMid``,
``ZTildeInterface``, ``PseudoThickness``, ``cellMask``, ``minLevelCell``, and
``maxLevelCell``) and returns conservative temperature and absolute salinity
arrays with dimensions ``(Time, nCells, nVertLevels)``.  The iteration is
driven by calling
{py:meth}`polaris.ocean.vertical.pstar_init.PStarInitStep.run_pstar_init()`
from within the step's ``run()`` method:

```python
from polaris.ocean.model import OceanIOStep
from polaris.ocean.vertical.pstar_init import PStarInitStep


class MyInit(PStarInitStep, OceanIOStep):
    def init_tracers(self, ds):
        ct = ...  # (Time, nCells, nVertLevels)
        sa = ...  # (Time, nCells, nVertLevels)
        return ct, sa

    def run(self):
        ds = self.run_pstar_init(
            ds_mesh=ds_mesh,
            geom_z_bot=geom_z_bot,
            sea_surface_height=geom_ssh,
        )
        ...
```

At convergence, the returned dataset contains all p-star coordinate variables
plus ``temperature``, ``salinity``, ``SpecVol``, ``pressure``, ``GeomZMid``,
``GeomZInterface``, ``bottomDepth``, and ``ssh``.  Here ``bottomDepth`` is the
geometric seafloor depth below $z = 0$ (the negation of the converged bottom
interface height), which Omega reads as ``BottomGeomDepth``; it equals the
geometric water-column thickness only when ``ssh`` is zero.

The iteration is controlled by two ``vertical_grid`` config options:

```cfg
# Number of outer iterations
pseudothickness_iter_count = 6

# Early-stopping threshold: iteration stops when the maximum fractional
# change in geometric water-column thickness falls below this value
water_col_adjust_frac_change_threshold = 1.0e-12
```

For tasks where each column has a different reference pseudo-depth (for
example because the z-tilde bottom varies spatially), the semi-private method
``_build_pstar_coord_ds()`` may be overridden to call
``init_pstar_vertical_coord()`` per cell with cell-specific config options,
as done in
{py:class}`polaris.tasks.ocean.horiz_press_grad.init.Init`.

(dev-ocean-framework-init-state)=

### Initial state

The `polaris.ocean.init_state` package provides general helpers for
building the initial-state fields the ocean models read (for example
from a converged p-star dataset):

- {py:func}`polaris.ocean.init_state.layer_thickness_from_geom_interfaces()`
  adds ``restingThickness`` and ``layerThickness`` computed from
  ``GeomZInterface``, masked by ``cellMask``.
- {py:func}`polaris.ocean.init_state.add_quiescent_normal_velocity()`
  adds an all-zero ``normalVelocity``.
- {py:func}`polaris.ocean.init_state.add_density_from_specvol()`
  adds an in-situ ``Density`` field as the inverse of ``SpecVol``.

For sigma coordinates, shared functionality for direct thickness computation is
available in
{py:func}`polaris.ocean.vertical.sigma.compute_sigma_layer_thickness()`.

The `polaris.ocean.vertical.diagnostics` module provides utilities:

- {py:func}`polaris.ocean.vertical.diagnostics.geom_thickness_from_ds()`
- {py:func}`polaris.ocean.vertical.diagnostics.pseudothickness_from_ds()`
- {py:func}`polaris.ocean.vertical.diagnostics.depth_from_thickness()`

#### Tracer conventions

An init step builds ``temperature`` and ``salinity`` in whatever
convention is natural for its physics and hands them over;
``write_initial_state_dataset()`` converts them to the convention the
ocean model expects (see {ref}`dev-ocean-framework-eos`) as it writes the
file.  A step should not convert the tracers itself.

By default, the step is assumed to have built its tracers in the
convention implied by the ``eos_type`` config option: conservative
temperature and absolute salinity for `teos-10` and, for any other EOS,
tracers that need no conversion.  A step that builds potential
temperature and practical salinity under TEOS-10 anyway (for example
because it is initialized from an E3SM restart) says so with
``tracer_convention='mpas-ocean'``, and the framework converts in the
other direction if the model is Omega.

The conversion happens on a copy just before the file is written, so it
cannot contaminate an in-memory dataset that is also used to write the
vertical coordinate.  It needs two things beyond the tracers themselves:

- **Pressure.**
  {py:func}`polaris.ocean.init_state.pressure_for_tracer_conversion()`
  uses the ``pressure`` field if the dataset has one (as p-star initial
  conditions do) and otherwise computes it from ``layerThickness``, the
  tracers and ``SurfacePressure`` (zero if absent).  Since the pressure
  only enters through the absolute-to-practical salinity correction, it
  does not need to be accurate.  The ``pressure`` field itself is dropped
  from the initial state, whether or not any conversion happens.
- **Location**, for the same salinity correction.  Explicit ``lon`` and
  ``lat`` arguments (in degrees) win.  Otherwise, ``lonCell`` and
  ``latCell`` are used, converted from radians, if the mesh has the
  ``on_a_sphere`` attribute set to ``YES``; a spherical mesh missing them
  is an error rather than a fallback.  On a planar mesh, whose
  ``lonCell``/``latCell`` are meaningless, the ``nominal_lon`` and
  ``nominal_lat`` config options in the ``ocean`` section are used
  instead.

(dev-ocean-framework-tracer-conventions-on-read)=

#### Tracer conventions on read

{py:meth}`polaris.ocean.model.OceanIOStep.open_model_dataset()` takes the
same ``tracer_convention`` argument, so that visualization and analysis
can work in one convention no matter which model ran.  In both cases the
argument is the convention on the Polaris side of the boundary --- the
tracers a step hands over on write, the tracers it gets back on read ---
and the ocean model supplies the other side.

The defaults differ, though.  On write, a step that says nothing is
assumed to have built its tracers in the convention implied by
``eos_type``.  On read, a caller that says nothing gets the tracers
exactly as the model wrote them, since only the caller knows whether it
wants the model's own convention or a common one.

The pressure comes from the same rules as on write.  The location does
not: a dataset being read has had its horizontal mesh variables removed
(or never had them), so ``lonCell`` and ``latCell`` come from the file
named by the ``mesh_filename`` argument.  A conversion with neither
``mesh_filename`` nor an explicit ``lon`` and ``lat`` is an error, as is
a mesh file with no ``on_a_sphere`` attribute, since assuming such a mesh
were planar would silently convert a global ocean at (0, 0).

The conversion is the last thing that happens to the tracers, after the
Omega-only derivations of ``layerThickness``, ``SpecVol`` and
``vertVelocityTop``, which read the model's own tracers and would be
wrong if they were converted first.

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

(dev-ocean-analysis)=

## Analysis of completed simulations

The package `polaris.tasks.ocean.analysis` contains the tasks of the
`omega_analysis` suite, which analyze a simulation that has already been run
rather than running one.  {ref}`ocean-analysis` describes the suite from a
user's point of view.  Four pieces of it are shared machinery that a new
analysis product builds on.

### Locating the simulation's files

`polaris.tasks.ocean.analysis.sim_files` is a leaf module --- it does not
import {py:class}`polaris.Step` --- so that it can be unit tested and reused
by every step that reads simulation output.

{py:class}`polaris.tasks.ocean.analysis.sim_files.SimulationFiles` is the
entry point.  It resolves the mesh, the vertical coordinate and the lists of
monthly-mean, global-statistics and MOC files covering a range of years, and
reports where each path came from.  Underneath it,
{py:class}`polaris.tasks.ocean.analysis.sim_files.OmegaConfig` reads the
simulation's own Omega configuration and answers questions about it
defensively: a missing stream, a stream that names no file, and an analysis
group that is turned off are told apart rather than raising from inside a
lookup.  This is the one place Polaris depends on the *shape* of Omega's
configuration rather than on its output.

Two details are worth knowing before adding a product:

- File-name templates are expanded by
  {py:func}`polaris.tasks.ocean.analysis.sim_files.expand_template`, which
  substitutes `$Y` and `$M`.  A template with no `$M` gives one file per year,
  and one with no date at all gives a single file --- which is the real case
  for Omega's analysis output.  These templates come from the Omega
  configuration and never from a Polaris config file, because Polaris config
  files use extended interpolation and a bare `$` in a value is an error.
- Omega builds the file name of an analysis group's output stream as
  `<prefix>_<period><TimeStats|Instants><template>`.  A group can write both
  time means and snapshots under different names, so
  {py:meth}`polaris.tasks.ocean.analysis.sim_files.OmegaConfig.analysis_streams`
  returns each stream with its period and whether it is a time reduction, and
  the caller must not assume either spelling.

### Naming the models' global statistics

Both ocean models write one variable per (field, statistic) pair in their
global statistics output and name it after the two, so
`polaris.ocean.global_stats_names` builds the names rather than listing them.
It is a leaf module for the same reason `sim_files` is, and it lives under
`polaris.ocean` rather than under the analysis package because the
`realistic_global` `analysis_members` task reads the same kind of output from
a forward step in its own task.

Three things about it are worth knowing:

- **The names are built, not mapped.**  `mpaso_to_omega.yaml` needs an entry
  only for the field itself --- `ssh: SshCell` --- and the statistic and,
  for one of Omega's time reductions, the period are appended.  Mapping the
  composite names instead would take an entry per (field, statistic) and,
  once Omega writes time means, one per (field, statistic, period).
- **The two models do not compute the same statistics.**  MPAS-Ocean writes
  a root-mean-square where Omega writes a standard deviation, and those are
  different quantities, so neither model's list in
  {py:data}`polaris.ocean.global_stats_names.GLOBAL_STATS` has an entry for
  the other's.  A step that wants a standard deviation from MPAS-Ocean
  derives one from the root-mean-square and the mean, which is a conversion
  and belongs in the step.
- **A step should not assume what a run wrote.**
  {py:func}`polaris.ocean.global_stats_names.select_global_stats` intersects
  the (field, statistic) pairs a step asks for with what a dataset holds,
  reports each one that is absent and drops it, and raises only when *none*
  of them is present --- which is a step reading the wrong thing rather than
  a simulation writing a subset.
  {py:func}`polaris.ocean.global_stats_names.discover_fields` goes the other
  way, giving the fields a file holds statistics for, which is what a config
  option that names no fields falls back to.

### Steps

{py:class}`polaris.tasks.ocean.analysis.analysis_step.AnalysisStep` extends
{py:class}`polaris.ocean.model.OceanIOStep` with the year range every analysis
step has and with the input handling every one of them needs:
`get_sim_files()` to resolve the simulation, `add_sim_input_file()` and
`add_sim_input_files()` to link its files into the step's work directory, and
`log_inputs()` to report what was read.

Analysis steps follow {ref}`dev-task-parallelism` from the start, since it is
cheap while the code is being written and expensive to retrofit.  In
particular, every file a step opens in `run()` goes through
{py:meth}`polaris.Step.work_path()` rather than a bare relative filename,
temporary files go in the step's own work directory, and a step declares the
parallelism it will actually start as `cpus_per_task` rather than sizing
itself to the machine.

Which products an analysis step makes is usually not known until it has read
the simulation, since a run writes some subset of the fields that were asked
for.  Such a step declares no per-field outputs at setup and instead calls
{py:meth}`polaris.ocean.model.OceanIOStep.add_produced_file` as it writes
each one.  That is also what keeps a plot and the netCDF file beside it from
getting out of step with each other, since they are registered together.

### Range-keyed steps

Every step lives at a subdirectory named for the range of years it covers ---
`climatology/0021-0040`, `global_stats/0001-0060` --- built with
{py:func}`polaris.tasks.ocean.analysis.sim_files.year_range_key`.

That is what gives the suite its re-analysis behavior, and it needs no
framework support.  A setup with a new range creates steps in directories that
have never run and so run; a setup with the same range lands on directories
that are already complete and recomputes nothing; and two ranges never share a
directory, so an earlier range's results cannot be clobbered or mislabelled.

A task's subdirectory is fixed when the component is constructed, but its
steps are not: `polaris setup` merges the user's config into each task and
then calls `configure()` before adding configs to steps, precisely so that
steps created there are handled.  The analysis tasks therefore discard and
rebuild their step lists from the config options, in the same way the cosine
bell tasks do for resolutions.  Construction itself must read nothing but the
packaged defaults, since `polaris list` builds every task in every component;
the simulation's Omega configuration is not read until step setup.

Steps are created with
{py:meth}`polaris.Component.get_or_create_shared_step()`, so a step several
tasks want --- the climatology, which every field group of `climatology_maps`
reads --- is built once for a range no matter how many of them ask for it.

### Publishing what the steps made

Publication is three pieces, none of which knows anything about the ocean, so
all three live in the component-neutral `polaris.analysis` package beside
`polaris.viz` rather than under `polaris.tasks.ocean.analysis`:

- the **manifest writer**, {py:class}`polaris.analysis.manifest.Manifest`,
  which a plotting step reaches through
  {py:meth}`polaris.tasks.ocean.analysis.analysis_step.AnalysisStep.add_product()`
  once per product;
- the **collector**, {py:func}`polaris.analysis.publish.publish`, which merges
  the fragments, symlinks each product into the staging tree and renders its
  thumbnail;
- the **site generator**,
  {py:func}`polaris.analysis.site.generate_site`, which renders the gallery
  from the merged manifest.

A step describes what it made as it makes it, and writes no fragment itself:

```python
self.add_product(
    plot='temperature_ANN_-100m.png',
    data='temperature_ANN_-100m.nc',
    group='climatology_maps',
    gallery='temperature',
    title='Potential temperature at 100 m, ANN, years 21-40',
    field='temperature', season='ANN', reduction='-100m',
)
```

`AnalysisStep` writes it.  `runtime_setup()` leaves an empty fragment before
`run()` is called and each `add_product()` writes it again, so a step that
makes products always has a current one on disk.  The range of years the step
covers is added to the facets unless the call passes its own, since every
product of a step covers the step's range and that range is what keeps the
published names of two analyses of one simulation apart.

Three rules keep the fragment from growing into a format that needs a
specification.  A step fills in the facets and nothing else --- the published
name, the thumbnail and the gallery page are the collector's business, so a
step never learns the staging tree's layout.  Only `group` and `gallery` shape
the site; every other facet is caption material today and filter material
later, which is what makes adding a facet cheap.  And products keep the order
they were added in, so a gallery reads ANN, DJF, MAM, JJA, SON because that is
the order the step plotted them in, with no sort key anywhere.

{py:class}`polaris.tasks.ocean.analysis.publish.Publish` is the one step that
knows how results are presented, and everything about presentation can change
without a plotting step changing.  Two things about it are easy to get wrong:

- **It never looks for its inputs.**  Walking the work directory for anything
  named `manifest.json` would be invisible to Polaris's input checking and to
  {ref}`dev-task-parallelism`, so instead each fragment is a declared input,
  linked into the step's `fragments/` directory from the step that wrote it,
  and each of those steps is a dependency as well.  A step that only computes
  intermediate results sets `makes_products = False` on its class --- the
  climatology does --- and is left out of both.

  This is why the fragment is written from `runtime_setup()` rather than at
  the end of `run()`.  A step with nothing to publish leaves an empty product
  list, which is what lets the fragment be declared and checked instead of
  tolerated when absent --- and a rule that had to be obeyed at the end of
  `run()` would be forgotten in exactly that step.  The two failures stay
  distinguishable: a fragment that is missing means a step ran without
  writing one, and a dependency's missing pickle means the step did not run
  at all.
- **Its dependencies are step objects, and the tasks sharing a config are
  configured in an arbitrary order.**  Every analysis task discards its steps
  and builds new ones each time it is configured, and Polaris checks that a
  dependency is an object that was set up, so wiring the step once at
  construction leaves it depending on steps that no longer exist.  Each task
  therefore calls
  {py:meth}`polaris.tasks.ocean.analysis.PublishTask.rebuild_steps()` after
  rebuilding its own, and whichever task is configured last leaves the
  dependencies correct.

Nothing about a dependency reorders steps --- the runner walks them in the
order the suite lists them --- so `omega_analysis.txt` lists `publish` last.
