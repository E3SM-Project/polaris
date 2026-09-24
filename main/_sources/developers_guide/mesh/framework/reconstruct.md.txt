(dev-mesh-reconstruct)=

# Vector Reconstruction

MPAS models carry horizontal vector fields as a single scalar component
normal to each edge (`normalVelocity`, for example).  Analysis, plotting and
coupling all need the full vector at cell centers or vertices instead.
`polaris.mesh.reconstruct` builds the least-squares weights that turn
edge-normal values into a Cartesian vector at those points, and applies them.

The method is the linear least-squares reconstruction of
[Peixoto and Barros (2014)](https://doi.org/10.1016/j.jcp.2014.04.043) on a
two-ring edge stencil (their Figure 5).  See
the [design document on vector reconstruction](../../../design_docs/vector_reconstruction.md)
for the derivation and for why this method was chosen over Perot's; this page
covers only what a caller of the framework needs to know.

## Weights are a property of the mesh

The weights depend on mesh geometry alone, not on the field being
reconstructed, so they are computed once per mesh and stored as mesh fields.
{py:func}`polaris.mesh.reconstruct.compute_reconstruction_weights()` returns a
small dataset with just those fields, and
{py:func}`polaris.mesh.reconstruct.add_reconstruction_weights_to_dataset()`
merges them into a mesh dataset:

```python
from polaris.mesh.reconstruct import add_reconstruction_weights_to_dataset

ds_mesh = add_reconstruction_weights_to_dataset(ds_mesh, location='cell')
```

Both take a `location` of either `'cell'` or `'vertex'` and write three
fields, named after that location:

| location   | stencil                     | edge count                    | weights                     |
|------------|-----------------------------|-------------------------------|-----------------------------|
| `'cell'`   | `reconstructStencilCell`    | `nEdgesReconstructOnCell`     | `reconstructWeightsCell`    |
| `'vertex'` | `reconstructStencilVertex`  | `nEdgesReconstructOnVertex`   | `reconstructWeightsVertex`  |

The stencil holds 1-based edge indices, padded with zeros, and the edge count
says how many of them are valid.  The weights have an extra `R3` dimension
because the reconstructed vector is Cartesian.

`compute_reconstruction_weights()` selects only the coordinate and
connectivity variables it needs before loading anything, so it is safe to hand
it a production mesh with large state and tracer fields attached; those are
never read.  It works with both MPAS-Ocean and Omega naming conventions and
writes output in whichever convention the input used.  The standalone driver
{ref}`dev-ocean-add-reconstruction-weights` wraps it for adding weights to an
existing mesh file from the command line.

## The stencil is two rings of edges

For a cell, the stencil is the union of `edgesOnVertex` over the
`verticesOnCell` of that cell, with duplicates removed — 12 unique edges on a
hexagon and 10 on a pentagon, so it fits the existing `maxEdges2` dimension.
For a vertex, it is the union of `edgesOnVertex` over the one-ring of
neighboring vertices, which is 9 edges on a triangular dual mesh and uses a
`NINE` dimension.

This is a wider stencil than the one-ring `edgesOnCell` that the legacy
`coeffs_reconstruct` field assumes, which is why the stencil is stored
explicitly rather than left implicit in the mesh connectivity.

Some meshes (QU240km among them) mark invalid connectivity entries with
`nIndices + 1` rather than zero.  `compute_reconstruction_weights()` normalizes
those to zero before building the stencil, so callers do not need to.

## Applying the weights

{py:func}`polaris.mesh.reconstruct.tangential_reconstruction()` contracts the
weights against an edge-normal field and returns the three Cartesian
components.  Pass the precomputed `stencil` and `weights` when the mesh already
carries them; otherwise pass `location` and they are built on the fly, which is
much slower and worth avoiding when reconstructing many time slices:

```python
from polaris.mesh.reconstruct import tangential_reconstruction

u_x, u_y, u_z = tangential_reconstruction(
    ds_mesh,
    ds.normalVelocity,
    stencil=ds_mesh.reconstructStencilCell,
    weights=ds_mesh.reconstructWeightsCell,
)
```

The edge-normal field may carry any extra dimensions besides `nEdges` —
`nVertLevels`, `Time` or both.  They are broadcast through unchanged, so a
whole time series of a 3D field is reconstructed in one call.

On a sphere the Cartesian result is usually not what you want to plot.
{py:func}`polaris.mesh.reconstruct.cartesian_to_local_geographic()` rotates it
into zonal, meridional and radial components at the reconstruction point:

```python
from polaris.mesh.reconstruct import cartesian_to_local_geographic

u_zonal, u_merid, u_radial = cartesian_to_local_geographic(
    ds_mesh, u_x, u_y, u_z
)
```

It infers whether the values are cell- or vertex-centered from the dimensions
of `u_x`, so there is no `location` argument.  Because the reconstruction is
tangential, `u_radial` is zero up to truncation error.

On a planar mesh, do not apply this rotation.  The tangent plane is the mesh
plane itself, so `u_x` and `u_y` are already the in-plane components and `u_z`
is zero.

## Planar meshes

The same functions work on planar meshes, but two things differ internally,
and both matter if you are reading the code:

- the rotation to the local tangent plane is the identity, since every
  reconstruction point already lies in the mesh plane; and
- because the identity rotation leaves the edge coordinates absolute rather
  than relative to the reconstruction point, they are translated explicitly.
  Without that, the least-squares fit would be anchored at the mesh origin and
  the constant term would be the field extrapolated there instead of the value
  at the reconstruction point.

Whether a mesh is planar is decided with {ref}`dev-mesh-info`, from the
`on_a_sphere` attribute, so a dataset missing that attribute raises a
`ValueError` rather than being reconstructed as the wrong kind of mesh.

## Validating against a baseline

{py:func}`polaris.mesh.reconstruct.get_reconstruction_validate_vars()` returns
the names of the three fields for a location, in the form
{py:meth}`polaris.Step.add_output_file()` expects:

```python
self.add_output_file(
    filename='reconstruction_weights.nc',
    validate_vars=get_reconstruction_validate_vars(location='cell'),
)
```

See {ref}`dev-mesh-validate` for the equivalent lists for mesh and cell-width
files.

## Internals

The remaining functions in the module — stencil construction, the rotation
matrix, the tangent-plane projection, the Renka (1984) least-squares weights
and the pseudo-inverse solve — are steps of the single pipeline that
`compute_reconstruction_weights()` drives.  They are not part of the API this
page describes, and their signatures may change; read
`polaris/mesh/reconstruct.py` if you need them.
