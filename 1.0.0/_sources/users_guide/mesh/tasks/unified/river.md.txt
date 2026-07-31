(users-mesh-unified-river)=

# River-network tasks

The unified-mesh river-network tasks simplify HydroRIVERS source data,
build target-grid channel masks, and prepare clipped base-mesh geometry that
downstream sizing-field and base-mesh workflows (see
{ref}`users-mesh-unified-sizing-field` and {ref}`mesh-base-mesh-task`) can
consume directly.

The standalone task runs the full river workflow in one place: source
simplification, target-grid channel rasterization, coastline-clipped base-mesh
geometry, and diagnostic plots.

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
- `river_rasterize`, the shared lat-lon step that writes the channel raster
  product;
- `river_clip`, the shared base-mesh conditioning step that clips river
  geometry to the coastline;
- `viz_river_network`, a diagnostic step that writes an overview plot and
  summary text file; and
- the upstream coastline and topography-combine shared steps
  (see {ref}`users-mesh-unified-coastline`).

## How the river network is derived

The source-level workflow follows a staged simplification strategy:

1. It downloads the HydroRIVERS archive and reads the shapefile.
2. It canonicalizes source features into one segment per `hyriv_id` when the
   source contains multiple geometries for the same river segment.
3. It filters segments by `drainage_area_threshold`.
4. It validates that the retained `next_down` graph is acyclic.
5. It identifies terminal basin roots from segments with `next_down == 0`.
6. It traverses upstream from each terminal root to keep main stems and
   significant tributaries, preserving basin connectivity and confluence
   structure. The retained segment metadata includes `outlet_hyriv_id`,
   `outlet_drainage_area`, and `river_network_rank` for later catchment
   grouping.

The `river_simplify` step is not a line-geometry simplification step in the
Douglas-Peucker sense. It is a graph simplification step: it keeps or prunes
whole HydroRIVERS segments while preserving the retained `next_down`
relationships. The algorithm builds an upstream adjacency map from the
HydroRIVERS `next_down` field, validates that the retained graph is acyclic,
and then traverses every terminal basin root. At each confluence, the upstream
segment with the largest drainage area is kept as the primary branch. Other
upstream branches are kept when they are large enough relative to that
confluence's primary branch, or when they are farther than
`branch_distance_tolerance` from the already-retained basin skeleton.

This differs from the greedy reverse-search simplification in the standalone
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh) reference
workflow that is the inspiration for the Polaris implementation. The standalone
workflow reconstructs one
basin at a time with `pyrivergraph`, rebuilds stream segments and stream order,
then mutates a per-basin R-tree of retained flowlines as it recursively searches
upstream from each outlet. Nearby candidates are accepted, rejected, or in some
cases replace smaller already-retained branches as that greedy search proceeds.
Polaris instead uses the HydroRIVERS `next_down` topology directly, processes
terminal basins independently, and applies a deterministic confluence-local
selection rule without removing retained segments later in the traversal. This
makes the implementation simpler to test and parallelize while preserving the
same intent: retain the dominant main stems and significant, geographically
separated tributaries at the mesh scale.

The lat-lon workflow then turns the simplified network into target-grid
products:

It samples the retained river lines densely enough to rasterize them onto the
chosen latitude-longitude grid, then writes a river-channel mask. Outlet
snapping and coastline reconciliation are deferred until after an MPAS base
mesh exists.

## Outputs

The source task writes:

- `simplified_river_network.geojson`, the retained river segments and their
  basin-root metadata, with networks sorted largest-first by terminal-root
  drainage area. Each feature includes:
  - `outlet_hyriv_id`, the HydroRIVERS ID of the terminal-root segment for
    that river network;
  - `outlet_drainage_area`, the terminal-root drainage area in square meters;
    and
  - `river_network_rank`, a 1-based rank with `1` denoting the largest
    retained river network for the current task configuration.

The lat-lon task writes:

- `river_network.nc`, containing `river_channel_mask`;
- `river_network_overlay.png`, `rasterized_river_network.png`, and
  `debug_summary.txt` from the visualization step.

The downstream shared base-mesh river step (see {ref}`mesh-base-mesh-task`)
also writes:

- `clipped_river_network.geojson`, with networks sorted largest-first by
  terminal-root drainage area;
- `clipped_river_network.nc`.

These clipped products are intended for the unified base-mesh workflow rather
than the standalone inspection tasks.

## Selecting individual river networks

`simplified_river_network.geojson` contains all retained river networks in one
GeoJSON feature collection. To inspect or export one network at a time, filter
features by `river_network_rank` or by the stable `outlet_hyriv_id`.

For example, this snippet writes the largest retained network to its own
GeoJSON file:

```python
import json

rank = 1

with open('simplified_river_network.geojson', encoding='utf-8') as infile:
    river_fc = json.load(infile)

features = [
    feature
    for feature in river_fc['features']
    if feature['properties']['river_network_rank'] == rank
]

network_fc = dict(
    type='FeatureCollection',
    features=features,
    metadata=river_fc.get('metadata', {}),
)

with open(
    f'river_network_rank_{rank:04d}.geojson',
    'w',
    encoding='utf-8',
) as outfile:
    json.dump(network_fc, outfile, indent=2, sort_keys=True)
```

To export the N largest networks as one combined file, use
`feature['properties']['river_network_rank'] <= n`. To create one file per
network, loop over the desired ranks and update the output filename in the
example above.

## Configuration

Each task links the shared `river_network.cfg` file and inherits the selected
mesh's `unified_mesh` settings, including the target-grid resolution. It also
uses the shared `[spherical_mesh]` setting
`antarctic_boundary_convention` when selecting the coastline product (see
{ref}`users-mesh-unified-coastline`).

The `[sizing_field]` section in each per-mesh config provides the resolution
parameters used to auto-derive thresholds:

- `land_background_km`: background land cell width in km. Used to compute
  `drainage_area_threshold` when that option is set to `-1`.
- `river_channel_km`: target cell width along river channels in km. Used to
  compute `branch_distance_tolerance` when that option is set to `-1`.

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
  `drainage_area_threshold = land_background_km² ×`
  `drainage_area_multiplier × 1×10⁶ m²`. For example, with the default
  multiplier of 100, the 30 km ocean / 10 km land mesh uses
  `1.0×10¹⁰ m²`; with its per-mesh multiplier of 10, the 240 km mesh uses
  `5.76×10¹¹ m²`. Override this in a per-mesh config to fix the
  threshold explicitly. Reducing this value retains finer tributaries at
  the cost of a much larger, denser network; increasing it produces a
  sparser network containing only the largest river systems.
- `drainage_area_multiplier`: number of land-grid-cell areas that must drain
  to a point for auto-derived channel retention. This option is only used
  when `drainage_area_threshold = -1`.
- `branch_distance_tolerance`: geographic fallback distance used during
  upstream traversal. The default value of `-1` signals auto-derivation from
  the `[sizing_field]` river-channel resolution:
  `branch_distance_tolerance = river_channel_km × 1000 m`. During upstream
  traversal,
  a tributary that is too small to satisfy `tributary_area_ratio` is
  still retained if the minimum great-circle distance from any point on
  that tributary to any already-retained basin segment exceeds this
  value, preserving geographically isolated branches that would otherwise
  be pruned on drainage-area grounds alone.
- `tributary_area_ratio`: minimum ratio of tributary drainage area to
  the primary branch drainage area at the current confluence. At each
  confluence, the upstream branch with the largest drainage area is
  always retained as the main stem. Each additional upstream branch is
  retained if its drainage area is at least this fraction of the
  primary branch's drainage area. Branches that fail this area test are
  still retained if they are far enough from the already-retained basin
  skeleton to satisfy the distance-based fallback (see
  `branch_distance_tolerance` above). Branches that fail both tests are
  pruned. Lowering this ratio retains more tributaries; raising it prunes
  all but the most significant branches.
- `base_mesh_clip_distance_km`: inland clip distance in km applied when
  preparing base-mesh river products. The coastline dataset stores a
  signed-distance field that is negative inland and positive over the
  ocean. The clip operation is local to each river line: Polaris densifies the
  line at the coastline-grid scale, samples the signed-distance field, and
  trims only the portions that lie within this distance of the coastline or
  seaward of it. Inland portions of the same HydroRIVERS feature are preserved,
  even when clipping splits one feature into multiple pieces. Linear
  interpolation is used to find the crossing point along each sampled line
  interval. Increase this value to push the clip boundary farther inland;
  reduce it to preserve more of each river's lower reach.
- `base_mesh_simplify_tolerance_km`: Douglas-Peucker simplification
  tolerance in km applied to each clipped segment. The tolerance is
  converted to degrees using the equatorial approximation
  (km ÷ 111), so the default 2 km corresponds to roughly 0.018°.
  Simplification reduces vertex count while preserving overall river
  shape, making the geometry more suitable for mesh-generation tools that
  operate at coarser scales. If simplification would collapse a valid clipped
  piece into a degenerate geometry, Polaris keeps the unsimplified piece
  instead. Increasing this value produces simpler, smoother geometry;
  decreasing it preserves finer bends at the cost of higher vertex count.
- `base_mesh_min_segment_length_km`: deprecated for river clipping. This
  option is retained for configuration compatibility, but valid inland clipped
  river pieces are no longer discarded based on length. Polaris drops only
  degenerate geometries with fewer than two distinct points.
The `[river_rasterize]` section controls the target-grid products:

- `channel_subsegment_fraction`: fraction of one target-grid cell used to set
  line-sampling density during rasterization.
- `channel_buffer_km`: optional physical buffer around sampled river-channel
  points. A value of `0` preserves one-cell-wide rasterization.

The `[viz_river_network]` section currently contains:

- `dpi`: output resolution for the river diagnostic plot.

## Diagnostics and expected behavior

`river_network_overlay.png` overlays the simplified and clipped river networks
on the selected coastline background, with a global view and a CONUS inset.
The simplified network is drawn faintly under the clipped network so gaps in
the clipped product can be distinguished from plotting order. The clipped
network should match the simplified network except where geometry falls inside
the configured coastal exclusion band.

`rasterized_river_network.png` shows the channel mask on the shared lat-lon
grid. For high-resolution grids, the plot uses max aggregation for display so
one-cell-wide river channels remain visible in the PNG; this aggregation does
not change `river_network.nc`.

`debug_summary.txt` records counts of simplified and clipped features, unique
retained and dropped `hyriv_id` values, total simplified and clipped lengths,
and rasterized channel cells.

The lat-lon NetCDF product also records target-grid metadata such as
`target_grid_resolution_degrees` and `channel_buffer_m`.

## Running a task

To run the full river-network workflow for one named unified mesh:

```bash
polaris setup -t \
    mesh/spherical/unified/u.oi30.lr10/river/task \
    -w river_30km
```

The work directory contains symlinks to the shared river, topography, and
coastline steps, along with the shared `river_network.cfg` file.
