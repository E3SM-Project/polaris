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
as config options from `vertical_grid`.

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
