# Vector Reconstruction at MPAS Cell Centers

date: 2026/04/06

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

## Summary

This design proposes a new workflow for generating cell-center vector
reconstruction coefficients for MPAS meshes in Python within `polaris`. The
primary goal is for `polaris` to compute mesh-based reconstruction metadata and
coefficients and write them to an MPAS mesh. A later MPAS-Ocean or Omega
implementation could read those mesh fields, but changes in those codes are out
of scope for this PR. Python is the intended home for coefficient generation
because it provides the most flexibility for experimenting with reconstruction
methods, stencil choices, and mesh-field layouts. The intent is that this
Python workflow will eventually become the authoritative way to generate these
coefficients, with follow-on PRs adding or updating support in MPAS-Ocean and
Omega to consume the stored mesh fields.

The initial target field is `normalVelocity`, but the coefficient-generation
workflow should be general enough to apply to any field represented as a scalar
component normal to MPAS edges. The design follows the best-performing
practical methods identified in Peixoto and Barros (2014). The first
implementation should use linear least-squares (LSQ) reconstruction on all cells,
because offline coefficient generation in Python makes the setup cost less
important than simplicity, uniformity, and maintainability. A hybrid method
that combines Perot's inexpensive cell-centered reconstruction on well-aligned
cells with a linear least-squares reconstruction on poorly aligned cells should
be retained as a backup optimization path if runtime performance of the all-LSQ
approach proves insufficient.

The design treats the reconstructed field as the sum of:

$$
\mathbf{u} = \mathbf{u}_t + w \hat{\mathbf{r}},
$$

where $\mathbf{u}_t$ is tangent to the sphere and reconstructed from edge-normal
components, and $w \hat{\mathbf{r}}$ is an optional radial contribution aligned
with the local vertical unit vector. For velocity reconstruction,
`vertVelocityTop` may be supplied on cell interfaces and converted to layer
midpoints; if it is omitted, the radial contribution is assumed to be zero.

Although velocity is the motivating use case, the core reconstruction should be
field-agnostic. The implementation will therefore separate:

- a generic reconstruction of tangential vectors from edge-normal components,
- basis transformations between Cartesian and local geographic coordinates, and
- generic 3D composition from a tangential component and an optional
  interface-centered radial component.

Success means that `polaris` gains a reusable, documented, and testable
coefficient-generation workflow in `polaris/mesh` that:

- computes least-squares reconstruction coefficients and stencil metadata that
  can be stored on an MPAS mesh and consumed at runtime by Omega or MPAS-Ocean,
- establishes Python in `polaris` as the implementation that is expected to
  become the authoritative source for generating these coefficients,
- reconstructs tangential vectors at MPAS cell centers with second-order
  behavior on spherical MPAS meshes,
- supports 3D Cartesian outputs and local zonal/meridional/radial outputs at
  cell centers and layer midpoints, and
- is structured so later extension to arbitrary-point reconstruction can reuse
  the same geometry and reconstruction cache.

## Requirements

### Requirement: Generic Tangential Reconstruction at Cell Centers

Date last modified: 2026/04/04

Contributors:

- Xylar Asay-Davis
- Codex

`polaris` shall support offline generation of reconstruction coefficients for a
tangential vector field at MPAS cell centers from scalar components given
normal to MPAS edges on spherical meshes. The capability must be general enough
to apply to fields other than velocity.

The initial implementation shall focus on reconstruction at cell centers rather
than arbitrary points. The generated coefficients shall use only local mesh
geometry and local edge data, and they shall avoid methods that are known to be
less robust or more expensive than needed for second-order accuracy on MPAS
Voronoi meshes.

The primary output of the implementation shall be coefficient and stencil data
that can be added to an MPAS mesh and used by Omega or MPAS-Ocean at runtime.

### Requirement: 3D Vector Outputs at Layer Midpoints

Date last modified: 2026/04/06

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

`polaris` shall support a generic interface that returns reconstructed vector
fields at cell centers and layer midpoints as:

- 3D Cartesian components, and
- zonal, meridional, and radial components in the local geographic basis.

If a radial interface field is supplied on `nVertLevelsP1`, the reconstructed
vector shall include a radial contribution consistent with the MPAS local
vertical direction. If no radial interface field is supplied, the radial
contribution shall default to zero.

For a horizontal-only reconstruction, the local geographic radial output shall
therefore be zero and may be ignored by downstream users.

For velocity, the corresponding radial interface field is `vertVelocityTop`.

### Requirement: Reusable Precomputation and Extensibility

Date last modified: 2026/04/05

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

The implementation shall support precomputation of mesh-dependent reconstruction
metadata and weights so repeated application to many time slices or vertical
levels is efficient. The implementation shall be organized so later support for
reconstruction to arbitrary points can reuse the same geometry utilities,
stencil selection, and basis transforms without redesigning the core interface.

The implementation shall define a mesh-storage format for reconstruction
coefficients and stencils that can be read directly at runtime by Omega or
MPAS-Ocean.

The implementation shall not rely on online coefficient generation in
MPAS-Ocean or Omega. New reconstruction coefficients shall be generated in
Python in `polaris` and then stored on the mesh for runtime use. Defining those
mesh fields is in scope for this design. Implementing MPAS-Ocean or Omega code
changes to read them is not, but follow-on PRs are expected to add that
support.

## Algorithm Design

### Algorithm Design: Generic Tangential Reconstruction at Cell Centers

Date last modified: 2026/04/04

Contributors:

- Xylar Asay-Davis
- Codex

Let $u_e$ be the scalar component of a tangential vector field normal to edge
$e$, evaluated at the edge midpoint. The goal is to reconstruct a tangential
vector $\mathbf{u}_t$ at a cell center $\mathbf{x}_c$.

Following Peixoto and Barros (2014), the baseline method for the first
implementation should be linear least-squares reconstruction on all cells using
a Voronoi-centered two-ring stencil. This choice is motivated by the paper's
results for cell-centered and Voronoi-centered reconstruction:

- least-squares reconstruction with a two-ring stencil is second-order and far
  less sensitive to grid imprinting,
- it avoids cell-by-cell method switching and alignment-threshold tuning in the
  primary implementation, and
- because coefficients are generated offline in Python, setup cost is less
  important than a simple and uniform formulation.

The same paper also supports a hybrid Perot/least-squares method as an
effective optimization. That hybrid should be retained as a fallback option if
runtime application of the all-LSQ coefficients proves too expensive.

For MPAS cells, the reconstructed point is the cell center, interpreted as the
local reconstruction point. The implementation should use the local tangent
plane at the cell center, because the source data are tangent to the sphere and
the paper's spherical extensions are based on local projection to the tangent
plane.

For a cell with local tangent coordinates $\boldsymbol{\xi}$ centered at the
cell center:

1. Project nearby edge midpoints and edge-normal vectors into the tangent plane.
2. Apply least-squares reconstruction in that plane.
3. Map the reconstructed tangent vector back to 3D Cartesian coordinates.

In the least-squares approach, a linear tangential vector field is fit in
tangent coordinates:

$$
\mathbf{u}_t(\boldsymbol{\xi}) = \mathbf{a}_0 + A \boldsymbol{\xi},
$$

subject to the observed edge-normal constraints over a two-ring stencil. The
value at the cell center is then $\mathbf{a}_0$. As in the paper, the least
squares system should be solved in a weighted form to improve conditioning.

The least-squares stencil should be Voronoi-centered and use two levels of
neighbors. In MPAS connectivity terms, this should be interpreted as the union
of `edgesOnVertex` over the `verticesOnCell` of the target cell, with duplicate
edges removed. Equivalently, this is the set of edges incident on the vertices
of the target Voronoi cell, not the much larger set obtained from
`edgesOnCell` of `cellsOnCell`.

For a hexagon, each of the 6 vertices contributes one edge on the cell boundary
and one additional outer edge after duplicates are removed, giving 12 unique
edges. For a pentagon, the same construction gives 10 unique edges. This
matches the LS12 method described in the paper for cell-centered or
Voronoi-centered reconstruction.

If runtime benchmarks later show that the all-LSQ approach is too expensive, a
secondary implementation path can adopt the paper's hybrid strategy. In that
case, Perot's method would be applied on well-aligned cells and least-squares
would be retained on the remaining cells. The Perot formula is:

$$
\mathbf{u}_{t,c}^{P} \approx
\frac{1}{A_c}\sum_{e \in c} l_e \, \mathbf{r}_e \, u_e,
$$

where $A_c$ is the cell area in the local projected plane, $l_e$ is edge
length, and $\mathbf{r}_e$ is the projected vector from the reconstruction
point to the midpoint of edge $e$. If this optimization path is pursued, the
alignment-index criterion from Peixoto and Barros should be revisited as part
of the performance study rather than being fixed in the first implementation.

### Algorithm Design: 3D Vector Outputs at Layer Midpoints

Date last modified: 2026/04/06

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

The generic reconstruction produces only the tangential part of the vector. A
full 3D vector at layer midpoint $k$ should be constructed as:

$$
\mathbf{u}_{c,k} =
\mathbf{u}_{t,c,k} + w_{c,k} \hat{\mathbf{r}}_c,
$$

where $\hat{\mathbf{r}}_c$ is the local vertical unit vector at the cell center.

If a radial interface field is provided on `nVertLevelsP1`, the midpoint radial
component should be formed by averaging adjacent interface values:

$$
w_{c,k} = \frac{1}{2}\left(w^\mathrm{top}_{c,k} +
w^\mathrm{top}_{c,k+1}\right).
$$

This yields a 3D vector defined at cell centers and layer midpoints. For
velocity, this is the expected target location for reconstructed 3D velocity in
MPAS-O analysis workflows.

If no radial interface field is supplied, then:

$$
w_{c,k} = 0.
$$

The tangential reconstruction is first returned in 3D Cartesian components
$(u_x, u_y, u_z)$ even when the vector lies entirely in the tangent plane. If a
radial component is supplied, it is added in Cartesian form before any basis
change is applied.

The output should also be available in the local geographic basis as zonal,
meridional, and radial components. Using longitude $\lambda$ and latitude
$\theta$ at the cell center, these components should be computed by projecting
the Cartesian vector onto the local eastward, northward, and vertical
directions used in the MPAS framework:

$$
u_\mathrm{zonal} = -u_x \sin\lambda + u_y \cos\lambda,
$$

$$
u_\mathrm{meridional} =
-(u_x \cos\lambda + u_y \sin\lambda)\sin\theta + u_z \cos\theta.
$$

$$
u_\mathrm{radial} =
(u_x \cos\lambda + u_y \sin\lambda)\cos\theta + u_z \sin\theta.
$$

These formulas are appropriate both for tangential-only reconstruction and for
the full vector after radial composition. For a tangential-only reconstruction,
$u_\mathrm{radial}$ should be zero up to truncation error. When a radial
contribution is included, it should appear explicitly in
$u_\mathrm{radial}$.

### Algorithm Design: Reusable Precomputation and Extensibility

Date last modified: 2026/04/05

Contributors:

- Xylar Asay-Davis
- Codex

The reconstruction should be divided into a mesh-dependent
coefficient-generation step and a field-dependent reconstruction step that uses
those precomputed coefficients. The coefficient-generation step is the primary
deliverable for `polaris` because it produces the coefficients and stencil
metadata to be stored on the mesh. This step should be implemented in Python
and is intended to become the authoritative implementation for the new
reconstruction method. The reconstruction step is also useful in Python for
testing and analysis. Changes to MPAS-Ocean or Omega to read the stored fields
would be follow-on work, not part of this PR.

The coefficient-generation step should precompute, for each cell:

- the edge stencil,
- projected edge geometry in the local tangent plane,
- a weighted least-squares pseudo-inverse or equivalent coefficient matrix for
  the cell-center value.

The reconstruction step should then reduce to weighted sums over each cell's
local stencil. For a given edge-normal field and vertical level, the tangential
reconstruction at each cell should be a weighted sum over the local stencil.

This separation is important because:

- the mesh geometry does not change between time slices,
- the same reconstruction is often applied over many vertical levels, and
- later arbitrary-point reconstruction can reuse the same tangent-plane
  machinery, stencil construction, and basis transforms.

The initial design intentionally excludes arbitrary-point interpolation with
spherical Wachspress coordinates. However, the reconstruction cache should be
built so this can be added later by introducing a second stage that evaluates
the field at vertices or other fixed locations and then interpolates.

## Implementation

### Implementation: Generic Tangential Reconstruction at Cell Centers

Date last modified: 2026/04/06

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

The proposed implementation adds a new coefficient-generation module to
`polaris/mesh`:

- `polaris/mesh/reconstruct.py`

and a companion module for basis transforms and 3D composition:

- `polaris/mesh/vector.py`

The public API should be generic enough to support velocity and other
edge-normal quantities. A likely structure is:

```python
def build_reconstruction_cache(ds_mesh, method="lsq"):
    ...


def build_reconstruction_mesh_fields(cache):
    ...


def reconstruct_tangential_cell_center(edge_normal_field, ds_mesh,
                                       cache=None):
    ...


def cartesian_to_local_geographic(u_x, u_y, u_z, ds_mesh):
    ...


def reconstruct_3d_cell_center(edge_normal_field, ds_mesh,
                               radial_interface_field=None, cache=None):
    ...
```

`build_reconstruction_cache()` should:

- validate that the mesh is spherical,
- determine the local tangent basis and local vertical direction at each cell,
- build the local stencil and coefficient arrays, and
- return a compact collection of precomputed arrays, likely as an
  `xarray.Dataset` or a small dataclass containing `xarray.DataArray` members.

The default method should be all-cell least-squares. An optional `method`
argument may later support `hybrid`, but that should not be the baseline path.

`build_reconstruction_mesh_fields()` should convert that full in-memory cache
into the smaller set of MPAS mesh variables that belong in a mesh file. Keeping
these steps separate is useful because the cache may include projected
coordinates, basis vectors, and other helper arrays that are convenient in
Python but do not need to be written to the mesh.

`reconstruct_tangential_cell_center()` should accept any edge-normal field with
an `nEdges` dimension, preserving all non-horizontal dimensions. This makes the
core implementation usable for velocity, pressure-gradient-like fields, or any
other tangential vector quantity represented through edge-normal components. It
should return a 3-component Cartesian vector that is tangent to the sphere at
each cell center, so `cartesian_to_local_geographic()` can be applied directly
to its output.

`reconstruct_3d_cell_center()` should build on the tangential reconstruction by
adding an optional radial interface field and returning Cartesian and
local geographic components. This function should remain usable for velocity and
other edge-normal quantities.

For xarray compatibility, the Python reconstruction implementation should work
with extra dimensions and apply the precomputed weights only along `nEdges`.
This will make the same code work naturally for:

- `nEdges`,
- `nEdges, nVertLevels`,
- `Time, nEdges, nVertLevels`,

and similar combinations.

The least-squares path should avoid repeated dense solves when reconstructing a
field. Instead, the coefficient-generation step should precompute the matrix
that maps the stencil's edge-normal values directly to the reconstructed
Cartesian vector at the cell center.

Pseudo code for generating coeffs:

```python
for cell in cells:
    basis = build_local_tangent_basis(cell)
    stencil = build_two_ring_edge_stencil(cell)
    coeffs[cell] = build_lsq_center_coeffs(cell, stencil, basis)
```

Pseudo code for applying coeffs:

```python
for cell in cells:
    tangential_xyz[..., cell] = sum(
        coeffs[cell, i, :] * edge_normal[..., stencil[cell, i]]
        for i in range(n_stencil[cell])
    )
```

`polaris/mesh/__init__.py` should export the main public functions.

This design does not propose porting the new coefficient-generation
algorithm to Fortran for online execution in MPAS-Ocean, and it does not
propose computing these coefficients directly in Omega. Instead, the Python
implementation in `polaris` should generate the coefficients once for a given
mesh, after which runtime codes should only consume the stored mesh fields.
Follow-on PRs should update MPAS-Ocean and Omega to use those fields.

#### Mesh Fields Written by Polaris

This subsection defines the mesh fields that `polaris` will write. It includes
these details so the mesh-file interface is clear, but it does not propose
changes to MPAS-Ocean or Omega in this PR.

The mesh-storage design needs special attention. Existing MPAS meshes already
contain:

- `coeffs_reconstruct(R3, maxEdges, nCells)`,

and the current MPAS runtime reconstruction uses `edgesOnCell` as the implicit
stencil. This is sufficient for the existing one-ring reconstruction but not
for the all-cell least-squares design described here, which requires a two-ring
stencil with up to 12 edges on hexagons and 10 on pentagons.

Therefore, the least-squares design requires runtime-readable mesh fields
that explicitly encode both:

- the reconstruction stencil for each cell, and
- the coefficients associated with that stencil.

The recommended target representation is:

- `reconstructEdgeStencil(maxEdges2, nCells)`,
- `nReconstructEdges(nCells)`,
- `coeffs_reconstruct(R3, maxEdges2, nCells)`.

Here, `maxEdges2` is already an MPAS mesh dimension and is 12 on standard
hexagon-pentagon meshes, which matches the LS12 stencil width described in the
paper. This makes `maxEdges2` a natural candidate for storing the two-ring
least-squares stencil.

This design explicitly recommends enlarging `coeffs_reconstruct` from
`maxEdges` to `maxEdges2` rather than introducing a second coefficient
variable. This keeps the runtime interface clearer by preserving the existing
coefficient name while expanding its stencil capacity to support both the
current one-ring case and the new two-ring least-squares case.

### Implementation: 3D Vector Outputs at Layer Midpoints

Date last modified: 2026/04/06

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

`polaris/mesh/vector.py` should contain the generic 3D-composition logic that
sits on top of the tangential reconstruction and the coefficient-generation
workflow.

The generic 3D wrapper should:

1. reconstruct the tangential Cartesian vector from an edge-normal field,
2. broadcast the tangential result to all non-horizontal dimensions,
3. derive midpoint radial values from an optional radial interface field,
4. add the radial contribution in the local vertical direction, and
5. derive zonal, meridional, and radial components from the resulting Cartesian
   vector.

For the optional radial interface field, the implementation should:

- require an `nCells` dimension,
- require `nVertLevelsP1` if present,
- form midpoint values on `nVertLevels`,
- preserve any leading dimensions such as `Time`.

If the radial interface field is omitted, the wrapper should behave exactly
like a horizontal-only reconstruction, with zero radial contribution.

The generic wrapper should return an `xarray.Dataset` with clearly named output
fields. A likely default is:

- `vectorX`,
- `vectorY`,
- `vectorZ`,
- `vectorZonal`,
- `vectorMeridional`,
- `vectorRadial`.

If later work wants velocity-oriented names, the design should also note how
this generic output could map onto fields such as:

- `uReconstructX`,
- `uReconstructY`,
- `uReconstructZ`,
- `uReconstructZonal`,
- `uReconstructMeridional`,
- `uReconstructRadial`.

The core implementation should remain usable for velocity and for other
edge-normal quantities even if some later workflow maps the outputs onto
velocity-specific names. Choosing and implementing those downstream names is out
of scope for this PR.

### Implementation: Reusable Precomputation and Extensibility

Date last modified: 2026/04/05

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

The reconstruction cache should be serializable or at least representable as an
`xarray.Dataset`, so it can be inspected during debugging and written to a mesh
file.

Recommended cache contents include:

- `nStencilEdges` on `nCells`,
- `stencilEdges` on `nCells, maxStencilEdges`,
- `reconstructCoeffs` on `nCells, maxStencilEdges, R3`,
- local basis vectors on `nCells, R3`.

This design intentionally precomputes coefficients for cell-center values only.
That keeps the initial implementation compact and directly aligned with the user
need. A later arbitrary-point design can either:

- add a second cache for fixed target points such as vertices, or
- add target-specific coefficient builders that reuse the same tangent-plane and
  stencil code.

The Polaris work described here can proceed in four steps:

1. implement the offline least-squares coefficient and stencil generator in
   `polaris`,
2. define the mesh-field representation written by `polaris` and write those
   fields to mesh files,
3. implement basis transforms and the Python 3D reconstruction wrapper with an
   optional radial interface field,
4. document the API and add examples for coefficient generation and
   reconstruction from stored coefficients.

Any MPAS-Ocean or Omega code changes to read the new mesh fields would be
separate follow-on work after this Polaris design and implementation are in
place.

If performance studies later indicate that runtime application is too costly, a
follow-on effort can evaluate the hybrid Perot/least-squares optimization.

## Testing

### Testing and Validation: Generic Tangential Reconstruction at Cell Centers

Date last modified: 2026/04/05

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

Testing should include unit tests and convergence tests.

Unit tests should verify:

- constant tangential vector fields reconstruct with small error,
- the reconstructed vector is tangent to the sphere when no radial component is
  supplied,
- mesh-output fields contain the expected stencil width and coefficient layout.

Convergence tests should use analytic spherical flows already available in
Polaris test cases, such as the sphere transport or cosine-bell style flows.
The test procedure should:

1. evaluate analytic zonal/meridional velocity on edges,
2. convert to edge-normal components,
3. reconstruct at cell centers,
4. compare with the analytic vector at cell centers.

The expected result is second-order convergence in RMS error for the
least-squares scheme on spherical MPAS meshes, with substantially reduced grid
imprinting relative to Perot alone.

For the coefficient-generation path, tests should also confirm that applying the
stored mesh coefficients reproduces the same result as the direct Python
reconstruction.

At least one test case should use a culled ocean mesh to confirm that stencil
construction and reconstruction behave sensibly near topography and other
non-global boundaries.

Performance tests should compare:

- coefficient-generation cost in Python for representative mesh sizes,
- runtime application cost of the stored least-squares coefficients,
- mesh storage footprint for the widened stencil representation.

If these tests show that runtime cost is too high, they should motivate
evaluation of the hybrid optimization path.

### Testing and Validation: 3D Vector Outputs at Layer Midpoints

Date last modified: 2026/04/06

Contributors:

- Xylar Asay-Davis
- Carolyn Begeman
- Codex

3D-vector tests should verify:

- Cartesian and local geographic outputs are mutually consistent,
- omission of the radial interface field yields zero radial contribution,
- midpoint radial velocity is computed correctly from interface values,
- the reconstructed local geographic radial component equals the simple mean of
  the adjacent top and bottom interface values,
- a case with nonzero radial contribution is reconstructed correctly in
  Cartesian form, and
- the local geographic radial output matches the expected midpoint radial
  velocity, and
- the zonal and meridional outputs remain consistent with the horizontal part
  of the reconstructed vector,
- shape and dimension handling are correct for `nVertLevels`,
  `nVertLevelsP1`, and optional `Time`.

A simple analytic test can define:

- a known tangential horizontal velocity,
- a known radial profile on interfaces,
- an expected full Cartesian vector at layer midpoints.

The generic wrapper should reproduce the known Cartesian and zonal/meridional
fields, together with the expected radial field, to within expected truncation
error. A velocity-specific test case using `normalVelocity` and
`vertVelocityTop` should remain part of the test suite as the motivating
example.

### Testing and Validation: Reusable Precomputation and Extensibility

Date last modified: 2026/04/05

Contributors:

- Xylar Asay-Davis
- Codex

For the primary workflow, tests should also verify that mesh-writing preserves
the coefficient fields exactly and that applying those stored fields gives
identical answers before and after I/O.

Tests in this section should also verify that converting the in-memory cache to
mesh fields preserves the coefficients needed for reconstruction, and that
applying those stored fields reproduces the same result as applying the
in-memory cache directly.

Documentation tests or example scripts should also be added to demonstrate:

- generic tangential reconstruction from an arbitrary edge-normal field,
- velocity reconstruction from `normalVelocity`,
- velocity reconstruction from `normalVelocity` and `vertVelocityTop`.

The initial implementation does not need regression-suite integration beyond
unit and convergence tests, but if the functionality becomes part of standard
analysis or initialization workflows, a lightweight analysis regression test
should be added later to guard against changes in reconstruction coefficients or
basis transforms.

## References

Peixoto, P. S., and S. R. M. Barros (2014), On vector field reconstructions for
semi-Lagrangian transport methods on geodesic staggered grids, *Journal of
Computational Physics*, 273, 185-211, DOI:[10.1016/j.jcp.2014.04.043](https://doi.org/10.1016/j.jcp.2014.04.043).
