(dev-mesh)=

# Mesh

(dev-spherical-meshes)=

## Spherical Meshes

Test cases that use global, spherical meshes can add either
{py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` or
{py:class}`polaris.mesh.IcosahedralMeshStep` in order to creating a base mesh,
using [JIGSAW](https://github.com/dengwirda/jigsaw).  Alternatively, they can
use {py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` as the base class
for creating a more complex mesh by overriding the
{py:meth}`polaris.mesh.QuasiUniformSphericalMeshStep.build_cell_width_lat_lon()`
method.

A developer can also customize the options data structure passed on to JIGSAW
either by modifying the `opts` attribute of either of these classes or by
overriding the {py:meth}`polaris.mesh.IcosahedralMeshStep.make_jigsaw_mesh()`
or {py:meth}`polaris.mesh.QuasiUniformSphericalMeshStep.make_jigsaw_mesh()`
methods.

Icosahedral meshes will be significantly more uniform and smooth in cell size
than quasi-uniform spherical meshes.  On the other hand, icosahedral meshes are
restricted to resolutions that are an integer number of subdivisions of an
icosahedron.  The following table shows the approximate resolution of a mesh
with a given number of subdivisions:

| subdivisions | cell width (km) |
| ------------ | --------------- |
| 5            | 240             |
| 6            | 120             |
| 7            | 60              |
| 8            | 30              |
| 9            | 15              |
| 10           | 7.5             |
| 11           | 3.8             |
| 12           | 1.9             |
| 13           | 0.94            |

The following config options are associated with spherical meshes:

```cfg
# config options related to spherical meshes
[spherical_mesh]

# for icosahedral meshes, whether to use cell_width to determine the number of
# subdivisions or to use subdivisions directly
icosahedral_method = cell_width

# output file names
jigsaw_mesh_filename = mesh.msh
jigsaw_geom_filename = geom.msh
jigsaw_jcfg_filename = opts.jig
jigsaw_hfun_filename = spac.msh
triangles_filename = mesh_triangles.nc
mpas_mesh_filename = base_mesh.nc

# options related to writing out and plotting cell widths
plot_cell_width = True
cell_width_filename = cellWidthVsLatLon.nc
cell_width_image_filename = cellWidthGlobal.png
cell_width_colormap = '3Wbgy5'

# whether to add the mesh density to the file
add_mesh_density = False

# convert the mesh to vtk format for visualization
convert_to_vtk = True

# the subdirectory for the vtk output
vtk_dir = base_mesh_vtk

# whether to extract the vtk output in lat/lon space, rather than on the sphere
vtk_lat_lon = False
```
