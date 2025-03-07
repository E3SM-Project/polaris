(seaice-single-column)=

# single column

## description

The single column tests include any sea ice tests using only column physics.

## mesh

The mesh is a single cell in the Arctic with coordinates 71.35N, 156.5W.

## initial conditions

1m thick disc.

## forcing

CORE atmospheric forcing.

## cores

The test runs on a single core.

## config options

None.

(seaice-single-column-standard-physics)=

## standard physics test

## mesh

See {ref}`seaice-single-column`.

## initial conditions

See {ref}`seaice-single-column`.

## forcing

See {ref}`seaice-single-column`.

## cores

See {ref}`seaice-single-column`.

## config options

None.

### timestep and run duration

The test runs with a one hour timestep for one year with year 2000 forcing.

### visualization

The test produces the following timeseries plot.

```{image} images/single_cell.png
:align: center
:width: 500 px
```

(seaice-single-column-exact-restart)=

## exact restart test

## mesh

See {ref}`seaice-single-column`.

## initial conditions

See {ref}`seaice-single-column`.

## forcing

See {ref}`seaice-single-column`.

## cores

See {ref}`seaice-single-column`.

## config options

None.

### timestep and run duration

The test runs with a one hour timestep using 2000-01-01 forcing.
A 'full_run' is run for one day with restarts written after 12 hours and 24 hours.
A second 'restart_run' is run for 12 hours, starting from the 12 hour restart from the 'full_run'.
The contents of the two restart files written at the end of the pair of runs are then compared.
