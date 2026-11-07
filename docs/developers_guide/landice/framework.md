(dev-landice-framework)=

# Land-ice framework

The shared framework for MALI tasks is in `polaris.landice`.

(dev-landice-model-step)=

## MALI model step

{py:class}`polaris.landice.model.MaliModelStep` is a
{py:class}`polaris.ModelStep` for running MALI with namelist and streams
files.  Its `velocity_solver` argument sets `config_velocity_solver`, after
any namelist files the step adds.  A step with a velocity solver from Albany
(`'FO'`) must also give `albany_input_package`, the package with its
`albany_input.yaml`, which is copied into the step's work directory.
{py:attr}`polaris.landice.model.MaliModelStep.needs_albany` tells the
component whether the MALI build needs Albany (see {ref}`dev-landice-albany`).

The step partitions `graph.info` in its work directory, so a task links that
file from the step that made the mesh.

(dev-landice-mesh)=

## MALI meshes

{py:func}`polaris.landice.mesh.make_mali_mesh()` turns a culled planar MPAS
mesh into a MALI mesh with a given number of vertical levels, with
mpas_tools' `create_landice_grid_from_generic_mpas_grid`, and optionally
writes a graph file for partitioning it.  It needs no MALI build, so steps in
other components can call it.
