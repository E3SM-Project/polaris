(dev-seaice-single-column)=

# single_column

The `single_column` tests in `polaris.tasks.seaice.single_column` exercise
column physics only. Here, we describe the tasks and their shared framework.

(dev-seaice-single-column-framework)=

## framework

The The shared framework is made up of a shared `forward` step and a set of
shared namelists and streams files.

### forward

The class {py:class}`polaris.tasks.seaice.single_column.forward.Forward`
defines a step for running MPAS-Seaice. The step stages the forcing files,
namelist and streams files for each task.

## standard_physics_test
The {py:class}`polaris.tasks.seaice.single_column.standard_physics.StandardPhysics`

The test runs for one year, using year 2000 conditions, as specified in the
`namelist.seaice` and `streams.seaice` files. The test will compare the contents
of the output file for year 2000 against a baseline if provided.

### viz

The class {py:class}`polaris.tasks.seaice.single_column.standard_physics.viz.Viz`
produces time series of sea ice volume, snow volume, and surface temperature.

## exact_restart_test
The {py:class}`polaris.tasks.seaice.single_column.exact_restart.ExactRestart`

The test runs a `full_run` for one day, writing restarts every 12 hours, as
specified by `namelist.full` and `streams.full`. The test then runs a
`restart_run` from the full run's 12 hour restart file, for 12 hours, writing
a restart file at the end of the run. The contents of each runs final restart file
are then compared.
