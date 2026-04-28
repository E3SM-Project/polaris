(users-mesh-coastline)=

# Coastline preparation tasks

The `mesh/spherical/unified/coastline` tasks build coastline masks and
signed-distance fields from the shared combined-topography products on
latitude-longitude grids. These tasks are intended for inspecting and caching
coastline products that later unified-mesh workflows can reuse.

Current coastline products are derived only from the combined topography
fields produced by `e3sm/init/topo/combine`. Alternate coastline sources such
as Natural Earth are not implemented yet.

## Available tasks

Polaris currently provides one standalone coastline task for each supported
latitude-longitude target grid:

- `mesh/spherical/unified/coastline/lat_lon/0.25000_degree/task`
- `mesh/spherical/unified/coastline/lat_lon/0.12500_degree/task`
- `mesh/spherical/unified/coastline/lat_lon/0.06250_degree/task`
- `mesh/spherical/unified/coastline/lat_lon/0.03125_degree/task`

Current testing suggests `0.25000_degree` is still useful for lower-cost
inspection but is too coarse for scientifically valid coastline products.
Prefer `0.12500_degree`, `0.06250_degree`, or `0.03125_degree` when coastline
fidelity matters.

Each task includes:

- a shared `combine_topo` step from `e3sm/init/topo/combine` that creates
  `topography.nc` on the selected target grid;
- a shared `prepare` step that writes one coastline NetCDF file for each
  supported coastline convention; and
- a shared `viz` step that writes diagnostic PNG images and a text summary.

## Coastline conventions

Each run writes three convention-specific NetCDF files:

- `coastline_calving_front.nc`
- `coastline_grounding_line.nc`
- `coastline_bedrock_zero.nc`

These correspond to three ways of handling Antarctic floating and grounded
ice when defining the ocean mask:

- `calving_front`: cells below sea level are ocean only where `ice_mask`
  indicates they are ice free;
- `grounding_line`: cells below sea level are ocean where `grounded_mask`
  indicates they are not grounded ice; and
- `bedrock_zero`: all cells below sea level are candidate ocean.

## How the coastline is derived

For each convention, Polaris builds the coastline fields in four stages:

1. It classifies each raster cell as candidate ocean or not candidate ocean
   using `base_elevation`, `ice_mask`, and `grounded_mask`.
2. It keeps only the connected ocean by labeling four-neighbor connected
   components on the latitude-longitude grid, merging components that meet
   across the antimeridian, and retaining only components that touch the
   northernmost latitude row.
3. It marks coastline transitions on east and north cell edges wherever the
   final ocean mask changes from ocean to land.
4. It computes signed distance to the nearest raster coastline sample from
   those edge transitions.

The flood-fill step is what removes disconnected inland basins. A cell can be
below sea level and still be classified as land if it belongs to a component
that never connects to the northern boundary of the grid through candidate
ocean cells.

The raster flood fill uses four-neighbor connectivity rather than diagonal
connectivity. North-south and east-west neighbors count as connected, but
cells that touch only at a corner do not. Longitudinal periodicity is handled
explicitly, so ocean that crosses the antimeridian remains connected.

The signed-distance calculation is also raster-based. Polaris places sample
points at the midpoints of coastline edges, converts both those samples and
all grid-cell centers from longitude/latitude to Cartesian coordinates on the
sphere, and builds a `scipy.spatial.cKDTree` from the coastline samples. The
nearest-neighbor search is performed in latitude chunks controlled by
`distance_chunk_size`, then the Cartesian chord distance is converted to a
spherical arc distance in meters. The result is positive in ocean cells and
negative in land cells.

Because the distance is measured to raster coastline samples rather than to an
exact vector shoreline, the answer is tied to the chosen latitude-longitude
resolution. Finer grids produce a more detailed coastline and a more accurate
approximation to the continuous shoreline.

## Output fields

For each convention, the coastline file contains:

- `ocean_mask`
- `signed_distance`

These fields have the following interpretation:

- `ocean_mask`: candidate ocean cells that remain after the flood fill;
- `signed_distance`: signed nearest-coastline distance in meters, negative
  over land and positive over ocean.

## Configuration

Each task links a shared config file named `coastline.cfg`. The main options
are:

- `[coastline].resolution_latlon`: the target latitude-longitude
  resolution in degrees. The task sets this automatically from the selected
  task path.
- `[coastline].include_critical_transects`: whether to apply the
  shared `geometric_features` critical land blockages and critical passages
  before flood filling. The default is `True`.
- `[coastline].mask_threshold`: threshold for converting remapped
  `ice_mask` and `grounded_mask` fields to binary masks. The default is
  `0.5`.
- `[coastline].sea_level_elevation`: elevation threshold for
  identifying below-sea-level cells. The default is `0.0` m.
- `[coastline].distance_chunk_size`: number of latitude rows
  processed at a time when computing signed distance. This changes memory use
  and query batching, not the definition of the distance. The default is
  `64`.
- `[viz_coastline].antarctic_max_latitude`: northern extent of
  Antarctic stereographic plots. The default is `-45.0` degrees.
- `[viz_coastline].dpi`: output resolution for diagnostic plots. The
  default is `200`.
- `[viz_coastline].signed_distance_limit`: symmetric colorbar limit
  for signed-distance plots. The default is `500000.0` m.

## Diagnostics

The visualization step writes global and Antarctic binary plots of the final
`ocean_mask` for each convention, along with matching signed-distance plots.
This keeps the visualization focused on the downstream-relevant land/ocean
classification and coastal-distance product while avoiding the slower
debug-only plots at high target-grid resolutions.

When critical transects are enabled, the flood fill honors the same shared
critical land blockages and critical passages from `geometric_features` that
are used in E3SM topography culling. This changes connectivity in the final
`ocean_mask` and derived `signed_distance` field without changing the output
schema.

The file `debug_summary.txt` records convention-specific counts such as the
number of ocean and land cells, along with the minimum and maximum signed
distance.

## Running a task

You can set up one of the coastline tasks with standard polaris commands, for
example:

```bash
polaris setup -t mesh/spherical/unified/coastline/lat_lon/0.12500_degree/task \
    -w coastline_0125
```

After setup, the work directory contains symlinks to the shared `combine_topo`,
`prepare`, and `viz` steps, along with the shared `coastline.cfg` file.