(dev-mesh-vector)=

# Mesh Geometry Vectors

`polaris.mesh.vector` holds the small geometric utilities that other mesh
code builds on: the Cartesian coordinates of mesh elements as a single array,
and the unit normal vector of each edge.  Both work the same way on spherical
and planar meshes, so callers do not have to branch on mesh type.

## Coordinates as a single array

MPAS meshes store coordinates as three separate variables per location
(`xCell`, `yCell`, `zCell` and so on).  Anything that does linear algebra
wants them stacked instead.
{py:func}`polaris.mesh.vector.get_coordinate_matrix()` does that for cells,
edges or vertices:

```python
from polaris.mesh.vector import get_coordinate_matrix

# (nCells, R3)
vec_cell = get_coordinate_matrix(ds_mesh, 'cell')
# (nEdges, R3)
vec_edge = get_coordinate_matrix(ds_mesh, 'edge')
```

The `location` argument is `'cell'`, `'edge'` or `'vertex'`, and the new
dimension is named `R3` to match the MPAS convention for three-component
vectors.

## Edge normal vectors

{py:func}`polaris.mesh.vector.compute_edge_normal_vec()` returns the unit
vector normal to each edge, as an `(nEdges, R3)` array:

```python
from polaris.mesh.vector import compute_edge_normal_vec

normal = compute_edge_normal_vec(ds_mesh)
```

The normal points from the first cell on the edge toward the second, which
matches the sign convention MPAS uses for `normalVelocity`.  On a boundary
edge, where only one of `cellsOnEdge` is a real cell, the normal is taken
between the edge location and that cell instead, so it still points out of the
domain.

Periodic planar meshes are handled from the mesh attributes.  If
`is_periodic` is `'YES'`, the cell positions are unwrapped using `x_period`
and `y_period` before the difference is taken, so an edge on the periodic
boundary gets a short normal across the seam rather than a long one spanning
the domain.  A non-periodic mesh uses a period of zero, which makes the
unwrapping a no-op, and a spherical mesh has no `is_periodic` attribute and
takes the same path.

The main consumer is {ref}`dev-mesh-reconstruct`, which projects these normals
into the local tangent plane at each reconstruction point.
