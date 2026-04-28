(users-mesh-river-network)=

# River-network preparation tasks

The unified-mesh river-network tasks simplify HydroRIVERS source data,
reconcile retained outlets with the selected coastline product, and build
target-grid masks that downstream sizing-field and base-mesh workflows can
consume directly.

The standalone tasks expose two layers of the workflow:

- a source-level task for inspecting HydroRIVERS conversion, outlet
  retention, and basin-aware simplification; and
- a latitude-longitude task for inspecting coastline-aware outlet snapping,
  target-grid masks, and diagnostic plots.

The downstream base-mesh workflow reuses these same shared steps and then
produces coastline-clipped river products for final mesh generation.

## Available tasks

Polaris registers two standalone river tasks for each named unified mesh:

- `mesh/spherical/unified/<mesh_name>/river/source/task`
- `mesh/spherical/unified/<mesh_name>/river/lat_lon/task`

Supported `mesh_name` values are:

- `ocn_240km_lnd_240km_riv_240km`
- `ocn_30km_lnd_10km_riv_10km`
- `ocn_rrs_6to18km_lnd_12km_riv_6km`
- `ocn_so_12to30km_lnd_10km_riv_10km`

Each source task contains the shared `prepare` step that downloads and
simplifies HydroRIVERS.

Each lat-lon task contains:

- `prepare_source`, the same shared source-level river step;
- `combine_topo`, the shared `e3sm/init/topo/combine` step for the mesh's
  target latitude-longitude grid;
- `prepare_coastline`, the shared coastline step for the selected target
  grid and coastline convention;
- `viz_prepare_coastline`, an optional coastline diagnostic step that is not
  run by default;
- `prepare`, the shared lat-lon river step that writes raster and outlet
  products; and
- `viz_river_network`, a diagnostic step that writes an overview plot and
  summary text file.

## How the river network is derived

The source-level workflow follows a staged simplification strategy:

1. It downloads the HydroRIVERS archive and converts the shapefile into
   `source_river_network.geojson`.
2. It canonicalizes source features into one segment per `hyriv_id` when the
   source contains multiple geometries for the same river segment.
3. It filters segments by `drainage_area_threshold`.
4. It validates that the retained `next_down` graph is acyclic.
5. It identifies outlet candidates from segments with `next_down == 0`, then
   keeps large, well-separated ocean outlets while retaining explicit inland
   sinks.
6. It traverses upstream from each retained outlet to keep main stems and
   significant tributaries, preserving basin connectivity and confluence
   structure.

The lat-lon workflow then turns the simplified network into target-grid
products:

1. It samples the retained river lines densely enough to rasterize them onto
   the chosen latitude-longitude grid.
2. It snaps ocean outlets to nearby ocean cells from `coastline.nc` when a
   match is available within `outlet_match_tolerance`.
3. It snaps inland sinks to the nearest land cell derived from the coastline
   `ocean_mask`.
4. It writes separate masks for channels, all outlets, ocean outlets, and
   inland sinks instead of overloading one raster with mixed semantics.

If an ocean outlet cannot be matched to ocean within tolerance, it is still
snapped to the nearest grid cell, but its `matched_to_ocean` flag remains
`false` and the snapping distance is recorded for diagnostics.

## Outputs

The source task writes:

- `source_river_network.geojson`, the direct conversion of the HydroRIVERS
  shapefile;
- `simplified_river_network.geojson`, the retained river segments and their
  basin and outlet metadata; and
- `retained_outlets.geojson`, one feature per retained ocean outlet or inland
  sink.

The lat-lon task writes:

- `river_network.nc`, containing `river_channel_mask`, `river_outlet_mask`,
  `river_ocean_outlet_mask`, and `river_inland_sink_mask`;
- `river_outlets.geojson`, containing source and snapped outlet coordinates,
  snapped grid indices, snapping distance, and `matched_to_ocean`; and
- `river_network_overview.png` and `debug_summary.txt` from the visualization
  step.

The downstream shared base-mesh river step also writes:

- `clipped_river_network.geojson`;
- `clipped_outlets.geojson`;
- and `clipped_river_network.nc`.

These clipped products are intended for the unified base-mesh workflow rather
than the standalone inspection tasks.

## Configuration

Each task links the shared `river_network.cfg` file and inherits the selected
mesh's `unified_mesh` settings, including the target-grid resolution and
coastline convention.

The `[river_network]` section controls HydroRIVERS access and source-level
simplification:

- `hydrorivers_url`: the public HydroRIVERS archive URL.
- `hydrorivers_archive_filename`: local filename used for the downloaded
  archive.
- `hydrorivers_shp_directory`: expected directory name after unpacking the
  archive.
- `hydrorivers_shp_filename`: HydroRIVERS shapefile basename inside the
  unpacked archive.
- `drainage_area_threshold`: minimum drainage area in square meters for
  retaining a source segment.
- `outlet_distance_tolerance`: minimum spacing in meters between retained
  non-endorheic outlets.
- `tributary_area_ratio`: minimum tributary-to-main-stem drainage-area ratio
  for retaining a nearby tributary.
- `base_mesh_clip_distance_km`: inland clip distance used later when
  preparing base-mesh river products.
- `base_mesh_simplify_tolerance_km`: geometry simplification tolerance used
  for downstream base-mesh products.
- `base_mesh_min_segment_length_km`: minimum retained segment length after
  downstream base-mesh clipping.
- `base_mesh_preserve_outlet_stub_km`: optional outlet-stub length preserved
  during downstream base-mesh clipping.

The `[river_lat_lon]` section controls the target-grid products:

- `outlet_match_tolerance`: maximum snapping distance in meters when matching
  an ocean outlet to a coastline ocean cell.
- `channel_subsegment_fraction`: fraction of one target-grid cell used to set
  line-sampling density during rasterization.
- `channel_buffer_km`: optional physical buffer around sampled river-channel
  points. A value of `0` preserves one-cell-wide rasterization.

The `[viz_river_network]` section currently contains:

- `dpi`: output resolution for the river diagnostic plot.

## Diagnostics and expected behavior

`river_network_overview.png` overlays the simplified river network and snapped
outlets on the selected coastline background, with a global view and a CONUS
inset. `debug_summary.txt` records counts of retained segments, retained
outlets, matched and unmatched ocean outlets, inland sinks, and raster cells
flagged in each mask.

The lat-lon NetCDF product also records target-grid metadata such as
`target_grid_resolution_degrees`, `outlet_match_tolerance_m`,
`channel_buffer_m`, `matched_ocean_outlets`, and
`unmatched_ocean_outlets`.

## Running a task

To inspect source-level simplification for one named unified mesh:

```bash
polaris setup -t \
    mesh/spherical/unified/ocn_30km_lnd_10km_riv_10km/river/source/task \
    -w river_source_30km
```

To inspect the coastline-aware target-grid products for the same mesh:

```bash
polaris setup -t \
    mesh/spherical/unified/ocn_30km_lnd_10km_riv_10km/river/lat_lon/task \
    -w river_lat_lon_30km
```

The work directory for the lat-lon task contains symlinks to the shared river,
topography, and coastline steps, along with the shared `river_network.cfg`
file.