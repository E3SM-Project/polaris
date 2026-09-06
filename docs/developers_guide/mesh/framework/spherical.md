(dev-spherical-meshes)=

# Spherical Meshes

The spherical meshes that have broad support accross tasks can be created with
the shared helper function
{py:func}`polaris.mesh.base.add_spherical_base_mesh_step()`.  Each mesh is
defined by a prefix (see the table below) and a `min_res` as well as an
optional `max_res` (both in km).  These meshes are all created with the
[JIGSAW](https://github.com/dengwirda/jigsaw) and
[JIGSAW-Python](https://github.com/dengwirda/jigsaw-python) tools.

```python
from polaris.mesh.base import add_spherical_base_mesh_step

mesh_step = add_spherical_base_mesh_step(
    prefix='qu',
    min_res=120.0,
)
```

```python
from polaris.mesh.base import add_spherical_base_mesh_step

mesh_step = add_spherical_base_mesh_step(
    prefix='so',
    min_res=12.0,
    max_res=30.0,
)
```

| prefix | mesh description                                     |
|--------|------------------------------------------------------|
| qu     | quasi-uniform resolution                             |
| icos   | dual mesh of a subdivided icosahedron                |
| rrs    | resolution approximately scaled by the Rossby radius |
| so     | resoluiton enhanced in the Southern Ocean            |

To define a new shared mesh or for more specialized meshes, can instantiate
{py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` or
{py:class}`polaris.mesh.IcosahedralMeshStep` directly when you need more
control. For more complex meshes, use
{py:class}`polaris.mesh.QuasiUniformSphericalMeshStep` as a base class and
override
{py:meth}`polaris.mesh.QuasiUniformSphericalMeshStep.build_cell_width_lat_lon()`.

A developer can also customize the options data structure passed on to JIGSAW
either by modifying the `opts` attribute of either of these classes or by
overriding the {py:meth}`polaris.mesh.IcosahedralMeshStep.make_jigsaw_mesh()`
or {py:meth}`polaris.mesh.QuasiUniformSphericalMeshStep.make_jigsaw_mesh()`
methods.

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
reconstruction_weights_filename = reconstruction_weights.nc

# JIGSAW mesh-optimization settings
jigsaw_optm_kern = odt+dqdx
jigsaw_optm_iter = 16
jigsaw_optm_qtol = 1.0e-4
jigsaw_optm_qlim = 0.9375

# whether to compute vector-reconstruction weights and stencils at cell
# centers for the base mesh
generate_reconstruction_weights = True

# options related to mesh name and resolution
# the prefix (e.g. Icos, QU, SO, RRS)
prefix = PREFIX
# the minimum (finest) resolution in the mesh
min_cell_width = <<<missing>>>
# the maximum (coarsest) resolution in the mesh, can be the same as
# min_cell_width
max_cell_width = <<<missing>>>

# Antarctic land-ice ownership convention shared by spherical mesh workflows
# and downstream topography-based culling
antarctic_boundary_convention = calving_front


# options related to writing out and plotting cell widths
plot_cell_width = True
cell_width_filename = cellWidthVsLatLon.nc
cell_width_image_filename = cellWidthGlobal.png
cell_width_colormap = 3Wbgy5

# whether to add the mesh density to the file
add_mesh_density = False

# convert the mesh to vtk format for visualization
convert_to_vtk = False

# the subdirectory for the vtk output
vtk_dir = base_mesh_vtk

# whether to extract the vtk output in lat/lon space, rather than on the sphere
vtk_lat_lon = False


# config options related to spherical mesh quality checks
[spherical_mesh_quality]

# whether to check MPAS cell polygons for geometry that can trip remapping
check_cell_geometry = True

# minimum edge length as a fraction of the median edge length in the cell
minimum_edge_length_ratio = 1.0e-5

# minimum sine of each cell corner angle.  Small values indicate nearly
# collinear or spiked consecutive vertices.
minimum_corner_sine = 1.0e-3

# maximum number of failing cells to include in the error message
max_bad_cells_to_report = 1
```

## JIGSAW mesh optimization

`jigsaw_optm_kern`, `jigsaw_optm_iter`, `jigsaw_optm_qtol` and
`jigsaw_optm_qlim` are passed through to JIGSAW by
{py:class}`polaris.mesh.QuasiUniformSphericalMeshStep`. The defaults are
the values the step used before they were configurable, which are also what
`mpas_tools` passes, so a mesh that does not set them is unaffected.
({py:class}`polaris.mesh.IcosahedralMeshStep` keeps its own settings and
does not read these.)

`jigsaw_optm_kern` chooses between an Optimal Delaunay Tessellation
(`odt+dqdx`) and a Centroidal Voronoi Tessellation (`cvt+dqdx`). MPAS cells
are the Voronoi dual of the JIGSAW triangulation, so `cvt+dqdx` optimizes
the cells that carry `dcEdge` rather than the triangulation, and it does
give a tighter *bulk* `dcEdge` distribution at roughly 1.8 times the
mesh-build time.

It is not currently used by any mesh, and it should not be selected without
reading the {ref}`design doc <design-docs>` `unified_mesh_dc_edge_noise`
first. On real unified meshes it thinned the bulk about fourfold while
introducing rare severe defects: the minimum `dcEdge` ratio on
`u.oi6to18.lr6to10` fell from 0.643 to 0.515, and `u.oi30.lr10` failed the
cell-polygon quality check outright. Because the cull diagnostic reports a
*minimum* over millions of edges, a kernel that improves the bulk and
worsens the tail is a net loss.

## Reconstruction weights

{py:class}`polaris.mesh.spherical.SphericalBaseStep` can add cell-centered
vector-reconstruction weights and stencils to the base mesh, written to
`reconstruction_weights_filename`.  See {ref}`dev-mesh-reconstruct` for what
those fields are and how to use them.

`generate_reconstruction_weights` controls whether they are computed.  They
are needed by Omega but not by MPAS-Ocean, and a mesh that gets culled
afterward -- a unified mesh, for instance -- should turn them off, since
culling renumbers cells and the weights have to be recomputed on the culled
mesh anyway.

## Cell-polygon quality checks

After the MPAS mesh is written, `SphericalBaseStep` checks its cell polygons
for geometry that would trip remapping later on, using
{py:func}`polaris.mesh.spherical.quality.check_cell_polygon_quality()`.  The
`[spherical_mesh_quality]` options above tune the check: `check_cell_geometry`
turns it off, `minimum_edge_length_ratio` and `minimum_corner_sine` set the
thresholds for degenerate edges and spiked corners, and
`max_bad_cells_to_report` limits how many failing cells the error message
names.

The default thresholds have several orders of magnitude of margin against
genuine degeneracy while still passing meshes built with river-network line
constraints, which pin vertices well below the target cell size wherever
those lines run.  See the comments in `polaris/mesh/spherical/spherical.cfg`
for the measurements the defaults are based on.

## Supported Base Mesh Steps

Many polaris tasks and steps are generated only for a set of predetermined,
supported base meshes and resolutions.  Those meshes are defined by
{py:data}`polaris.mesh.base.BASE_MESH_DEFINITIONS`, which maps each mesh name
to a {py:class}`polaris.mesh.base.BaseMeshDefinition` giving its prefix and
resolutions.  {py:func}`polaris.mesh.base.get_base_mesh_steps()` turns those
definitions into steps,
{py:func}`polaris.mesh.base.get_base_mesh_definition()` looks up a single one
by name, and {py:func}`polaris.mesh.base.get_base_mesh_step_names()` lists the
names.

Currently, the following meshes and resolutions are defined:

Uniform:
* Icos480km
* Icos240km
* Icos120km
* Icos60km
* Icos30km

* QU480km
* QU240km
* QU210km
* QU180km
* QU150km
* QU120km
* QU90km
* QU60km
* QU30km

Variable:
* SO12to30km
* RRS6to18km

If you wish to add a new resolution (in km), edit the list of either uniform
or variable resolutions in `_get_base_mesh_definitions()` in
`polaris/mesh/base/__init__.py`:

```python
    uniform_res = {
        'icos': [480.0, 240.0, 120.0, 60.0, 30.0],
        'qu': [480.0, 240.0, 210.0, 180.0, 150.0, 120.0, 90.0, 60.0, 30.0],
    }

    variable_res = {
        'so': [(12.0, 30.0)],
        'rrs': [(6.0, 18.0)],
    }
```

Each variable resolution mesh has a tuple of the finest and coarsest
resolution.

To add a new type of base mesh, you first need to add its base class to
`MESH_CLASSES` and `MESH_NAME_PREFIXES` in `polaris/mesh/base/add.py`:

```python
MESH_CLASSES = {
    'icos': IcosahedralMeshStep,
    'qu': QuasiUniformSphericalMeshStep,
    'rrs': RRSBaseMesh,
    'so': SOBaseMesh,
}

MESH_NAME_PREFIXES = {
    'icos': 'Icos',
    'qu': 'QU',
    'rrs': 'RRS',
    'so': 'SO',
}
```

Then, you can add the prefix and its associated resolutions to
`_get_base_mesh_definitions()` as above.

By adding new mesh prefixes and/or resolutions to that function,
a version of each task that builds on base meshes (such as those for remapping
topography and culling out land or ocean) will be added to the list of tasks
when you run `polaris list`.

## Approximately Uniform Spherical Meshes

Icosahedral meshes will be significantly more uniform and smooth in cell size
than quasi-uniform spherical meshes.  On the other hand, icosahedral meshes are
restricted to resolutions that are an integer number of subdivisions of an
icosahedron.  The following table shows the approximate resolution of a mesh
with a given number of subdivisions:

| subdivisions | cell width (km) |
|--------------|-----------------|
| 5            | 240             |
| 6            | 120             |
| 7            | 60              |
| 8            | 30              |
| 9            | 15              |
| 10           | 7.5             |
| 11           | 3.8             |
| 12           | 1.9             |
| 13           | 0.94            |

## Rossby-radius Scaled (RRS) Meshes

The RRS meshes are defined by {py:class}`polaris.mesh.base.rrs.RRSBaseMesh` and
have a resolution that ranges from finest at the poles to coarsests at the
equator, scaling approximately with the Rossby radius.  The scaling is:

```{math}
w(\phi) =
\frac{r_{\min}}{\Big[\,\gamma + (1-\gamma)\,\sin^{4}(|\phi|)\,\Big]^{1/4}},\quad
\gamma = \left(\frac{r_{\min}}{r_{\max}}\right)^{4}.
```

Where $\phi$ is the latitude in radians and $r_{\min}$ and $r_{\max}$ are the
finest and coarsest resolutions, respectively.

```{image} images/rrs.png
:align: center
:width: 500 px
```

## Southern Ocean (SO) Meshes

The SO meshes are defined by {py:class}`polaris.mesh.base.so.SOBaseMesh` and
have a quasi-uniform, coarse background resolution that transitions to a
higher resolution region surrounding the Southern Ocean.  The high resolution
region is defined by a geojson shape that attempts to approximatly follow
dynamical ocean contours since rapid changes in resolution have been shown to
steer ocean currents along isocontours of resolution.

```{image} images/so.png
:align: center
:width: 500 px
```
