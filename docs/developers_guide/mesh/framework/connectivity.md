(dev-mesh-connectivity)=

# Mesh Connectivity

`polaris.mesh.connectivity` answers questions about which cells of a mesh a
model can actually move a quantity between, given a mask saying which cells
belong to the domain.  Its main use is finding land-locked cells and other
disconnected pockets before a mesh is culled; see the
[design document on land-locked cells](../../../design_docs/land_locked_cells.md)
for the reasoning behind the criteria below.

The key point is that sharing an edge is not the same as being connected.
Whether two neighboring cells are connected depends on the grid staggering of
the model that will use the mesh, so these functions take the mask and return
the connectivity, rather than assuming one answer.

## Active edges

An edge of a cell is *active* when the cell across it is also in the domain.
{py:func}`polaris.mesh.connectivity.active_edge_masks()` returns three
`(nCells, maxEdges)` boolean arrays: whether each local edge is active, and
whether the next and previous edges around the same cell are.  The next and
previous masks are what make vertex questions answerable, since two edges that
are adjacent in a cell's edge ordering meet at a vertex.

Two convenience functions sit on top of it:

- {py:func}`polaris.mesh.connectivity.count_active_edges()` counts the active
  edges of each cell.  An ocean cell on a C-grid needs at least two -- one way
  in and one way out -- and they need not be adjacent.
- {py:func}`polaris.mesh.connectivity.has_active_vertex()` finds cells with at
  least one vertex all of whose surrounding cells are in the domain.  A sea-ice
  cell on a B-grid needs one of these, or there is no velocity point by which
  ice can leave it.

Both evaluate every cell, including cells outside the domain, so mask the
result if that matters.

## Connectivity to seeds

{py:func}`polaris.mesh.connectivity.connected_to_seeds()` flood-fills the
domain from a set of seed cells and returns the cells it reaches.  Cells in
the domain that it does not reach are the disconnected pockets -- inland seas,
land-locked cells, and lakes that a global ocean should not include.

The `link_mask` argument chooses the grid staggering.  The default connects
every active edge, which is the ocean's C-grid connectivity.  For sea ice on a
B-grid, pass {py:func}`polaris.mesh.connectivity.transport_link_mask()`
instead: the velocity that moves ice across an edge is built from the
velocities at that edge's two vertices, so an edge whose vertices are both
inactive carries no flux and does not connect the cells it separates, even
though they share an edge.

Seeds usually come from a handful of known-open locations.
{py:func}`polaris.mesh.connectivity.seed_mask_from_points()` turns longitudes
and latitudes in degrees into a mask on the nearest cell to each point:

```python
from polaris.mesh.connectivity import connected_to_seeds, seed_mask_from_points

seed_mask = seed_mask_from_points(ds_mesh, lon_seed, lat_seed)
connected = connected_to_seeds(ds_mesh, cell_mask, seed_mask)
```

Seeds that land outside the domain are ignored rather than raising, so a seed
point that a particular mesh resolution turns to land does not break the
workflow.
