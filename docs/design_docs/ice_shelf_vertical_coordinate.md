# Vertical Coordinate Under Ice Shelves

date: 2026/11/23

Contributors: Xylar Asay-Davis, Claude

## Summary

Under an ice shelf, z-star squeezes the whole reference column between the
ice draft and the bed.  Under deep ice, the top layers become thin and their
interfaces follow the draft, so they slope steeply across calving fronts and
draft steps.  The pressure-gradient error that follows drives fast spurious
flow.  In a `realistic_global` so12to30km run with ice-shelf cavities, z-star
blows up within 4 hours at a Totten front where an 847 m draft sits on a
21 m column next to open water.

This design drops reference levels from the top of each column under an ice
shelf, raising `minLevelCell`, and applies z-star to the shorter reference
column that remains.  Each ice shelf drops the levels above a percentile of
the drafts along its calving front.  Cells at the front drop just the levels
above their own draft, so their layers line up with the open ocean.  A few
more levels are dropped where neighboring columns would still be too steep.
The coordinate belongs to the ocean framework, so idealized tasks such as
ISOMIP+ and MISOMIP can use it as well as `realistic_global`.

The design has two stages:

| stage | what it delivers |
| --- | --- |
| **fixed geometry** | the drop, computed by Polaris at initialization and fixed during a run |
| **evolving geometry** | the drop, recomputed by the ocean model as the ice changes in a coupled run, with levels added and removed by Lagrangian vertical remapping |

The fixed-geometry stage succeeds with a `realistic_global` dynamic
adjustment on so12to30km and qu30km, under the `grounding_line` convention,
that runs to the end of its `simulation` stage with flow under the ice below
0.5 m/s.  The evolving-geometry stage succeeds with ISOMIP+ runs whose ice
geometry changes in time, and then coupled MISOMIP runs, that conserve heat
and salt as levels come and go.

Requirements, algorithms and tests for the evolving-geometry stage are marked
as such.  Everything else applies to both stages.

## Open questions

These concern the evolving-geometry stage only.

- **The hysteresis margin.**  How far a draft must pass a level boundary
  before a drop changes.  Half a level is a starting point.
- **Lagrangian vertical remapping in MPAS-Ocean.**  It exists but still
  needs debugging and testing before this stage can rely on it.

## Requirements

### Requirement: Layers under ice shelves stay near their reference thicknesses

Under an ice shelf, layers shall be close to the thickness of the reference
levels at their depth, rather than squeezed between the draft and the bed.
One thin cell at a calving front shall not set the layers of a whole shelf.

### Requirement: Layers at calving fronts line up with the open ocean

Where an ice front faces open water below its draft, the layers of the cell
under the ice shall line up with those of the open-water cell, and the ice
shall not wall off open water below its draft.

### Requirement: Neighboring columns are not too steep

The slope of layer interfaces between neighboring columns under ice shelves,
measured by the hydrostatic consistency number rx1, shall not exceed a
configured maximum where the column has the levels to meet it.

### Requirement: Each ice shelf is known at init for every possible ocean cell

Every cell under land ice, floating or grounded, shall belong to an ice
shelf at init, so that a cell that becomes ocean later has a shelf whose
layers it follows.

### Requirement: Ocean tasks with ice-shelf cavities can use the coordinate

The coordinate shall be available to any ocean task with ice-shelf cavities
that uses z-star or the p-star initialization.  It shall be off by default,
leaving other tasks unchanged.

### Requirement: The coordinate follows the ice as it evolves

Evolving-geometry stage.  When the ice geometry changes during a run, each
column's first level shall follow the new geometry by the same rules as at
init.

### Requirement: Levels come and go without changing the ocean's content

Evolving-geometry stage.  When a column gains or loses top levels, its heat,
salt and momentum shall be conserved and continuous in time.

### Requirement: A column's levels do not flicker

Evolving-geometry stage.  A draft that stays near a level boundary shall not
add and remove the same level again and again.

## Algorithm Design

### Algorithm Design: Layers under ice shelves stay near their reference thicknesses

Each ice shelf (see below) drops the reference levels lying entirely above
the 20th percentile of the drafts of its front cells.  The percentile is
weighted by each cell's length of calving front (`dvEdge`).  Floating cells
of the shelf take this drop, and film cells drop nothing.  A column keeps at
least `min_vert_levels` levels.  A shelf with no front that faces open water
gets no drop of its own.

The remaining levels follow z-star over the reduced reference column.  With
$k_{min}$ the first remaining level, $z_{k_{min}}$ the depth of its top and
$\Delta z_k$ the reference thicknesses, the resting thickness, which
MPAS-Ocean requires to sum to the bed depth $H$, is

$$
h_{rest,k} = \Delta z_k \frac{H}{H - z_{k_{min}}},
\qquad
h_k = h_{rest,k} \frac{H + \eta}{H}
$$

so a layer under a draft near $z_{k_{min}}$ is close to its reference
thickness.

> **Rationale.**  The shallowest front draft let one front cell with a draft
> of a few meters keep the Ross Ice Shelf at 3 to 4 dropped levels, with top
> layers 1.5–5 m thick.  The 10th and 20th percentiles gave the same flow
> through a full so12to30km dynamic adjustment, and the 20th needs fewer
> extra drops between cells inside a shelf (1042 against 1392).

### Algorithm Design: Layers at calving fronts line up with the open ocean

A front is an edge between a cell under land ice and an open-water cell,
neither of them a film, where the open cell's bed is below the ice cell's
draft by more than a film column: `min_vert_levels` times the film's layer
thickness.  A front cell drops exactly the reference levels lying entirely
above its own draft, even where that is fewer than its shelf drops, so its
first layer starts just above the draft and faces open water at the same
depths.

> **Rationale.**  Ice that nearly reaches the bed may face open water whose
> bed is above the draft.  Taking its own draft would leave its cell a thin
> column of a few thick layers, which escape the wetting-and-drying velocity
> ramp and burst against a thicker neighbor.  Such an edge is therefore not
> a front.

### Algorithm Design: Neighboring columns are not too steep

For an edge between cells $a$ and $b$ with shared layers $k$, interface
heights $z^{top}$ and $z^{bot}$ and thicknesses $h$,

$$
r_{x1} = \max_k \frac{\left|z^{top}_{a,k} - z^{top}_{b,k}
+ z^{bot}_{a,k} - z^{bot}_{b,k}\right|}{h_{a,k} + h_{b,k}}
$$

After the shelf and front drops, on each edge touching land ice with no film
cell whose $r_{x1}$ exceeds the maximum (30 by default), the cell with the
deeper draft drops the fewest further levels that bring the edge to the
maximum, with its neighbor at its shelf or front drop.  Where no drop does,
it drops all but `min_vert_levels`.  A cell takes the largest drop over its
edges.  Where both cells of an edge drop further, $r_{x1}$ can stay above
the maximum, but rarely: on so12to30km with the 20th percentile, the 99th
percentile of $r_{x1}$ under the ice is 26.

### Algorithm Design: Each ice shelf is known at init for every possible ocean cell

Floating cells are under land ice and not a film, and grounded cells are
films under land ice.  Each connected region of floating cells is a shelf.
Grounded cells then join shelves in rings: a grounded cell next to a cell
already in a shelf joins the shelf with the lowest label among those
neighbors.  Grounded regions that no floating region reaches become shelves
of their own.

The shelves have no history.  A seam between two shelves under grounded ice
is reached only if the ice collapses a long way.  The shelf of each cell is
written to the initial state as `iceShelfGroup`, 0 away from land ice.

### Algorithm Design: Ocean tasks with ice-shelf cavities can use the coordinate

The drop is computed from the geometric draft (`ssh`), bed depth, land-ice
and film masks and the mesh, before the vertical coordinate is built, and
the coordinate takes the result as the first level of each column.  The
p-star coordinate ([pstar_init](pstar_init.md)) compares geometric depths
with its reference pseudo-depths, which differ by the ratio of the density
to the reference density, a few percent at most.

### Algorithm Design: The coordinate follows the ice as it evolves

Evolving-geometry stage.  Each time the coupler updates the land-ice fields,
the ocean model recomputes the drops with the algorithms above, from the
current draft (the SSH under land ice), bed depth and masks:

1. Find the fronts.
2. For each shelf, gather the front drafts into a histogram over shelves and
   reference levels, weighted by `dvEdge`, with one global sum.  The
   histogram gives each shelf's percentile draft.
3. Compute the shelf, front and rx1 drops, which need only each cell's
   neighbors.

The shelves are the `iceShelfGroup` of the initial state and never change.

### Algorithm Design: Levels come and go without changing the ocean's content

Evolving-geometry stage.  A change in a column's first level is applied with
Lagrangian vertical remapping.  The column's tracers are remapped from the
old layers to the new ones, conserving each tracer's content.  The normal
velocity on each edge is remapped the same way, so momentum is conserved
too.  A new top level starts with the properties of the layer it is split
from, and a removed top level is merged into the layer below it.

### Algorithm Design: A column's levels do not flicker

Evolving-geometry stage.  A drop changes only when the value that sets it
passes a level boundary by more than a margin, a fraction of the level's
thickness:

- a shelf's drop, when its percentile draft does;
- a front cell's own drop, when its draft does;
- an rx1 drop, when the edge's $r_{x1}$ passes the maximum by a margin.

A drop then changes by one level at a time.  The current drop is the only
history the coordinate keeps.

## Implementation

### Implementation: Layers under ice shelves stay near their reference thicknesses

`polaris.ocean.vertical.ice_shelf.compute_ice_shelf_min_level_cell()` takes
the config, the mesh, `ssh`, `bottomDepth`, `landIceMask`, the film mask and
the film's layer thickness, and returns the zero-based first level of each
column and `iceShelfGroup`.  It builds the reference column of each cell with
the z-star helpers, including partial bottom cells, to find each cell's
levels.  The options, in `[vertical_grid]`, are:

```cfg
[vertical_grid]

# how the first level of each column under an ice shelf is chosen:
# "surface" (the top reference level) or "front_draft" (below the levels
# above the shelf's calving-front drafts)
ice_shelf_top_level = surface

# the percentile of each shelf's calving-front drafts, weighted by the length
# of front, above which the shelf drops reference levels
ice_shelf_front_percentile = 20.0

# the largest rx1 allowed between columns under ice shelves
ice_shelf_max_rx1 = 30.0
```

With `surface`, the function returns zeros.

### Implementation: Layers at calving fronts line up with the open ocean

The front test and each front cell's own drop are in the same function, with
the film layer thickness passed by the caller from its own options, since
each task with a film already has one.

### Implementation: Neighboring columns are not too steep

The extra drops use the layers of the reduced z-star column at the
initial `ssh`.  Only edges above the maximum are visited, each with a short
search over the drops of its deeper cell.

### Implementation: Each ice shelf is known at init for every possible ocean cell

`compute_ice_shelf_groups()` labels the floating regions with
`scipy.sparse.csgraph.connected_components()` and grows them into grounded
cells one ring at a time.

### Implementation: Ocean tasks with ice-shelf cavities can use the coordinate

- `init_vertical_coord()` and `init_z_star_vertical_coord()` take an
  optional `min_level_cell`.  The first level is capped so a column keeps
  `min_vert_levels` levels, and `restingThickness` is rescaled to sum to
  `bottomDepth`.
- `init_pstar_vertical_coord()` and `PStarInitStep.run_pstar_init()` take
  the same argument, and `RefPseudoThickness` is rescaled to sum to the
  pseudo-depth of the bed.
- `realistic_global`: its p-star init step computes the drop with the draft
  and film mask of each p-star solve, and its cavity options set
  `ice_shelf_top_level = front_draft`.  The initial state writes
  `iceShelfGroup`.
- ISOMIP+ and MISOMIP can pass the drop to `init_vertical_coord()` in the
  same way.  They are not changed in the fixed-geometry stage.

### Implementation: The coordinate follows the ice as it evolves

Evolving-geometry stage.  This stage is mostly MPAS-Ocean work, and Omega
work once Omega has ice-shelf cavities.

- The ocean model computes the drops as
  `compute_ice_shelf_min_level_cell()` does, after each update of the
  land-ice fields from the coupler.  It reads `iceShelfGroup` from the
  initial state, and the `[vertical_grid]` options above become namelist
  options.
- `minLevelCell` and the fields derived from it, such as the first level
  of each edge and vertex and the cell and edge masks, become time-varying
  and go in the restart file.
- Polaris keeps the Python function as the reference.  A Polaris task with
  evolving geometry turns the drop on in the model's namelist, and its
  initial state supplies the first drop and `iceShelfGroup`.

### Implementation: Levels come and go without changing the ocean's content

Evolving-geometry stage.  MPAS-Ocean's Lagrangian vertical remapping applies
the change in `minLevelCell` in the same time step that the drops are
recomputed.

### Implementation: A column's levels do not flicker

Evolving-geometry stage.  The margin is a namelist option, with a matching
`[vertical_grid] ice_shelf_drop_margin` in Polaris so that a task can set
it.  The drop at the start of the run comes from the initial state, so the
first recomputation already has a drop to compare with.

## Testing

### Testing and Validation: Layers under ice shelves stay near their reference thicknesses

Unit tests of the weighted percentile and of the drops on a small synthetic
mesh.  On so12to30km, the drops match those of the offline prototype that
completed the dynamic adjustment.

### Testing and Validation: Layers at calving fronts line up with the open ocean

A unit test that a front cell takes its own draft's levels and that an edge
facing a shallower bed is not a front.

### Testing and Validation: Neighboring columns are not too steep

A unit test that a steep edge gets the fewest extra drops that meet the
maximum.

### Testing and Validation: Each ice shelf is known at init for every possible ocean cell

A unit test with two floating regions, grounded cells reached from each,
and a grounded region reached from neither.

### Testing and Validation: Ocean tasks with ice-shelf cavities can use the coordinate

Unit tests that z-star and p-star columns with dropped levels sum to the bed
depth, and that the default leaves them unchanged.  The `realistic_global`
dynamic adjustment on so12to30km and qu30km with `grounding_line` runs to
the end of `simulation`, with flow under the ice below 0.5 m/s.

With GM, this needs MPAS-Ocean to limit the GM bolus velocity with wetting
and drying, as it does the submesoscale velocity.  Next to a thin film at a
calving front, the bolus velocity otherwise reaches 2 m/s.  MPAS-Ocean also
needs fixes for columns whose top levels are inactive.

### Testing and Validation: The coordinate follows the ice as it evolves

Evolving-geometry stage.  The model's drops match those of the Python
function for the same geometry, at the start of a run and after the
geometry has changed.  The ISOMIP+ tasks whose ice geometry changes in time
run with the coordinate on, and then coupled MISOMIP runs.

### Testing and Validation: Levels come and go without changing the ocean's content

Evolving-geometry stage.  In those runs, the global heat and salt content
change only through the surface and land-ice fluxes, to round-off, across
every change in a column's levels.

### Testing and Validation: A column's levels do not flicker

Evolving-geometry stage.  A unit test that a draft oscillating within the
margin keeps its drop, and one that crosses it changes the drop by one
level.  In the ISOMIP+ runs, no column changes its first level back and
forth within a few coupling intervals.

## Decisions

- **A percentile of the front drafts, not the shallowest.**  See the first
  algorithm.  The 20th percentile is the default, and the option allows
  others.
- **Front cells take their own draft, not their shelf's.**  Taking the larger
  of the two walled off open water below the ice by up to 106 m at the 20th
  percentile.
- **Shelves are fixed at init.**  Labels are not carried from step to step
  or inherited from neighbors at run time.
- **The fixed-geometry stage comes first.**  It needs no MPAS-Ocean changes
  beyond fixes for inactive top levels, and it supports the realistic global
  runs with ice-shelf cavities now.  The evolving-geometry stage needs
  run-time drops and Lagrangian vertical remapping in the ocean model.
- **One global sum per coupling interval, not drops from neighbors alone.**
  A drop computed from each cell's neighbors cannot know its shelf's
  percentile.  The sum is one value per shelf and level, once per coupling
  interval.
- **Hysteresis, not drops free to change at every update.**  A drop that
  follows its draft exactly would flicker for a draft near a level boundary,
  with a remap each time.
- **Moving calving fronts are set aside.**  Cells that start or stop being
  ocean when ice calves or a front advances need more than a change of first
  level.
- **z-star, not a Haney-number coordinate or smoothed geometry.**  Compass's
  Haney-number coordinate digs the bed into "teeth", and smoothing changes
  the ice geometry that MALI will supply.
