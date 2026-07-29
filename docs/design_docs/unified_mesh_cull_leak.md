# Unified Mesh: Fixing Resolution Leakage into the Ocean/Sea-Ice Domain

date: 2026/07/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Unified meshes prescribe finer resolution for the land/river domain than for
parts of the ocean/sea-ice domain (e.g. 10 km land vs 30 km ocean in
`u.oi30.lr10`). The ocean and sea ice are CFL limited, so land/river
resolution "leaking" into the culled ocean/sea-ice meshes causes forward-run
instability: `u.oi30.lr10` was found to contain edges with `dcEdge` down to
9.16 km against a 30 km nominal ocean background, and the MPAS-Ocean `short`
forward run produced NaNs precisely at the finest cells.

This design adds two capabilities:

1. A **ratio-based `dcEdge` diagnostic** in the `e3sm/init` `topo/cull` mask
   step that fails loudly if the culled ocean/sea-ice domain contains edges
   whose `dcEdge` deviates too far from the local ocean background cell width,
   before any forward run is attempted.
2. An **effective ocean mask** for the unified sizing field that anticipates
   what the MPAS cull will keep, by emulating the cull on the lat/lon sizing
   grid at mesh scale, so the sizing field never prescribes land/river
   resolution in regions that end up in the ocean/sea-ice domain.

Success means (a) all four unified meshes rebuild with no ocean/sea-ice edge
below the diagnostic threshold, and (b) any future regression of this kind is
caught at the cull-mask step rather than by a forward-run crash.

## Diagnosis

Analysis of the `test_20260721` results on Chrysalis (all four unified
meshes: `u.oi30.lr10`, `u.oi240.lr240`, `u.oi6to18.lr6to10`,
`u.oi.so12to30.lr10`) established two mechanisms. Defining the *ratio* of an
edge as `dcEdge` divided by the ocean background cell width at the edge
location, clean jigsaw noise spans about [0.76, 1.39]; every mesh except the
uniform-resolution `u.oi240.lr240` had edges with ratios of 0.29–0.34.

### Mechanism A (dominant): flood-fill connectivity is resolution dependent

Coastal lagoons and shallow banks (Banc d'Arguin, Chukotka lagoons, Exmouth
Gulf, the Vistula/Curonian Lagoons, Gulf of Sidra, ...) are below sea level
but sit behind thin barriers (spits, tidal flats). At the 1/32-degree
resolution of the shared coastline products, the barrier is *resolved*: the
coastline flood fill classifies the whole lagoon as land, so the sizing field
places it in the land-side coastline blend (10 -> 30 km for `u.oi30.lr10`).
On the MPAS mesh, however, the same cells have `ocean_frac` of 0.5–1.0 (the
conservative remap of the same source ocean mask is correct — most of their
*area* is below sea level), the barrier occupies too little area of any
mesh-scale cell to pull `ocean_frac` below 0.5, and a connected path of
candidate-ocean cells reaches the lagoon, so the MPAS flood fill keeps it.

No land cell is promoted to ocean anywhere in this mechanism: the two grids
simply see different topology at different resolutions. The lagoon is culled
on the fine lat/lon grid but retained on the coarse MPAS mesh because
averaging erases the narrow land barrier.

### Mechanism B (secondary): critical passages preserved wider on MPAS

Critical ocean passages (Fury & Hecla Strait, the Northwest Passage, Nares
Strait, Akimiski Strait, Ilulissat, Carroll Inlet) are preserved on the MPAS
mesh via transect cell masks plus `widen_transect_edge_masks` — a swath 1–3
cells wide — while the lat/lon rasterization of the same transects is a
single grid cell (~0.125 degree) wide. Cells with `ocean_frac` as low as
0.10 are kept inside a region the sizing field classifies as land-side blend.

## Requirements

### Requirement: dcEdge ratio diagnostic in the cull-mask step

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

For unified meshes, the `topo/cull` mask step of the `e3sm/init` component
must fail with an informative error if the ocean/sea-ice domain implied by
the ocean cull mask contains base-mesh edges whose `dcEdge` is below
`min_dc_edge_ratio` times, or above `max_dc_edge_ratio` times, the local
ocean background cell width. The thresholds must be config options so each
unified mesh can override them. The check must be ratio based (not absolute)
so it applies to variable-resolution meshes. The error must localize the
violations (worst clusters in lat/lon) and a diagnostics file must be
written to aid debugging.

### Requirement: sizing field consistent with the MPAS-mesh view of topography

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

The unified sizing field must prescribe (approximately) the full ocean
background cell width everywhere the MPAS cull will keep as ocean/sea-ice,
while preserving land/river refinement elsewhere. Constraints agreed during
design:

- The cull masks themselves stay on the MPAS mesh; culling from a remapped
  lat/lon coastline is not an option because much of the cull logic is mesh
  dependent.
- The shared coastline products (`prepare_coastline`) stay mesh independent
  and unchanged; all mesh-dependent adjustments happen per mesh in the
  sizing-field step.
- Widening of critical passages for sizing must be proportional to the local
  ocean background resolution.
- Exact prediction of the cull is impossible (the outcome near the
  `ocean_frac` = 0.5 threshold depends on the exact MPAS cell tiling), so
  the prediction must be deliberately generous toward ocean, with the
  diagnostic from the first requirement as the backstop.

## Algorithm Design

### Algorithm Design: dcEdge ratio diagnostic in the cull-mask step

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

After the ocean cull mask is created, select base-mesh edges whose two
adjacent cells are both kept (the interior edges of the future culled ocean
mesh). Sample the ocean background cell width from the mesh's sizing-field
product (nearest neighbor on the lat/lon sizing grid) at each edge location
and form `ratio = dcEdge / background`. Fail if
`min(ratio) < min_dc_edge_ratio` or `max(ratio) > max_dc_edge_ratio`.

Threshold justification (from `test_20260721`): clean jigsaw noise spans
[0.76, 1.39] x background; the contaminated meshes reached 0.29. The
lower bound is the meaningful guard, since fine cells leaking into the
ocean are a CFL hazard; `min_dc_edge_ratio = 0.65` leaves margin above the
clean noise floor while failing the contaminated meshes decisively.

The upper bound only flags anomalously coarse edges, which are a mild
mesh-quality issue rather than a stability hazard. It must tolerate
isolated jigsaw outliers whose magnitude grows with the number of edges:
across the four regenerated meshes the maximum ratio rose monotonically
with edge count (1.32 at 21k edges, 1.42 at 1.4M, 1.50 at 2.4M, 1.51 at
12M), so a tight ceiling is fragile. `max_dc_edge_ratio = 2.0` still
catches an edge that is genuinely double the intended resolution while
tolerating lone coarse jigsaw blips on large meshes.

### Algorithm Design: effective ocean mask via mesh-scale cull emulation

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

Build a per-mesh *effective ocean mask* on the lat/lon sizing grid:

1. **Candidate fraction**: start from the combined-topography `ocean_mask`
   fraction (the same source field that becomes `ocean_frac` on the MPAS
   mesh) block-averaged from the finest (1/32-degree) grid to the mesh's
   sizing grid.
2. **Mesh-scale averaging**: box-average the fraction over the local ocean
   background cell width L(x) — emulating `ocean_frac` on mesh-scale cells —
   and threshold at 0.5. The local window is quantized into geometric bins;
   the longitude window grows as 1/cos(latitude).
3. **Critical transects**: remove rasterized land blockages; add ocean
   passages dilated to a swath of `passage_widen_factor` x L (a larger
   factor poleward of the sea-ice latitude threshold, mimicking
   `widen_transect_edge_masks`).
4. **Flood fill** from the standard ocean seed points (as the MPAS cull
   does), with periodic longitude connectivity.
5. **Hysteresis growth**: extend the flood-filled mask into connected
   regions whose fraction is at least `grow_threshold` (< 0.5). This covers
   cells whose fate at the strict threshold depends on the exact MPAS cell
   tiling, without promoting isolated inland regions.
6. **Union** with the shared flood-filled coastline `ocean_mask`. The union
   never demotes shared-mask ocean, so true coastlines are unaffected.

Recompute the signed distance from the effective coastline (reusing the
existing KD-tree machinery) and apply the existing land-side blend to the
effective signed distance.

The trade-off is asymmetric by construction: over-prediction (effective
ocean that the actual cull removes) only coarsens land/river sizing toward
the ocean background — no CFL hazard — while under-prediction is caught by
the diagnostic. Prototype validation on all four meshes (see below) showed
over-prediction of 2.4–3.7% of the ocean cell count with essentially no
overlap with river channels.

### Prototype validation (2026/07/23)

The algorithm was prototyped offline with `grow_threshold = 0.35`
and passage widening of 1.5x / 3.0x L equatorward/poleward of 43 degrees, and
validated against the actual cull masks of the `test_20260721` runs:

| mesh | kept cells | under-pred (base -> emul) | over-pred (on river) | current min ratio | predicted min ratio |
| --- | --- | --- | --- | --- | --- |
| u.oi30.lr10 | 462,924 | 1,328 -> 335 | 16,943 (0) | 0.31 | 0.76 |
| u.oi240.lr240 | 7,313 | 125 -> 1 | 185 (0) | 0.80 (clean) | 1.00 |
| u.oi6to18.lr6to10 | 4,015,940 | 5,930 -> 1,168 | 30,287 (19) | 0.34 | 0.86 |
| u.oi.so12to30.lr10 | 794,665 | 1,179 -> 181 | 18,927 (0) | 0.29 | 0.82 |

"Predicted min ratio" is the minimum, over the current culled-mesh edges, of
the sizing the effective coastline would prescribe relative to the ocean
background; it exceeds the 0.65 diagnostic threshold on every mesh (no
edge below threshold), with residual under-predicted cells all lying close
enough to the effective coastline that the blend keeps them near the ocean
background.

## Implementation

### Implementation: dcEdge ratio diagnostic in the cull-mask step

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

- The ratio check is a testable public function in
  `polaris/tasks/e3sm/init/topo/cull/dc_edge_diagnostics.py`; it writes
  `ocean_dc_edge_diagnostics.nc` (per-edge ratio and violation masks), logs
  a summary with the worst violation clusters, and raises `ValueError` on
  failure.
- `CullMaskStep` gains an optional `sizing_field_step`; when set (unified
  meshes), `sizing_field.nc` is linked as an input and the check runs at
  the end of `run()`, after all masks are written, using `oceanCullMask`
  (the ocean/sea-ice domain including cavities).
- `get_cull_topo_steps()` passes the sizing-field build step (already
  constructed upstream for unified meshes) to `CullMaskStep`; for simple
  meshes the diagnostic is skipped.
- `_get_cull_topo_config()` additionally merges the unified-mesh configs
  (`unified_mesh.cfg` and `{mesh_name}.cfg`) so per-mesh threshold
  overrides are honored; defaults live in
  `polaris/tasks/e3sm/init/topo/cull/cull.cfg` (`[cull_mesh]`
  `min_dc_edge_ratio`, `max_dc_edge_ratio`).

### Implementation: effective ocean mask via mesh-scale cull emulation

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

- Reusable helpers in a dependency-light leaf module
  `polaris/mesh/spherical/unified/effective_ocean.py`: mesh-scale variable
  box averaging, passage widening, seeded flood fill, hysteresis growth,
  and effective-mask assembly.
- `BuildSizingFieldStep` links the finest-resolution combined topography
  (for the candidate fraction) as an additional input, builds the effective
  ocean mask and effective signed distance, and passes them (instead of the
  shared coastline fields) to `sizing_field_dataset()`. New diagnostic
  variables are added to `sizing_field.nc`: the effective and emulated
  ocean masks, the widened passages and the effective signed distance.
- New config options in `[sizing_field]`: `enable_cull_emulation` (default
  `true`), `cull_emulation_grow_threshold` (0.35), `passage_widen_factor`
  (1.5), `passage_widen_factor_high_lat` (3.0) and
  `passage_widen_latitude_threshold` (43 degrees).
- The base meshes change as a result; downstream cached products (sizing
  field, base mesh and `e3sm/init` topography products) are regenerated,
  while shared coastline caches are unaffected.

Development takes place on the `fix-uoi30lr10-cull` branch; see
`PLAN_fix_unified_mesh_cull_leak.md` there for the commit series.

## Testing

### Testing and Validation: dcEdge ratio diagnostic in the cull-mask step

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

Unit tests in `tests/e3sm/init/topo/test_cull_mask.py` exercise the pure
ratio-check function with small synthetic meshes and sizing fields: a
passing case, a min-ratio failure, a max-ratio failure, correct edge
selection (only edges with both cells kept), and the contents of the
diagnostics file. Integration-wise, re-running only the mask step against
the existing `test_20260721` work directories must fail on the current
contaminated masks and pass after the meshes are regenerated with the fix.

### Testing and Validation: effective ocean mask via mesh-scale cull emulation

Date last modified: 2026/07/23

Contributors: Xylar Asay-Davis, Claude

Unit tests for `effective_ocean.py` construct synthetic topographies where
the expected behavior is known: a thin-barrier lagoon that must be included
at a coarse mesh scale and excluded at a fine one; hysteresis growth that
adds threshold-ambiguous fringes connected to the ocean but not isolated
inland depressions; passage widening whose swath width scales with the
local background. `test_sizing_field.py` is extended to verify the
integration (effective fields present in the output, ocean-background
sizing on emulated-ocean cells). Final validation is the regeneration of
all four unified meshes with the Part 1 diagnostic active, which must pass,
plus spot checks of the former hotspots.
