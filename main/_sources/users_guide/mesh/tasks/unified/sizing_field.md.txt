(users-mesh-unified-sizing-field)=

# Sizing-field tasks

The `mesh/spherical/unified/<mesh_name>/sizing_field` tasks build a
cell-width map on a shared latitude-longitude grid for each named unified
mesh. The sizing field combines the coastline and river products from the
upstream workflows into a single target cell-width dataset that the
downstream base-mesh step (see {ref}`users-mesh-unified-base-mesh`) passes
to the JIGSAW mesh generator.

Running these tasks is most useful when you want to inspect or tune the
sizing field without committing to a full mesh generation.

## Available tasks

Polaris registers one sizing-field task for each named unified mesh:

- `mesh/spherical/unified/<mesh_name>/sizing_field/task`

Supported `mesh_name` values are:

- `u.oi240.lr240`
- `u.oi30.lr10`
- `u.oi6to18.lr6to10`
- `u.oi.so12to30.lr10`

The task work directory contains symlinks to all upstream coastline and river
shared steps, plus:

- `sizing_field`, the step that builds `sizing_field.nc`; and
- `sizing_field_viz`, a diagnostic step that writes cell-width overview
  plots and a summary text file.

## What the sizing field contains

`sizing_field.nc` stores a `cell_width` variable on the mesh's lat-lon target
grid. Each grid cell holds the target MPAS cell width in km. The field is
built by combining:

- the ocean background (a 2-D cell-width array derived from the mesh family
  configuration, e.g. constant or RRS latitude-dependent);
- the land background (`land_background_km`); and
- optional refinement controls derived from the coastline and river masks.

## Refinement controls

Two optional refinements can be enabled independently:

**Coastline refinement** (`enable_coastline_refinement`)
Sets the target cell width at the coastline raster edge to the finest cell
width between ocean and land backgrounds. A linear transition of width
`coastline_transition_land_km` can be applied on the land side of the
coastline to smooth the transition back to the land background, and
`coastline_transition_exponent` controls the shape of that transition.

The transition is by far the steepest feature in the sizing field -- its
slope is `|land_background - ocean_background|` divided by the transition
width, roughly a hundred times the open-ocean gradient. Where that gradient
meets the ocean it seeds defects in JIGSAW's hexagonal packing, and those
defects carry the shortest `dcEdge` values, which in turn cap the
forward-run time step.

An exponent of 2 (the default) makes the blending factor and its first
derivative both vanish at the coastline, so the field leaves the ocean flat
and does its steepening at the inland end, where only cells that get culled
away feel it. An exponent of 1 is the plain linear ramp. Because the
exponent changes the *shape* rather than the *extent* of the transition, it
costs no extra inland reach: river geometry still begins exactly where the
blend ends. See the {ref}`design doc <design-docs>`
`unified_mesh_dc_edge_noise`.

**River-channel refinement** (`enable_river_channel_refinement`)
Reduces the target cell width to `river_channel_km` on rasterized river
channels. This aligns mesh edges with river centerlines in the final JIGSAW
mesh.

## Cull emulation

By default (`enable_cull_emulation`), the coastline used for the land-side
blend is not the shared coastline product directly but an *effective*
coastline that anticipates which cells the MPAS cull in `e3sm/init` will
keep as ocean/sea-ice: the below-sea-level fraction is averaged at the local
ocean-background scale, critical ocean passages are widened in proportion to
the local resolution, and the result is flood filled and unioned with the
shared coastline mask. This prevents land/river refinement from leaking
into the CFL-limited ocean/sea-ice domain (e.g. in coastal lagoons whose
thin barriers are not resolved at mesh scale). The design and validation
are documented in the `unified_mesh_cull_leak` design doc (see
{ref}`design-docs`).

## Configuration

The sizing-field task shares the mesh's `sizing_field.cfg` file. The
relevant options are in the `[sizing_field]` section:

- `ocean_background_mode`: background ocean resolution mode. Options are
  `constant` (one cell width everywhere) and `rrs_latitude` (latitude-
  dependent). The `so_region` mesh family uses an additional mode for
  Southern Ocean refinement.
- `ocean_background_min_km`: minimum ocean background cell width in km.
  For `constant` mode, set equal to `ocean_background_max_km`.
- `ocean_background_max_km`: maximum ocean background cell width in km.
  For `rrs_latitude`, this is the equatorial resolution. For `so_region`,
  this is the coarse background.
- `land_background_km`: background land cell width in km.
- `enable_coastline_refinement`: whether to apply coastline-proximity
  refinement.
- `coastline_transition_land_km`: width in km of the linear-transition zone
  on the land side of the coastline. Set to `0` to apply only at the
  raster edge.
- `coastline_transition_exponent`: exponent of the land-side blending
  factor. `1` is linear; `2` (the default) flattens the mesh-size gradient
  at the coastline and steepens it inland without extending the
  transition's reach.
- `enable_river_channel_refinement`: whether to refine cells on the
  river-channel mask.
- `river_channel_km`: target cell width in km along river channels.
- `enable_cull_emulation`: whether to build the effective ocean mask by
  emulating the MPAS cull at mesh scale (see above).
- `cull_emulation_grow_threshold`: hysteresis lower bound on the mesh-scale
  candidate-ocean fraction for growing the emulated ocean into
  threshold-ambiguous fringes.
- `passage_widen_factor` and `passage_widen_factor_high_lat`: width of the
  swath around critical ocean passages that receives ocean-background
  sizing, in units of the local ocean background cell width, equatorward
  and poleward of `passage_widen_latitude_threshold` respectively.

Visualization options are in `[sizing_field_viz]`:

- `dpi`: output resolution for diagnostic plots.
- `cell_width_cmap`: colormap for cell-width plots.

## Running a task

```bash
polaris setup -t \
    mesh/spherical/unified/u.oi30.lr10/sizing_field/task \
    -w sizing_field_30km
```

The `sizing_field_viz` step writes `sizing_field_overview.png` (a global
cell-width map), an active-control diagnostic map (showing which refinement
control dominates at each grid cell), and `debug_summary.txt` with min/max
cell widths and count statistics.
