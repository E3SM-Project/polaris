(dev-ocean-external-gravity-wave)=

# external_gravity_wave

The {py:class}`polaris.tasks.ocean.external_gravity_wave.ExternalGravityWave`
task provides a test case to evaluate the time-convergence of time-stepping
schemes in the simplest possible model configuration.

Note that this is *not* a shallow water test case.
While the standard, non-linear shallow water thickness equation 
has been left alone, all tendencies in the  momentum equation have been turned
off, save the pressure gradient term. The resulting equations are given by
$$
\begin{align}
    &\partial_t \mathbf{u} = -g \nabla h \\
    &\partial_t h + \nabla \cdot (h\mathbf{u}) = 0 \,.
\end{align}
$$

In particular, this task is used to  test the convergence of local 
time-stepping schemes (`LTS` and `FB_LTS`) that employ a operator splitting
in which tendency terms other than those above are advanced with
a first-order error. As a result, this task helps to show that these local
time-stepping schemes are achieving the correct theoretical order of
convergence if said splitting was not used.

To calculate errors, the task runs the case once at a small time-step
to generate a reference solution.

## framework

The config options for the `external_gravity_wave` tests are described in
{ref}`ocean-external-gravity-wave` in the User's Guide.

### base_mesh

External gravity wave tasks use shared `base_mesh` steps for creating
{ref}`dev-ocean-spherical-meshes` at a sequence of resolutions.

### init

The class {py:class}`polaris.tasks.ocean.external_graivty_wave.init.Init`
defines a step for setting up the initial state.

### init_lts

The class
{py:class}`polaris.tasks.ocean.external_graivty_wave.lts_regions.LTSRegions`
descends from {py:class}`polaris.step`.
This step labels the cells and edges of a mesh generated in an `init` step
for use with an LTS method.

### forward

The class {py:class}`polaris.tasks.ocean.external_gravity_wave.forward.Forward`
descends from
{py:class}`polaris.ocean.convergence.spherical.SphericalConvergenceForward`,
and defines a step for running MPAS-Ocean from an initial condition produced in
an `init` step. See {ref}`dev-ocean-convergence` for some relevant
discussion of the parent class.

Additionally, the class
{py:class}`polaris.tasks.ocean.external_gravity_wave.forward.ReferenceForward`
descends directly from {py:class}`polaris.ocean.model.OceanModelStep`.
This is done to create a forward step to generate the reference solution
independent of the rest of the convergence framework.

The time steps are determined from the resolution
based on the `{time_integrator}_dt_per_km` config option in the `[convergence_forward]`
section.  Other model config options are taken from `forward.yaml`.

## analysis

The class
{py:class}`polaris.tasks.ocean.external_graivty_wave.analysis.Analysis`
descends from
{py:class}`polaris.ocean.convergence.analysis.ConvergenceAnalysis` and 
defines a step for computing the error norm (L2) for results for each
time-step against the reference solution, saving them in 
`convergence_layerThickness.csv` and `convergence_normalVelocity.csv`, and
plotting them in `convergence_layerThickness.png` and 
`convergence_normalVelocity.png`.

