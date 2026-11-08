(dev-planar-meshes)=

# Planar Meshes

So far, there is not support for creating planar meshes in the polaris
framework.  But there are helpful functions for creating both
[uniform hexagonal meshes](https://mpas-dev.github.io/MPAS-Tools/stable/mesh_creation.html#uniform-planar-meshes)
and [more general planar meshes](https://mpas-dev.github.io/MPAS-Tools/stable/mesh_creation.html#planar-meshes)
using the [mpas_tools](https://mpas-dev.github.io/MPAS-Tools/stable/index.html)
package.

## Uniform planar meshes

You can build a uniform planar mesh in a step by calling
{py:func}`mpas_tools.planar_hex.make_planar_hex_mesh()`.  The mesh is defined
by the number of cells in the x and y directions (`nx` and `ny`), the
resolution `dc` in km (`dc` is the distance between adjacent cell centers),
and some (admittedly oddly named) parameters for determining which directions
(if any) are periodic, `nonperiodic_x` and `nonperiodic_y`.

There are a few considerations for determining `nx` and `ny`. There is a
framework level function {py:func}`polaris.mesh.planar.compute_planar_hex_nx_ny()`
to take care of this for you:

```python
from polaris.mesh.planar import compute_planar_hex_nx_ny


nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
```

What follows is an explanation of the subtleties that are accounted for in that
function. Typically, we need at least 4 grid cells in each direction for
MPAS-Ocean to be well behaved, and similar restrictions may apply to other
components.  Second, `ny` needs to be an even number because of the staggering
of the hexagons used to create the mesh.  (We typically also use even numbers
for `nx` but that is not strictly necessary.)

Another important consideration is that the physical size of the mesh in the x
direction is `lx = nx * dc`.  However, the physical extent in the y direction
is `ly = (np.sqrt(3) / 2) * ny * dc` because of the staggering of the hexagons
in that direction.  As a result, if you know the desired domain size `ly`,
you need to compute the number of cells in that direction including an extra
factor of `2. / np.sqrt(3)`, as in this example:
```python
import numpy as np
from mpas_tools.planar_hex import make_planar_hex_mesh

lx = 500e3
ly = 160e3
dc = 1e3

nx = max(2 * int(0.5 * lx / dc + 0.5), 4)
# factor of 2/sqrt(3) because of hexagonal mesh
ny = max(2 * int(0.5 * ly * (2. / np.sqrt(3)) / dc + 0.5), 4)

ds_mesh = make_planar_hex_mesh(nx=nx, ny=ny, dc=dc, nonperiodic_x=False,
                               nonperiodic_y=True)
```

## General planar meshes

One way to create a more general planar mesh is by calling
{py:func}`mpas_tools.mesh.creation.build_mesh.build_planar_mesh()`, which uses
JIGSAW to build a mesh with variable resolution.  See
[Planar Meshes](https://mpas-dev.github.io/MPAS-Tools/stable/mesh_creation.html#planar-meshes)
for more details.  We plan to create framework-level steps for planar meshes
similar to {py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` and
{py:class}`polaris.mesh.IcosahedralMeshStep` in the not too distant future.
