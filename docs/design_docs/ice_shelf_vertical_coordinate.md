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

This design starts each column under an ice shelf at a top depth and applies
z-star to the reference column below it.  Each ice shelf takes its top depth
from a percentile of the drafts along its calving front.  Cells at the front
take their own draft, so their layers line up with the open ocean.  Cells
whose neighbors would still be too steep take deeper top depths.  Reference
levels entirely above a column's top depth are dropped, raising
`minLevelCell`, and the level containing it becomes a partial top level,
like a partial bottom cell upside down.  A top level that shares its level
with fewer than two neighbors merges into the level below.  The coordinate
is a function of the current geometry and the ice shelves of the initial
state.  It changes continuously with the geometry, except where an
interface near the top of a column appears or disappears.  The coordinate
belongs to the ocean framework, so idealized tasks such as ISOMIP+ and
MISOMIP can use it as well as `realistic_global`.

The design has two stages:

| stage | what it delivers |
| --- | --- |
| **fixed geometry** | the top depths, computed by Polaris at initialization and fixed during a run |
| **evolving geometry** | the top depths, recomputed by the ocean model as the ice changes in a coupled run |

The fixed-geometry stage succeeds with a `realistic_global` dynamic
adjustment on so12to30km and qu30km, under the `grounding_line` convention,
that runs to the end of its `simulation` stage with flow under the ice below
0.6 m/s.  The evolving-geometry stage succeeds with ISOMIP+ runs whose ice
geometry changes in time, and then coupled MISOMIP runs, that conserve heat
and salt as the layers change.

Requirements, algorithms and tests for the evolving-geometry stage are marked
as such.  Everything else applies to both stages.

## Open questions

- **A shelf top depth that changes continuously.**  Evolving-geometry stage.
  A percentile jumps when it crosses a gap between front drafts, which moves
  the layers of the whole shelf at once.  A percentile of a smoothed
  histogram, or a weighted soft minimum, would change continuously and still
  need only one global sum.
- **An rx1 search that changes continuously.**  Evolving-geometry stage.
  The shallowest top depth that meets the rx1 maximum can jump where
  $r_{x1}$ does not fall steadily as the top depth deepens, or where a
  partial top level merges.
- **Cascades of merged top levels.**  Evolving-geometry stage.  Merging a
  top level can take an active edge from a neighbor, which then merges its
  own, and so on.  Each pass needs a halo exchange of `minLevelCell`, or a
  halo as wide as the number of passes.  Knowing that no column changed
  needs a global reduction on every pass.  Stopping after a fixed number of
  passes instead leaves top levels with one active edge, which can carry
  jets.  On so12to30km the cascade took 5 passes, with each column moving
  straight to its first level with two active edges.  That is more than
  MPAS-Ocean's 3-cell halo, and geometry evolving under MALI may need more.
  A small change in the draft can also merge or split off top levels in
  several neighboring columns at once.

## Example

The figures compare z-star (top of each) with the coordinate (bottom) in the
`realistic_global` so12to30km initial state with ice-shelf cavities under
the `grounding_line` convention.  Both come from the same initialization and
differ only in `ice_shelf_top_level`.  The coordinate shown is an earlier
version that rounds each top depth up to the top of its level, so it has no
partial top levels.  The fill is layer thickness.  Orange
lines are the bottoms of every tenth layer, pale blue-gray is land ice and
tan is the seafloor.

```{figure} ice_shelf_vertical_coordinate/transects_map.jpg
:alt: Ice draft around Antarctica, with four transects
:width: 60%

The ice draft and the transects.  Each starts at its dot, in open water.
```

```{figure} ice_shelf_vertical_coordinate/filchner_ronne_front.jpg
:alt: z-star and the coordinate across the Filchner-Ronne calving front
:width: 100%

The Filchner-Ronne calving front.  z-star bends every level down from the
surface, so its top layers are thin and slope steeply across the front.  The
coordinate drops the reference levels above the draft, so the layers under
the ice continue those of the open ocean.
```

```{figure} ice_shelf_vertical_coordinate/filchner_ronne_trough.jpg
:alt: z-star and the coordinate in a deep trough near the Filchner-Ronne grounding line
:width: 100%

A deep trough near the Filchner-Ronne grounding line, where the draft
deepens by about 800 m.  z-star's top layers are a few meters thick, while
the coordinate's stay near their reference thicknesses.  Where neighboring
columns start at different levels, their top layers end in short walls.
```

```{figure} ice_shelf_vertical_coordinate/totten_front.jpg
:alt: z-star and the coordinate across the Totten calving front
:width: 100%

The Totten calving front, which ends on a cliff.  The cells at 139 to 150 km
are a thin film under ice that nearly reaches the bed.  Beyond them, under a
970 m draft, z-star squeezes all its levels into a 180 m column, while the
coordinate keeps about ten near their reference thicknesses.
```

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

### Requirement: Top layers under ice shelves connect to at least two neighbors

The top layer of a column under an ice shelf shall share its level with at
least two neighboring columns, where the column has such a level.

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
column's layers shall follow the new geometry by the same rules as at init.

### Requirement: The layers depend only on the current geometry

Evolving-geometry stage.  Once a change in the ice geometry has been
applied, a run's layers shall be those of an initial state made from the
same geometry and the same ice shelves, whatever geometry the run started
from.

### Requirement: Small changes in the geometry make small changes in the layers

Evolving-geometry stage.  A small change in the ice geometry, including one
near any threshold of the coordinate, shall make only a small change in the
layers, so that a geometry that wavers does not reshape its columns again
and again.

### Requirement: Levels come and go without changing the ocean's content

Evolving-geometry stage.  When a column's layers change, including when it
gains or loses top levels, its heat, salt and momentum shall be conserved
and continuous in time.

## Algorithm Design

### Algorithm Design: Layers under ice shelves stay near their reference thicknesses

Each ice shelf (see below) has a top depth $z_t$, the 20th percentile of
the drafts of its front cells.  The percentile is weighted by each front's
length (`dvEdge`) and its front weight (see below).  Floating cells of the
shelf start at this depth, and film cells at the surface.  A shelf with no
front that faces open water starts at the surface.  A column's top depth is
no deeper than leaves it `min_vert_levels` levels.

Reference levels lying entirely above $z_t$ are dropped.  With depths
positive down, level $k$ spanning $z_k$ to $z_{k+1}$ and
$\Delta z_k = z_{k+1} - z_k$, the level $k_t$ containing $z_t$ keeps the
fraction

$$
f = \frac{z_{k_t+1} - z_t}{\Delta z_{k_t}}
$$

of its reference thickness as a partial top level.  Where $f$ is below a
minimum fraction, the partial level merges into the level below, which
gains $f \Delta z_{k_t}$.  Either way, the reference thicknesses
$\Delta z'_k$ that remain sum to $H - z_t$, with $H$ the bed depth.  They
follow z-star, and the resting thickness, which MPAS-Ocean requires to sum
to $H$, is

$$
h_{rest,k} = \Delta z'_k \frac{H}{H - z_t},
\qquad
h_k = h_{rest,k} \frac{H + \eta}{H}
$$

so a layer under a draft near $z_t$ is close to its reference thickness.

> **Rationale.**  With whole levels, the shallowest front draft let one
> front cell with a draft of a few meters keep the Ross Ice Shelf at 3 to 4
> dropped levels, with top layers 1.5–5 m thick.  The 10th and 20th
> percentiles gave the same flow through a full so12to30km dynamic
> adjustment, and the 20th needs fewer extra drops between cells inside a
> shelf (1042 against 1392).

### Algorithm Design: Layers at calving fronts line up with the open ocean

A front is an edge between a cell under land ice and an open-water cell,
neither of them a film, where the open cell's bed is below the ice cell's
draft by more than a film column: `min_vert_levels` times the film's layer
thickness.  Each front has a weight, the product of two linear ramps from 0
to 1: one as the open cell's bed goes from a film column below the draft to
a film column plus the reference thickness at the draft, and one as the ice
cell's column goes from one film column to two.  A front cell's top depth is its own
draft $d$ blended with its shelf's top depth by its largest front weight
$w$:

$$
z_t = w\,d + (1 - w)\,z_{t,shelf}
$$

Where $w$ is 1, the cell's layers are the reference levels below its draft,
so they face open water at the same depths, even where its draft is
shallower than its shelf's top depth.

> **Rationale.**  Ice that nearly reaches the bed may face open water whose
> bed is above the draft.  Taking its own draft would leave its cell a thin
> column of a few thick layers, which escape the wetting-and-drying velocity
> ramp and burst against a thicker neighbor.  Such an edge is therefore not
> a front.  The weight keeps a cell's top depth, and its shelf's, from
> jumping when an edge becomes or stops being a front.

### Algorithm Design: Neighboring columns are not too steep

For an edge between cells $a$ and $b$ with shared layers $k$, interface
heights $z^{top}$ and $z^{bot}$ and thicknesses $h$,

$$
r_{x1} = \max_k \frac{\left|z^{top}_{a,k} - z^{top}_{b,k}
+ z^{bot}_{a,k} - z^{bot}_{b,k}\right|}{h_{a,k} + h_{b,k}}
$$

After the shelf and front top depths, on each edge touching land ice with no
film cell whose $r_{x1}$ exceeds the maximum (30 by default), the cell with
the deeper draft takes the shallowest deeper top depth that brings the edge
to the maximum, with its neighbor at its shelf or front top depth.  Where
none does, it keeps only `min_vert_levels` levels.  A cell takes the deepest
top depth over its edges.  Where both cells of an edge go deeper, $r_{x1}$
can stay above the maximum, but rarely: with whole levels on so12to30km and
the 20th percentile, the 99th percentile of $r_{x1}$ under the ice is 26.

### Algorithm Design: Top layers under ice shelves connect to at least two neighbors

An edge is active at a level when both of its cells have that level.  After
the partial top levels are set, each column that starts below the surface
and whose top level has fewer than two active edges merges that level into
the level below.  The level below gains its thickness, as when a partial
top level merges.  A column keeps at least `min_vert_levels` levels.
Merging a level can take an active edge from a neighbor's top level, so the
columns are revisited until none changes.  A column with no level that has
two active edges, given its neighbors' levels before any merge, keeps its
levels.

A merge never adds an active edge.  The columns therefore settle on the
shallowest top levels that meet the rule, in whatever order they are
visited.

> **Rationale.**  At a minimum fraction of 0.5, the so12to30km dynamic
> adjustment grew jets of 3.4 m/s at a Weddell Sea front and 5.8 m/s at the
> Cook Ice Shelf front.  The Cook jet then broke into spikes of 20–34 m/s.
> At both, the ice cell's top level had a single active edge, to open
> water.  A momentum budget showed the same cross-front force at that level
> and the one below.  Below, the Coriolis term opposes the flow.  At the top
> level, only the open cell's half of the TRiSK stencil contributes, so the
> flow cannot reach geostrophic balance.  On so12to30km at a minimum fraction
> of 0.1, the rule merges levels in 179 columns:
>
> - 100 merge one level and the most merge 14;
> - the merged layer is twice its level's thickness at the median and 9
>   times at most;
> - changes spread at most 3 cells from a column that broke the rule at the
>   start;
> - 17 columns have no level with two active edges, and their flow stayed
>   below 0.17 m/s.

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

The top depths are computed from the geometric draft (`ssh`), bed depth,
land-ice and film masks and the mesh, before the vertical coordinate is
built, and the coordinate starts each column at its top depth.  The
p-star coordinate ([pstar_init](pstar_init.md)) compares geometric depths
with its reference pseudo-depths, which differ by the ratio of the density
to the reference density, a few percent at most.

### Algorithm Design: The coordinate follows the ice as it evolves

Evolving-geometry stage.  Each time the coupler updates the land-ice fields,
the ocean model recomputes the top depths with the algorithms above, from
the current draft (the SSH under land ice), bed depth and masks:

1. Find the fronts and their weights.
2. Gather each shelf's weighted front drafts with one global sum, which
   gives each shelf's top depth.
3. Compute the front and rx1 top depths, which need only each cell's
   neighbors.
4. Merge top levels with fewer than two active edges, in passes with a halo
   exchange of `minLevelCell` between them (see the open questions).

Over the coupling interval that follows, each column's top depth moves
linearly in time from its old value to its new one, and its resting
thicknesses follow at each time step.

The shelves are the `iceShelfGroup` of the initial state and never change.

### Algorithm Design: The layers depend only on the current geometry

Evolving-geometry stage.  The top depths come from the current geometry and
the shelves alone, with no margin.  The previous top depths are used only
to move each column across a coupling interval.  At its end, each column's
top depth is the one computed from the latest geometry, so the layers match
those of an initial state made from that geometry.

### Algorithm Design: Small changes in the geometry make small changes in the layers

Evolving-geometry stage.  The top depths are not rounded to whole levels,
and the front weights ramp rather than switch, so the top depths change
continuously with the geometry.  Interfaces then move continuously, with two
exceptions:

- the interface between a partial top level and the level below appears or
  disappears where the partial fraction crosses its minimum, which mixes
  those two layers;
- a top level that loses or regains its second active edge merges or splits
  off, and neighboring top levels can follow;
- a cell that becomes or stops being a film changes its top depth at once,
  but its column is then only a film thick.

A geometry that wavers near any of these thresholds can still cause these
changes, at most once per coupling interval, but each one is small.  The shelf top
depths and the rx1 search are not yet continuous everywhere; see the open
questions.

### Algorithm Design: Levels come and go without changing the ocean's content

Evolving-geometry stage.  As a top depth moves, the resting thicknesses
change and the interfaces move with them.  The ALE vertical transport
carries tracers and momentum between layers, as it does when the interfaces
move with the SSH.  When a partial top level merges into the level below,
the merged layer takes the sum of the two layers' thicknesses and tracer
contents, and on each edge their thickness-weighted velocity.  When a level
splits off again, both layers start with the properties of the layer they
come from.

## Implementation

### Implementation: Layers under ice shelves stay near their reference thicknesses

`polaris.ocean.vertical.ice_shelf.compute_ice_shelf_top_depth()` takes the
config, the mesh, `ssh`, `bottomDepth`, `landIceMask`, the film mask and the
film's layer thickness, and returns the top depth of each column and
`iceShelfGroup`.  It builds the reference column of each cell with
the z-star helpers, including partial bottom cells, to find each cell's
levels.  The options, in `[vertical_grid]`, are:

```cfg
[vertical_grid]

# how the top of each column under an ice shelf is chosen: "surface" (the
# top reference level) or "front_draft" (a top depth set by the shelf's
# calving-front drafts)
ice_shelf_top_level = surface

# the percentile of each shelf's calving-front drafts, weighted by the length
# of front, that sets the shelf's top depth
ice_shelf_front_percentile = 20.0

# the smallest fraction of its reference thickness that a partial top level
# keeps before it merges into the level below
ice_shelf_min_top_fraction = 0.1

# the largest rx1 allowed between columns under ice shelves
ice_shelf_max_rx1 = 30.0
```

With `surface`, the function returns zeros.

### Implementation: Layers at calving fronts line up with the open ocean

The front test, the front weights and each front cell's top depth are in the
same function, with the film layer thickness passed by the caller from its
own options, since each task with a film already has one.

### Implementation: Neighboring columns are not too steep

The deeper top depths use the layers of the z-star column at the initial
`ssh`.  Only edges above the maximum are visited, each with a search over
the top depths of its deeper cell, between its shelf or front top depth and
the deepest one that leaves it `min_vert_levels` levels.

### Implementation: Top layers under ice shelves connect to at least two neighbors

`start_columns_at_top_depth()` merges the top levels after the partial top
levels, given `cellsOnEdge`, which z-star and p-star take from their
dataset.  It applies to columns whose top depth is below the surface, so
film cells and open water are unchanged.

### Implementation: Each ice shelf is known at init for every possible ocean cell

`compute_ice_shelf_groups()` labels the floating regions with
`scipy.sparse.csgraph.connected_components()` and grows them into grounded
cells one ring at a time.

### Implementation: Ocean tasks with ice-shelf cavities can use the coordinate

- `init_vertical_coord()` and `init_z_star_vertical_coord()` take an
  optional `top_depth`, capped so a column keeps `min_vert_levels` levels.
  They set `minLevelCell` below the dropped levels, cut or merge the partial
  top level, and rescale `restingThickness` to sum to `bottomDepth`.
- `init_pstar_vertical_coord()` and `PStarInitStep.run_pstar_init()` take
  the same argument, and `RefPseudoThickness` is rescaled to sum to the
  pseudo-depth of the bed.
- `realistic_global`: its p-star init step computes the top depths with the
  draft and film mask of each p-star solve, and its cavity options set
  `ice_shelf_top_level = front_draft`.  The initial state writes
  `iceShelfGroup`.
- ISOMIP+ and MISOMIP can pass top depths to `init_vertical_coord()` in the
  same way.  They are not changed in the fixed-geometry stage.

### Implementation: The coordinate follows the ice as it evolves

Evolving-geometry stage.  This stage is mostly MPAS-Ocean work, and Omega
work once Omega has ice-shelf cavities.

- The ocean model computes the top depths as
  `compute_ice_shelf_top_depth()` does, after each update of the land-ice
  fields from the coupler.  It reads `iceShelfGroup` from the initial
  state, and the `[vertical_grid]` options above become namelist options.
- `restingThickness`, `minLevelCell` and the fields derived from them, such
  as the first level of each edge and vertex and the cell and edge masks,
  become time-varying.  They and the top depths at the last two updates go
  in the restart file.
- Polaris keeps the Python function as the reference.  A Polaris task with
  evolving geometry turns the top depths on in the model's namelist, and
  its initial state supplies the first top depths and `iceShelfGroup`.

### Implementation: The layers depend only on the current geometry

Evolving-geometry stage.  The coordinate keeps no state beyond the top
depths at the last two updates, which the interpolation across a coupling
interval needs.

### Implementation: Small changes in the geometry make small changes in the layers

Evolving-geometry stage.  `ice_shelf_min_top_fraction` becomes a namelist
option.  The ramps of the front weights have no options.

### Implementation: Levels come and go without changing the ocean's content

Evolving-geometry stage.  MPAS-Ocean's ALE thickness is `restingThickness`
plus a share of the SSH, so updating `restingThickness` at each time step
moves the interfaces, and the existing vertical transport moves tracers and
momentum with them.  A merge or split is applied in the time step in which
the partial fraction crosses its minimum.

## Testing

### Testing and Validation: Layers under ice shelves stay near their reference thicknesses

Unit tests of the weighted percentile and of the top depths on a small
synthetic mesh.

### Testing and Validation: Layers at calving fronts line up with the open ocean

A unit test that a front cell takes its own draft as its top depth, that an
edge facing a shallower bed is not a front, and that the weight ramps
between them.

### Testing and Validation: Neighboring columns are not too steep

A unit test that a steep edge gets the shallowest deeper top depth that
meets the maximum.

### Testing and Validation: Top layers under ice shelves connect to at least two neighbors

Unit tests that a top level with one active edge merges into the level
below, that a merge can make a neighbor merge, that a column with no level
with two active edges keeps its levels, and that columns starting at the
surface are unchanged.  In the so12to30km and qu30km initial states, the
only top levels left with fewer than two active edges are in columns that
have no level with two.

### Testing and Validation: Each ice shelf is known at init for every possible ocean cell

A unit test with two floating regions, grounded cells reached from each,
and a grounded region reached from neither.

### Testing and Validation: Ocean tasks with ice-shelf cavities can use the coordinate

Unit tests that z-star and p-star columns with a top depth sum to the bed
depth, with partial top levels above and below the minimum fraction, and
that the default leaves them unchanged.  The `realistic_global`
dynamic adjustment on so12to30km and qu30km with `grounding_line` runs to
the end of `simulation`, with flow under the ice below 0.6 m/s.

With GM, this needs MPAS-Ocean to limit the GM bolus velocity with wetting
and drying, as it does the submesoscale velocity.  Next to a thin film at a
calving front, the bolus velocity otherwise reaches 2 m/s.  MPAS-Ocean also
needs fixes for columns whose top levels are inactive.

### Testing and Validation: The coordinate follows the ice as it evolves

Evolving-geometry stage.  The model's top depths match those of the Python
function for the same geometry, at the start of a run and after the
geometry has changed.  The ISOMIP+ tasks whose ice geometry changes in time
run with the coordinate on, and then coupled MISOMIP runs.

### Testing and Validation: The layers depend only on the current geometry

Evolving-geometry stage.  In the ISOMIP+ runs, at the end of a coupling
interval, the model's layers match those of a Polaris initial state made
from the geometry at that time with the run's shelves.

### Testing and Validation: Small changes in the geometry make small changes in the layers

Evolving-geometry stage.  A unit test sweeps a draft through a level
boundary and back.  The interfaces move continuously except for one merge
and one split, and the layers are the same at the same draft in both
directions.

### Testing and Validation: Levels come and go without changing the ocean's content

Evolving-geometry stage.  In those runs, the global heat and salt content
change only through the surface and land-ice fluxes, to round-off, as top
depths move and partial top levels merge and split.

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
  run-time top depths and resting thicknesses that change during a run in
  the ocean model.
- **One global sum per coupling interval, not top depths from neighbors
  alone.**  A top depth computed from each cell's neighbors cannot know its
  shelf's percentile.  The sum is a few values per shelf, or one per shelf
  and level for a histogram, once per coupling interval.
- **Partial top levels, not whole levels with hysteresis.**  Any whole-level
  rule driven by the current geometry has thresholds, and a draft that stays
  at one changes the level at every update, with or without relaxation
  toward it.  Only hysteresis stops that, and it makes the layers depend on
  the geometry's history.  A partial top level lets the coordinate depend on
  the current geometry alone, and a merge or split moves one interface
  instead of the whole column.
- **A partial top level at a shared top depth, not at each column's own
  draft.**  Cells in a shelf share their top depth, so they share the
  fraction of their partial level, and z-star spreads it smoothly.
  Fractions differ only at fronts and steep edges, where levels already
  jump.  A z-level coordinate with partial top cells at each column's own
  draft was tried before, and its stair-steps at the ice–ocean interface
  made flow and melt rates very noisy.
- **A minimum fraction of 0.1, as for partial bottom cells.**  A merged
  layer is at most $1 + f$ times its reference thickness, so a large
  minimum makes thick layers.  On so12to30km, minimums of 0.1, 0.25 and
  0.75 all ran the dynamic adjustment to the end, with flow under the ice
  no faster than 0.52 m/s.
- **Merge top levels with one active edge, not tune the minimum fraction.**
  Minimums of 0.25 and 0.75 moved the two cells that jetted out of that
  geometry, but left 15 and 26 other top levels whose one active edge faces
  open water.
- **A merged top level joins the level below, not the whole column.**  The
  interfaces below stay level with the neighbors', as when a partial top
  level merges.  Stretching the whole column instead would make the
  so12to30km columns 1.08 times thicker at the median and 8 times at most,
  but move every interface in them.
- **Columns with no level that has two active edges keep their levels.**
  No merge would give them a second active edge.
- **Partial top levels in both stages.**  An evolving run starts from a
  Polaris initial state, which must match what the ocean model computes for
  the same geometry.  The example and the whole-level results above come
  from an earlier version that rounded each top depth up to the top of its
  level.
- **The ALE vertical transport, not Lagrangian vertical remapping.**
  Interfaces move continuously, so the vertical transport that already
  moves them with the SSH can carry the change.  A merge or split involves
  only two layers.
- **Moving calving fronts are set aside.**  Cells that start or stop being
  ocean when ice calves or a front advances need more than a change of first
  level.
- **z-star, not a Haney-number coordinate or smoothed geometry.**  Compass's
  Haney-number coordinate digs the bed into "teeth", and smoothing changes
  the ice geometry that MALI will supply.
