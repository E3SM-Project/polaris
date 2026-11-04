(dev-e3sm-init-framework)=

# Framework

The `e3sm/init` component includes a small amount of shared framework code.
`polaris.e3sm.init.topo` defines supported source-topography resolutions and
helper functions used by `e3sm/init` tasks and by other components that need
the same resolution logic. `polaris.e3sm.init.glc_ocean_maps` makes the maps
between a land-ice mesh and an ocean mesh that E3SM's coupler reads.

## Supported Resolutions

The supported cubed-sphere resolutions are collected in
`CUBED_SPHERE_RESOLUTIONS`:

- `3000`, the standard high-resolution source-topography product
- `120`, the lower-cost source-topography product for coarse workflows

The supported latitude-longitude resolutions are collected in
`LAT_LON_RESOLUTIONS`:

- `1.0`
- `0.25`
- `0.125`
- `0.0625`
- `0.03125`

## Resolution Naming

The helper `format_lat_lon_resolution_name()` converts a latitude-longitude
resolution in degrees into the directory naming convention used throughout
Polaris. It formats the resolution with
`LAT_LON_RESOLUTION_DECIMALS = 5` decimal places and appends `_degree`.

Examples:

- `1.0` becomes `1.00000_degree`
- `0.125` becomes `0.12500_degree`
- `0.03125` becomes `0.03125_degree`

## Cubed-Sphere Resolution Selection

The helper `get_cubed_sphere_resolution(low_res)` returns either
`STANDARD_CUBED_SPHERE_RESOLUTION` or
`LOW_RES_CUBED_SPHERE_RESOLUTION`.

The helper `uses_low_res_cubed_sphere(cell_width)` encapsulates the current
selection rule for MPAS base meshes. It returns `True` when `cell_width` is
at least `LOW_RES_BASE_MESH_CELL_WIDTH`, currently `120.0` km.

This separation keeps shared resolution logic in the component framework
rather than in `polaris.tasks.e3sm.init`, which allows mesh and ocean
workflows to reuse the same supported-resolution definitions.

## Maps Between Land Ice and the Ocean

{py:class}`polaris.e3sm.init.glc_ocean_maps.GlcOceanMapStep` makes a
conservative map between a land-ice (glc) mesh and an ocean mesh, in either
direction. The caller adds the step's input files, `glc_scrip.nc` and
`ocn_scrip.nc`, and sets the mesh names, which give the map a unique name,
either when the step is created or before its `runtime_setup()` runs.

A map from the land ice to the ocean can be smoothed with `smoothed=True`.
Each ocean cell is then inflated by `expand_distance` meters outward from its
center before the cells are overlapped, so each land-ice cell is spread over
the ocean cells within about that distance. pyremap inflates only the cells of
a mesh, so a smoothed map reads the ocean's MPAS mesh from `ocn_mesh.nc`
instead of its SCRIP file. A smoothed map can smooth the land-ice geometry the
ocean sees, both in its initial condition and through the coupler, while the
fluxes use the unsmoothed conservative map.
