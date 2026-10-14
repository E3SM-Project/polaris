# Land-Locked Cells in the Ocean and Sea-Ice Domains

date: 2026/08/11

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

The `topo/cull` mask step of the `e3sm/init` component removes cells in
which sea ice would become trapped, and cells through which the ocean
cannot circulate. It does this by calling
{py:func}`mpas_tools.ocean.coastline_alteration.add_land_locked_cells_to_mask`
twice, once for the ocean domain and once for the ocean without ice-shelf
cavities, and following each call with a flood fill.

That routine knows nothing about land ice and cannot tell the two domains
apart, so it applies one fixed pair of criteria to both. Three consequences
follow. The sea-ice criterion, which exists because MPAS-Seaice is a B-grid
with velocities at vertices, is applied to ice-shelf cavities where sea ice
never forms. The ocean criterion is applied to a domain the ocean model does
not run on. And because both criteria act only poleward of a latitude
threshold chosen for sea ice, dead-end ocean cells at lower latitudes are
never examined at all: roughly fifty cells per unified mesh survive with a
single usable edge.

This design replaces the two calls with a single pass implemented in Polaris
that computes both cull masks together, with the land-ice mask available
throughout, and applies to each domain the criterion its model's grid
actually requires. It also makes the relationship between the two domains
exact: they differ by ice-shelf cavities and by nothing else.

Success means that the requirements below hold by construction on every
supported mesh and every Antarctic boundary convention, are checked at the
end of the mask step, and no longer depend on the behaviour of an external
routine.

This capability is implemented in Polaris rather than contributed back to
MPAS-Tools. Other tools may continue to use
`add_land_locked_cells_to_mask`; there is no requirement to stay in sync,
and E3SM v4 meshes will be produced with Polaris, so their provenance is
unambiguous.

## Current behavior

The two grids place different demands on the mesh.

**MPAS-Seaice is a B-grid**: velocities live at vertices. A vertex is usable
only if every cell around it is in the sea-ice domain. A cell with no usable
vertex has no velocity point by which ice can leave it, so ice drifting in
accumulates indefinitely.

**MPAS-Ocean and Omega are C-grids**: normal velocities live at edges. The
ocean's requirement is a count rather than a geometry. A cell needs two
edges it can move water through, so that there is a way in and a way out. No
condition on vertices applies.

The B-grid criterion is strictly the stronger. An active vertex has all
three surrounding cells in the domain, so the two edges of the cell meeting
there are both active: one active vertex implies two active edges. The
converse fails, since a cell may have two active edges on opposite sides and
no active vertex at all.

Measured on `u.oi30.lr10` for all three Antarctic boundary conventions, the
current implementation leaves 51 to 55 cells per mesh with fewer than two
active edges, every one of them equatorward of the 43-degree threshold and
therefore never examined. All have exactly one active edge; none has zero,
and none lies on a critical ocean passage. The vertex criterion fares
better, with no violations anywhere it is meant to apply.

Such cells do not destabilize MPAS-Ocean. A cell with one active edge is
well posed; it simply has no through-flow, filling and draining through a
single face. The cost is a stagnant pocket that can trap tracers and hold
spurious local extrema, together with a wasted cell and its time-step cost.

## Requirements

### Requirement: grid-appropriate land-locked criteria

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Every cell of the `ocean` domain and every cell of the `ocean_no_cavities`
domain must have at least two active edges, meaning edges shared with
another cell of the same domain. The two edges need not be adjacent and no
active vertex is required. This applies globally, not only poleward of the
sea-ice latitude threshold. Removing the cavities from `ocean` can take a
cell below two active edges, so the criterion must be enforced on
`ocean_no_cavities` in its own right rather than inherited.

Every cell of the `ocean_no_cavities` domain poleward of the sea-ice
latitude threshold must in addition have at least one active vertex, a
vertex all of whose surrounding cells are in that domain.

The vertex criterion must never be applied to the `ocean` domain. Since the
vertex criterion implies the edge criterion, the edge criterion is
automatic on `ocean_no_cavities` poleward of the threshold and must still be
enforced there equatorward of it.

### Requirement: connectivity on the appropriate graph

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Every cell of the `ocean` domain must be reachable from the global open
ocean through edges shared with other cells of that domain.

Sea ice must not accumulate where it cannot escape. The velocity that moves
ice across an edge is built from the velocities at that edge's two
vertices, so an edge whose vertices are both inactive carries no flux and
does not connect the cells it separates, even though they share an edge.
Every cell of the `ocean_no_cavities` domain in which sea ice can form must
therefore be able to reach the global open ocean over the reduced graph of
edges having at least one active vertex.

The target is the equatorward part of the sea-ice domain, not the global
open ocean. Ice escapes by drifting to where it melts, and cells
equatorward of `sea_ice_latitude_threshold` form no ice, so they cannot be
affected by this requirement and instead serve as its seeds. Concretely,
every cell of `ocean_no_cavities` poleward of the threshold must reach some
cell of `ocean_no_cavities` equatorward of it.

Seeding this way is what keeps the requirement from deleting whole seas.
Transport isolation is symmetric: ice that cannot leave a basin cannot
enter it either, so a basin that forms no ice accumulates none. On
`u.oi30.lr10` the Mediterranean, the Red Sea and the Sea of Marmara are all
transport-isolated from the world ocean, because Gibraltar, Bab-el-Mandeb
and the Dardanelles are too narrow at 30 km for any edge there to have an
active vertex. Seeded from the equatorward band, each of them contains or
reaches its own seeds and is kept. A basin straddling the threshold is kept
for the right reason: ice forming in its poleward part can drift into its
equatorward part and melt there.

This also avoids a fatal difficulty with seeding the sea-ice fill from the
`geometric_features` ocean seed points, as the ocean fill does. Those
points span latitudes 65 degrees south to 10 degrees north, and **none lies
poleward of 43 degrees north**, so a sea-ice fill seeded from them and
restricted to the ice-forming region would have no seed at all in the
northern hemisphere.

The step must fail if `ocean_no_cavities` has no cells equatorward of the
threshold, which would leave this fill with no seeds and silently remove
the entire sea-ice domain. That is only reachable by mis-setting the
threshold, but the failure mode is severe enough to check.

### Requirement: consistent domains and meaningful labels

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Every cell that is in `ocean` but not in `ocean_no_cavities` must be covered
by land ice. A cell removed from `ocean_no_cavities` to satisfy the sea-ice
criteria must therefore also be removed from `ocean` unless it is a cavity
cell; the ocean does not keep an open-water embayment that sea ice cannot
use.

`ocean_no_cavities` must remain a subset of `ocean`, `land` must remain the
exact complement of `ocean_no_cavities`, and a cell removed from `ocean`
must also be removed from `ocean_no_cavities`.

A cell on a critical ocean passage must not be removed by any of the above.
If satisfying the criteria would require removing one, that indicates a
poorly formed critical passage: the error must name the transect
responsible and state that it may need modification in `geometric_features`.
Disabling individual passages per mesh is out of scope unless it proves
unavoidable.

A cell removed for connectivity or sea-ice reasons must not thereby be
labelled as land ice. The land-ice mask must mean land ice, and the
ice-shelf cavity cells must be exactly `ocean` minus `ocean_no_cavities`.

## Algorithm Design

### Algorithm Design: grid-appropriate land-locked criteria

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

For a cell mask defining a domain, a neighbor across a local edge is active
when it exists and belongs to the domain. The count of active edges per cell
gives the edge criterion directly. Two edges of a cell that are adjacent in
the cell's edge ordering meet at a vertex, and that vertex is active when
the neighbors across both edges are active, so the vertex criterion is the
existence of an adjacent pair of active edges.

Both are evaluated as whole-array operations over the base mesh using
`cellsOnCell` and `nEdgesOnCell`, with the next and previous neighbor
arrays formed by rotating the local edge index modulo `nEdgesOnCell`.

Removal is iterative within a pass, since removing one cell can take a
neighbor below its threshold, and it is monotone: cells are only ever
removed. A pass therefore terminates.

### Algorithm Design: connectivity on the appropriate graph

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Ocean connectivity is a flood fill over cell adjacency restricted to the
domain. Sea-ice connectivity is the same fill over the subgraph in which an
edge is retained only if at least one of its two vertices is active. On a
Voronoi mesh the three cells meeting at a vertex are pairwise edge-adjacent,
so this is equivalently a fill through active vertices. A link requires both
of its cells to be in the domain, not only the neighbor; a graph built
without that restriction joins separate basins through the land cells
between them.

The ocean fill starts from the `geometric_features` ocean seed points,
replacing the hard-coded latitude and longitude boxes used inside
`add_land_locked_cells_to_mask`, so one notion of "open ocean" serves the
whole workflow. The sea-ice fill instead seeds itself from the sea-ice
domain equatorward of the threshold:

```python
seeds = no_cavities & (np.abs(lat_cell) < threshold)
reachable = connected_to_seeds(
    ds_mesh, no_cavities, seeds,
    link_mask=transport_link_mask(ds_mesh, no_cavities),
)
remove = no_cavities & ~reachable
```

No latitude test is needed on `remove`: a cell equatorward of the threshold
is a seed and is therefore always reachable, so only poleward cells can be
removed. No region masks are needed either, which matters because
rasterizing `geometric_features` regions onto a base mesh is expensive at
these resolutions.

Measured on `u.oi30.lr10`, this removes no cells under any of the three
Antarctic boundary conventions, with about 330,000 seeds in each case. The
requirement therefore acts as a guard for future meshes rather than a
change to existing ones.

### Algorithm Design: consistent domains and meaningful labels

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The two domains are refined together rather than in sequence:

1. Form candidate `ocean` and `ocean_no_cavities` masks, the latter being
   the former minus the land ice, both carrying the critical land blockages
   and critical ocean passages.
2. Enforce the edge criterion on `ocean`, then ocean connectivity.
3. Remove from `ocean_no_cavities` everything removed from `ocean`.
4. Enforce the vertex criterion on `ocean_no_cavities` poleward of the
   threshold and the edge criterion equatorward of it, then sea-ice
   connectivity.
5. Remove from `ocean` any cell dropped in step 4 that is not a cavity cell.
6. Repeat from step 2 until neither domain changes.
7. Take `land` as the complement of `ocean_no_cavities`.
8. Leave the land-ice mask as the ice mask; the cavity cells are then
   exactly `ocean` minus `ocean_no_cavities`.
9. Report any critical passage cell that the criteria would have removed,
   naming the transect.

Step 6 terminates because every pass only removes cells. Long, narrow
channels with no active vertices are expected to be removed, and needing
more than one alternation to reach that state is acceptable.

Under the `calving_front` convention no cell is both ocean and land ice once
the critical passages have been applied, so `ocean` minus
`ocean_no_cavities` is empty and the two domains are necessarily identical.
The equality that the cull-mask consistency check currently verifies then
follows from the requirements rather than from the behaviour of an external
routine.

## Implementation

### Implementation: grid-appropriate land-locked criteria

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

A dependency-light leaf module provides the mesh-connectivity primitives as
pure functions of a base-mesh dataset and a cell mask: active-edge counts,
active-vertex presence, the reduced sea-ice transport graph, and a flood
fill from seed points over a supplied graph. Nothing in it depends on
`CullMaskStep`, so it is testable on small synthetic meshes.

### Implementation: connectivity on the appropriate graph

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The flood fill is expressed as a connected-components problem on a sparse
adjacency matrix built from `cellsOnCell`, with the retained-edge mask
supplied by the caller. This serves both the ocean and the sea-ice graph
without duplicating the fill itself.

The sea-ice fill needs no new inputs: its seeds come from `latCell` and the
candidate mask, both already in hand. The only new failure path is the
empty-seed check, raised before the fill runs.

### Implementation: consistent domains and meaningful labels

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

A single function takes the base mesh, the candidate masks, the land-ice
mask, the critical-transect masks and the latitude threshold, and returns
both refined masks together with any critical-passage violations. This
replaces both `add_land_locked_cells_to_mask` calls and both ocean flood
fills in `CullMaskStep`, along with the step that currently adds
connectivity removals to the land-ice mask.

Naming the transect responsible for a critical-passage violation requires
the per-transect masks and `transectNames` to reach the check.
`_create_critical_transects` currently collapses them into a single combined
mask, so the check consults `critical_ocean_transects_widened.nc` instead.

The cull-mask consistency check gains the edge and vertex criteria as
post-conditions, and its `calving_front` equality is re-derived from the
domain relationship rather than asserted.

## Testing

### Testing and Validation: grid-appropriate land-locked criteria

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Unit tests on small synthetic meshes covering a cell with one active edge, a
cell with two non-adjacent active edges and no active vertex, a cell with an
adjacent pair, and a cascade in which removing one cell takes a neighbor
below the threshold. The equatorward and poleward cases are tested
separately so the latitude scoping is exercised.

### Testing and Validation: connectivity on the appropriate graph

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

Unit tests covering a pocket that is edge-connected to the seeded region but
joined only by edges with two inactive vertices: sea-ice connectivity must
remove it when it lies wholly poleward of the threshold and keep it when it
straddles or lies equatorward, while ocean connectivity keeps it in every
case. Also a region disconnected outright, which both must remove, and a
threshold that leaves no equatorward cells, which must raise.

On real meshes, the Mediterranean, Red Sea and Sea of Marmara must survive
in both ocean domains on every convention. They are the cases this seeding
exists to protect, and their loss would be the loudest possible signal that
the requirement has been mis-scoped.

### Testing and Validation: consistent domains and meaningful labels

Date last modified: 2026/08/11

Contributors: Xylar Asay-Davis, Claude

The existing cull-mask consistency tests are extended with the new
post-conditions. On real meshes, `u.oi240.lr240` and `u.oi30.lr10` are
culled under all three Antarctic boundary conventions and checked for the
domain relationships, for the absence of cells with fewer than two active
edges, and for the absence of vertex-criterion violations poleward of the
threshold. The `calving_front` runs must additionally show `ocean` and
`ocean_no_cavities` identical.

Because this changes which cells are culled, baseline comparisons against
`main` will differ on every mesh, which is the expected outcome rather than
a failure.

## `bedrock_zero` is available but not yet fully supported

On `u.oi30.lr10` with `antarctic_boundary_convention = bedrock_zero`, the
cull-mask step passes every check in this document and then fails the
`dcEdge` diagnostic at sixteen edges around ten cells near 69.7 degrees
south, 140 degrees east, in Adelie Land.

The ten cells are ice-shelf cavity cells: in `ocean`, out of
`ocean_no_cavities`, all flagged as land ice. Under `bedrock_zero` the
ocean extends into subglacial basins below sea level, and these cells sit
in one. They are meshed at 11 to 19 km against a 30 km ocean background,
so their `dcEdge` ratio falls to 0.373 against a floor of 0.65.

The cause predates this design. The coastline product for `bedrock_zero`
takes its candidate ocean to be everything below sea level, which does
include the basin, and then flood fills at the 0.125 degree coastline
resolution, where the barrier between the basin and the sea is unbroken.
The basin is therefore dropped, and the sizing field assigns it land or
river resolution. The MPAS cull works at mesh scale, where the same
barrier is diluted, so its own flood fill connects the basin and keeps it
as ocean. That is Mechanism A of the `unified_mesh_cull_leak` design doc,
and `build_effective_ocean_mask` exists to compensate for it, but its
hysteresis growth does not bridge this barrier under this convention.

What changed is only that the old implementation hid it. Its land-locked
check applied the B-grid vertex criterion to the ocean, which removed
exactly these cells. Under the criteria set out here the ocean keeps them,
because a C-grid needs only two active edges. The margin was already thin:
the same mesh under the old code reported a minimum ratio of 0.654 against
the same 0.65 floor.

`calving_front`, which is the default, and `grounding_line` are unaffected,
reporting minimum ratios of 0.664 and 0.743.

Fixing this means teaching the sizing field's cull emulation to bridge
barriers that the mesh-scale cull dilutes. That belongs to the
`unified_mesh_cull_leak` subsystem: it would change the sizing field and
therefore the base mesh of every unified mesh, which is well outside the
scope of the land-locked criteria.

The convention is therefore available but not yet ready for production
use, and is expected to need further debugging before it is. It behaves
correctly at 240 km, where the base mesh is uniform and no land or river
resolution exists to leak.
