(landice-dome)=

# dome

The `dome` tasks evolve an ice dome on a flat bed, the test Compass called
`dome`.  Each task runs with MALI's shallow-ice velocity solver (`sia`) and
with Albany's first-order solver (`fo`):

```none
landice/dome/2km/sia/smoke_test
landice/dome/2km/sia/decomp
landice/dome/2km/sia/restart
landice/dome/2km/fo/smoke_test
landice/dome/2km/fo/decomp
landice/dome/2km/fo/restart
```

The tasks share the `landice/dome/2km/init` step, which makes the mesh and
initial condition.  The first-order tasks need a Polaris environment with
Albany (see {ref}`dev-landice-albany`).

## mesh

The mesh is a planar hexagonal mesh with 2-km resolution and 30 by 34 cells,
nonperiodic in both directions, with 10 uniformly spaced vertical levels.

## initial conditions

The ice thickness is a Halfar dome with a radius of
$r_0 = 60\sqrt{0.125}$ km and a maximum thickness of
$h_0 = 2000\sqrt{0.125}$ m:

$$
h(r) = h_0 \left[1 - \left(\frac{r}{r_0}\right)^{4/3}\right]^{3/7}
$$

for $r < r_0$, and zero elsewhere.  The dome is centered on the cell nearest
the center of the domain, which is moved to the origin.  The bed is flat at
sea level.

## forcing

The surface mass balance is zero.

## time step and run duration

The time step is 1 year.  `smoke_test` runs for 200 years with the
shallow-ice solver and for 2 years with the first-order solver.  `decomp`
runs for 2 years, and `restart` compares a 2-year run with a 1-year run that
restarts from its first year.

## config options

```cfg
# config options for dome tasks
[dome]

# sizes (in cells) for the uniform mesh
nx = 30
ny = 34

# number of vertical levels in the mesh
levels = 10

# the dome type ('halfar' or 'cism')
dome_type = halfar

# Whether to center the dome in the center of the cell that is closest to the
# center of the domain
put_origin_on_a_cell = True

# whether to add a small shelf to the test
shelf = False


# config options related to visualization for dome tasks
[dome_viz]

# the colormap for ice thickness
thickness_cmap = cmo.ice_r

# the colormap for surface speed
speed_cmap = cmo.speed
```

A `cism` dome has a parabolic profile, $h_0\sqrt{1 - (r/r_0)^2}$.  With
`shelf = True`, the bed drops to 2,000 m below sea level for $x < -10$ km.

## cores

The model runs on 4 cores, except in `decomp`, which compares runs on 1 and
4 cores.

(landice-dome-smoke-test)=

## smoke_test

`smoke_test` runs MALI and plots the ice thickness and surface speed at the
end of the run in its `viz` step.

(landice-dome-decomp)=

## decomp

`decomp` runs MALI on 1 and 4 cores and compares the thickness and normal
velocity.  With the shallow-ice solver, they must be bit-for-bit.  With the
first-order solver, they must agree within the norms that Compass used.

(landice-dome-restart)=

## restart

`restart` runs MALI for 2 years in `full_run`, and for 1 year in
`restart_run`, which starts from the restart file `full_run` writes after
its first year.  The thickness and normal velocity at the end of the two
runs must be bit-for-bit.
