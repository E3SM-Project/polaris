(users-mesh-unified-river)=

# River-network tasks

The unified-mesh river-network tasks simplify HydroRIVERS source data,
reconcile retained outlets with the selected coastline product, and build
target-grid masks and clipped base-mesh geometry that downstream
sizing-field and base-mesh workflows (see {ref}`users-mesh-unified-sizing-field`
and {ref}`mesh-base-mesh-task`) can consume directly.

The standalone task runs the full river workflow in one place: source
simplification, coastline-aware outlet snapping, target-grid rasterization,
coastline-clipped base-mesh geometry, and diagnostic plots.

The downstream sizing-field and base-mesh workflows reuse these same shared
steps without re-running them.

## Available tasks

Polaris registers one standalone river task for each named unified mesh:

- `mesh/spherical/unified/<mesh_name>/river/task`

Supported `mesh_name` values are:

- `u.oi240.lr240`
- `u.oi30.lr10`
- `u.oi6to18.lr6to10`
- `u.oi.so12to30.lr10`

The task work directory contains symlinks to:

- `river_simplify`, the shared source-level step that downloads and
  simplifies HydroRIVERS;
- `river_rasterize`, the shared lat-lon step that writes raster and outlet
  products;
- `river_clip`, the shared base-mesh conditioning step that clips river
  geometry to the coastline;
- `viz_river_network`, a diagnostic step that writes an overview plot and
  summary text file; and
- the upstream coastline and topography-combine shared steps
  (see {ref}`users-mesh-unified-coastline`).

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
  basin and outlet metadata, with networks sorted largest-first by outlet
  drainage area; and
- `retained_outlets.geojson`, one feature per retained ocean outlet or inland
  sink.

The lat-lon task writes:

- `river_network.nc`, containing `river_channel_mask`, `river_outlet_mask`,
  `river_ocean_outlet_mask`, and `river_inland_sink_mask`;
- `river_outlets.geojson`, containing source and snapped outlet coordinates,
  snapped grid indices, snapping distance, and `matched_to_ocean`; and
- `river_network_overview.png` and `debug_summary.txt` from the visualization
  step.

The downstream shared base-mesh river step (see {ref}`mesh-base-mesh-task`)
also writes:

- `clipped_river_network.geojson`, with networks sorted largest-first by
  outlet drainage area;
- `clipped_outlets.geojson`;
- and `clipped_river_network.nc`.

These clipped products are intended for the unified base-mesh workflow rather
than the standalone inspection tasks.

## Configuration

Each task links the shared `river_network.cfg` file and inherits the selected
mesh's `unified_mesh` settings, including the target-grid resolution and
coastline convention (see {ref}`users-mesh-unified-coastline`).

The `[sizing_field]` section in each per-mesh config provides the resolution
parameters used to auto-derive thresholds:

- `land_background_km`: background land cell width in km. Used to compute
  `drainage_area_threshold` when that option is set to `-1`.
- `river_channel_km`: target cell width along river channels in km. Used to
  compute `outlet_distance_tolerance` when that option is set to `-1`.

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
  retaining a source segment. The default value of `-1` signals
  auto-derivation from the `[sizing_field]` land resolution:
  `drainage_area_threshold = land_background_km² × 1×10⁸ m²`
  (100 grid cells at land resolution). For example, the 30 km ocean /
  10 km land mesh uses `1.0×10¹⁰ m²` and the 240 km mesh uses
  `5.76×10¹²  m²`. Override this in a per-mesh config to fix the
  threshold explicitly. Reducing this value retains finer tributaries at
  the cost of a much larger, denser network; increasing it produces a
  sparser network containing only the largest river systems.
- `outlet_distance_tolerance`: minimum great-circle spacing in meters
  between retained non-endorheic (ocean) outlets, and also a geographic
  fallback distance used during upstream traversal. The default value of
  `-1` signals auto-derivation from the `[sizing_field]` river-channel
  resolution: `outlet_distance_tolerance = river_channel_km × 1000 m`.
  During the outlet-selection pass, candidates are ranked from largest to
  smallest drainage area and added greedily; any candidate whose endpoint
  falls within this distance of an already-retained ocean outlet is
  skipped, preventing many closely spaced outlets from being kept in the
  same delta or estuary. Inland sinks are exempt from this check and are
  always retained regardless of their proximity to other inland sinks.
  The same tolerance is reused during upstream traversal as a fallback:
  a tributary that is too small to satisfy `tributary_area_ratio` is
  still retained if the minimum great-circle distance from any point on
  that tributary to any already-retained basin segment exceeds this
  value, preserving geographically isolated branches that would otherwise
  be pruned on drainage-area grounds alone.
- `tributary_area_ratio`: minimum ratio of tributary drainage area to
  basin-outlet drainage area for retaining a nearby tributary. At each
  confluence, the upstream branch with the largest drainage area is
  always retained as the main stem. Each additional upstream branch is
  retained if its drainage area is at least this fraction of the
  **basin outlet's** drainage area. Strahler stream-order-1 headwater
  tributaries skip this area check entirely and go straight to the
  distance-based fallback (see `outlet_distance_tolerance` above).
  Branches that fail both tests are pruned. Lowering this ratio retains
  more tributaries; raising it prunes all but the most significant
  branches.
- `base_mesh_clip_distance_km`: inland clip distance in km applied when
  preparing base-mesh river products. The coastline dataset stores a
  signed-distance field that is negative inland and positive over the
  ocean. River-segment coordinates that lie within this distance of the
  coastline — or seaward of it — are trimmed away, removing the
  near-shore portions of river segments that would potentially affect
  resolution too close to the ocean-sea ice portion of the base mesh
  and thus could result in smaller-than-acceptable cells in the culled
  ocean-sea ice mesh. Linear interpolation is used to
  find the exact crossing point along each segment edge. Increase this
  value to push the clip boundary farther inland; reduce it to preserve
  more of each river's lower reach.
- `base_mesh_simplify_tolerance_km`: Douglas-Peucker simplification
  tolerance in km applied to each clipped segment. The tolerance is
  converted to degrees using the equatorial approximation
  (km ÷ 111), so the default 2 km corresponds to roughly 0.018°.
  Simplification reduces vertex count while preserving overall river
  shape, making the geometry more suitable for mesh-generation tools that
  operate at coarser scales. Increasing this value produces simpler,
  smoother geometry; decreasing it preserves finer bends at the cost of
  higher vertex count.
- `base_mesh_min_segment_length_km`: minimum arc-length in km that a
  segment must have after clipping and simplification in order to be
  retained. Clipping near the coastline often leaves short stubs that
  are numerically harmless but visually noisy; this threshold discards
  them. Arc-length is computed along the sphere using the haversine
  formula.
- `base_mesh_preserve_outlet_stub_km`: optional minimum stub length in
  km to preserve for outlet segments that would otherwise be fully
  removed by clipping. When an outlet segment's entire length lies within
  `base_mesh_clip_distance_km` of the coastline and would normally be
  dropped, a stub is reconstructed from the clip boundary back to the
  outlet endpoint. If that stub is at least this long it is kept,
  ensuring the outlet location remains present in the clipped product;
  otherwise the segment is still discarded. The default value of 0.0
  disables stub preservation entirely. Set this to a small positive value
  (e.g., 1–5 km) when outlet positions must be retained in the clipped
  product even when most of the segment has been removed.

The `[river_rasterize]` section controls the target-grid products:

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

To run the full river-network workflow for one named unified mesh:

```bash
polaris setup -t \
    mesh/spherical/unified/u.oi30.lr10/river/task \
    -w river_30km
```

The work directory contains symlinks to the shared river, topography, and
coastline steps, along with the shared `river_network.cfg` file.