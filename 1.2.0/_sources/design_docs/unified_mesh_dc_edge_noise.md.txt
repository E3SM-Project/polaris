# Unified Mesh: Raising the dcEdge Floor in the Ocean/Sea-Ice Domain

date: 2026/08/09

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

The shortest edge in a culled ocean/sea-ice domain sets the forward-run time
step. On the unified meshes that edge was shorter than intended:
`u.oi6to18.lr6to10` had a 3.945 km edge against a 6 km finest ocean
background, and `u.oi30.lr10` a 19.931 km edge against 30 km — both about
0.66 of what the mesh was designed for, costing a third of the time step.

This design makes two changes:

1. **Shape the coastline transition.** The land-side blend from the ocean
   background to the land background is raised to a power, so the mesh-size
   gradient vanishes at the coastline and steepens inland. This keeps the
   steepest part of the sizing field away from the CFL-limited ocean without
   extending how far the blend reaches inland.
2. **Guard the CFL floor on absolute `dcEdge`.** The existing guard compared
   each edge against its *local* ocean background, which detects leaked
   land/river resolution but is not the CFL question. A second guard
   compares the *shortest* edge against the *finest* ocean background
   anywhere in the domain, which is.

Success means every unified mesh clears the new guard with margin. All four
now do:

| mesh | before | after |
| --- | --- | --- |
| u.oi240.lr240 | 0.7991 | 0.7991 (unchanged; uniform mesh) |
| u.oi30.lr10 | 0.6644 | 0.7730 |
| u.oi6to18.lr6to10 | 0.6574 | 0.7985 |
| u.oi.so12to30.lr10 | not measured | 0.8010 |

## Diagnosis

The short edges are not leaked land/river resolution. `dcEdge / cellWidth`
and `dcEdge / ocean_background` are identical to four decimals for all 12
million ocean edges of `u.oi6to18.lr6to10`, and `active_control` is
`background` throughout the low tail — the sizing field prescribes the full
ocean background at every one of them. The cull emulation from the
`unified_mesh_cull_leak` design doc is doing its job.

They are instead the seams of pentagon-heptagon dislocation pairs in
JIGSAW's hexagonal packing. Every ocean edge below 0.80 times its local
background has a non-hexagonal neighbor cell, against a 2.85% baseline, and
their Voronoi faces are stretched to roughly 1.6 times the ideal
`1/sqrt(3)`.

Those dislocations concentrate where the sizing field is steep. JIGSAW never
sees a coastline — only `cellWidth` and the sphere — so any coastal signal
has to act through the field. Defect density in ocean cells of
`u.oi6to18.lr6to10`, by distance to the effective coast in units of the
local ocean background:

| distance | cells | non-hexagonal |
| --- | --- | --- |
| 0-2 | 136,189 | 6.18% |
| 2-5 | 152,774 | 4.27% |
| 5-10 | 207,016 | 3.02% |
| 30+ | 2,947,149 | 1.15% |

The cause is the slope of the land-side blend,
`|land_background - ocean_background| / coastline_transition_land_km`: 0.333
on `u.oi30.lr10` and 0.222 on `u.oi6to18.lr6to10`, against an open-ocean
background gradient near 0.001.

## Requirements

### Requirement: keep the mesh-size gradient away from ocean edges

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

The sizing field must not place a steep mesh-size gradient within a few cell
widths of the ocean/sea-ice domain. Land and river refinement must still be
reached, and reached no further inland than before: every unified config
sets `base_mesh_clip_distance_km` equal to `coastline_transition_land_km` so
that river geometry begins exactly where the blend ends, and that invariant
must hold. The control must be a config option whose neutral value
reproduces the previous sizing field bit for bit.

### Requirement: guard the quantity that sets the time step

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

The `topo/cull` mask step must fail when the culled ocean/sea-ice domain
contains an edge short enough to constrain the forward-run time step beyond
what the mesh was designed for. It must not fail on an edge that is short
only relative to a coarse local background, since such an edge is longer
than the mesh's own finest intended resolution and costs nothing. Detection
of leaked land/river resolution must be retained as a separate guard.

## Algorithm Design

### Algorithm Design: keep the mesh-size gradient away from ocean edges

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

Raise the land-side blending factor to a power:

$$
h(x) = L(x) + \alpha(s)\left(H - L(x)\right), \qquad
s = \min\left(\frac{|d(x)|}{T},\; 1\right), \qquad
\alpha(s) = s^{p}
$$

with $d$ the distance inland from the effective coast, $L$ the local ocean
background, $H$ the land background, $T$ the transition width and $p$ the
exponent. The mesh-size gradient is $|H-L|\,\alpha'(s)/T$, so for $p>1$ both
$\alpha$ and $\alpha'$ vanish at the coastline: the field leaves the ocean
flat and steepens inland, where only cells the cull removes ever feel it.
$p=1$ is the previous linear ramp exactly.

The decisive property is that $p$ changes the *shape* of the transition, not
its *extent*, so the `clip == transition` invariant is preserved.

**Choosing the transition width.** Both the exponent and the width matter,
and the width matters more than it first appears. At one ocean cell width
inland the gradient is $p|H-L|L^{p-1}/T^{p}$; for a quadratic with $T=2L$
this reduces to $|H-L|/2L$, which is *identical* to the linear ramp's
gradient there. So on a mesh with $T=2L$ the shape change buys nothing at
the scale JIGSAW resolves, and everything depends on the relative resolution
jump $|H-L|/L$:

| mesh | jump | gradient at one cell width | result |
| --- | --- | --- | --- |
| u.oi6to18.lr6to10 | 0.44 | 0.222 | 0.799 |
| u.oi30.lr10, T = 2L | 0.67 | 0.333 | 0.699 |
| u.oi30.lr10, T = 3L | 0.67 | 0.148 | 0.773 |

The two meshes with a 0.67 jump therefore widen $T$ from 60 to 90 km, with
`base_mesh_clip_distance_km` moved to match. A single exponent of 2 is used
everywhere; only the per-mesh width varies, and that was already a per-mesh
parameter.

### Algorithm Design: guard the quantity that sets the time step

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

Add `min_dc_edge_abs_ratio`, checked as

```
min(dcEdge over ocean-interior edges)
    >= min_dc_edge_abs_ratio * min(ocean background over those edges)
```

Both terms come from arrays the diagnostic already builds. This is the CFL
question: the time step is set by the shortest edge globally, and a mesh is
already sized for its own finest intended resolution.

`min_dc_edge_ratio` keeps comparing each edge against its *local*
background, which is what detects a leak, and relaxes from 0.65 to 0.45 so
it stops gating on coarse-region blemishes. The contaminated meshes that
motivated it reached 0.29 to 0.34; clean meshes bottom out much higher, but
not at the 0.76 once assumed — on a 6M-cell mesh, rare packing defects in
the open ocean reach 0.51, at a different location every build and with no
sizing-field cause.

## Implementation

### Implementation: keep the mesh-size gradient away from ocean edges

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

- `_apply_transition()` in
  `polaris/tasks/mesh/spherical/unified/sizing_field/build.py` raises the
  transition fraction to `exponent`; an exponent of 1 reproduces the previous
  expression exactly and the `transition_m == 0` special case is untouched.
  `_build_coastline_candidate()` and `sizing_field_dataset()` pass it
  through, and `BuildSizingFieldStep.run()` reads the config option.
- New `[sizing_field]` option `coastline_transition_exponent`, default 2.0.
- `u.oi30.lr10` and `u.oi.so12to30.lr10` widen
  `coastline_transition_land_km` and `base_mesh_clip_distance_km` from 60 to
  90 km. `u.oi6to18.lr6to10` and `u.oi240.lr240` are unchanged.

### Implementation: guard the quantity that sets the time step

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

- `check_ocean_dc_edge()` in
  `polaris/tasks/e3sm/init/topo/cull/dc_edge_diagnostics.py` gains a
  `min_abs_ratio` argument, logs the CFL guard line unconditionally and
  raises before the ratio check when it is violated. `min_dc_edge_abs_ratio`
  is recorded in `ocean_dc_edge_diagnostics.nc`.
- New `[cull_mesh]` option `min_dc_edge_abs_ratio`, default 0.70;
  `min_dc_edge_ratio` moves from 0.65 to 0.45.
- `u.oi6to18.lr6to10`'s per-mesh `min_dc_edge_ratio` override is removed; no
  mesh needs one.

### Implementation: supporting changes

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

- `minimum_edge_length_ratio` in `[spherical_mesh_quality]` moves from 1e-4
  to 1e-5. River-network line constraints degrade land cell polygons by
  about two orders of magnitude, independently of anything in this design,
  leaving the old guard on two to five times margin against a floor that
  drops as meshes get finer.
- Four `[spherical_mesh]` options — `jigsaw_optm_kern`, `jigsaw_optm_iter`,
  `jigsaw_optm_qtol` and `jigsaw_optm_qlim` — expose JIGSAW's optimization
  settings at exactly the values `QuasiUniformSphericalMeshStep` previously
  hard-coded, so no mesh changes. No mesh overrides them.

## Testing

### Testing and Validation: keep the mesh-size gradient away from ocean edges

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

Unit tests in `tests/mesh/spherical/unified/test_sizing_field.py` cover the
blend directly: an exponent of 1 reproduces the linear ramp exactly; a
quadratic stays closer to the ocean background just inland of the coast; and
every exponent reaches the land background at the same distance, which is
what keeps river geometry out of the blend. Two further tests pin the
invariants rather than the numbers — `clip == transition` on every mesh, and
no mesh exceeding the coastal gradient of the one known to pass — so a new
mesh with a large relative jump and a narrow transition fails at unit-test
time rather than after a rebuild.

### Testing and Validation: guard the quantity that sets the time step

Date last modified: 2026/08/09

Contributors: Xylar Asay-Davis, Claude

Tests in `tests/e3sm/init/topo/test_dc_edge_diagnostics.py` exercise the new
guard on synthetic meshes: it fails on an edge short against the finest
background, and passes an edge that is short only against a coarse local
background — the `u.oi6to18.lr6to10` case.
`tests/e3sm/init/topo/test_unified_tasks.py` checks that every mesh resolves
to the shared thresholds with no override.

Integration validation is the rebuild of all four unified meshes on
Chrysalis, reported in the summary table above.

## Findings

This section records what was learned along the way, including approaches
that were tried and abandoned. None of it is part of the shipped design.

### The threshold this work started from rested on a wrong conclusion

`u.oi6to18.lr6to10` previously carried a per-mesh `min_dc_edge_ratio` of
0.64, recorded as a "real, if small, resolution leak" on the grounds that
clean jigsaw noise bottoms out near 0.76. That 0.76 came from meshes 10 to
500 times smaller. The ratio's 0.01-percentile is 0.810 to 0.814 on all
three meshes measured, so the distribution does not change with mesh size —
only the number of draws does, and the minimum falls accordingly: 0.799 at
21 thousand ocean edges, 0.664 at 1.4 million, 0.643 at 12 million.
`u.oi30.lr10` was clearing the 0.65 default by luck rather than by margin.

When investigating a future failure, compare `dcEdge` against `cellWidth`
before suspecting the sizing field. If that ratio agrees with
`dcEdge / ocean_background`, the field is not the problem.

### A flat collar was tried first, and broke a river-workflow invariant

The first implementation held the ocean background flat for
`2 x ocean_background` inland before starting the linear ramp. It worked on
the dcEdge metrics — `u.oi30.lr10` went from 0.664 to 0.778 — but its reach
is `T + 2L`, which pushed the blend on `u.oi6to18.lr6to10` from 35.6 km to
71.6 km inland and put river geometry inside it: river-mask cells held above
1.05 times their target rose from 3.84% to 6.45%. The exponent reaches the
same place without spending reach.

Shortening `T` to pay for a collar was screened and is worse than doing
nothing: halving the transition drove the worst ocean ratio to 0.6476 and
doubled the near-coast tail.

### The centroidal-Voronoi kernel was tried and reverted

`cvt+dqdx` optimizes the Voronoi cells that carry `dcEdge` rather than the
triangulation, and on synthetic spheres it beat the default on both bulk and
tail — pooled minimum 0.755 against 0.682 over 2.3M cells uniform, 0.773
against 0.630 over 1.8M cells graded. It thinned the bulk of the real
distribution about fourfold. It was reverted anyway: `u.oi30.lr10` failed
the cell-polygon quality check outright, and the bulk gain never reached the
metric that matters, since the CFL floor is set by rare defects rather than
by the bulk.

The discriminator is JIGSAW's line-constraint geometry. Unified meshes hand
JIGSAW the retained river network as `edge2` constraints — 122,198 vertices
on `u.oi6to18.lr6to10`. Adding constraint polylines with the same
segment-length distribution to the synthetic world reproduces the failure:
far from any constraint, CVT with constraints reaches 0.613 and puts eight
edges below 0.75, while CVT alone or the default kernel with constraints
stay near 0.77. Vertices pinned on constraint edges cannot move under
Voronoi-centroid smoothing, so the pinned network behaves as a rigid
inclusion and the frustration relieves as defects elsewhere.

The same constraints degrade cell polygons by about two orders of magnitude
for either kernel, which is why `minimum_edge_length_ratio` moved. That
degradation is confined to land: the minimum over ocean cells is 0.27 to
0.40 on every mesh measured, while over land it reaches 2.2e-4 to 5.1e-4.

### Raising the exponent instead of the width does not work

At fixed reach, higher exponents buy coastal suppression monotonically —
near-coast worst climbs from 0.7880 at quadratic to 0.8005 at quintic — but
the overall worst falls just as steadily, from 0.7748 to 0.7507, back to the
linear baseline. The steeper inland kink seeds its own defects that reach
the ocean score. Widening the transition is the lever that works.

### The river constraints work as intended

Measuring the distance from constraint *vertices* to the nearest cell center
gives a median of 1.5 km on a 6 km mesh, which looks like the constraints
are being ignored. Measuring to the constraint *lines* instead shows about
129,000 cells locked within 250 m — 1.06 per constraint vertex — with the
count flat from 250 m out to 2 km. JIGSAW conforms to the constraint paths
and redistributes vertices along them, so cell centers follow the river
network even though the input nodes are not preserved. Nothing needs fixing
here, and the obvious measurement gives the wrong answer.

The snap tolerance is likewise correct as designed: it is half
`river_channel_km` on every mesh, and the median constraint edge comes out at
0.94 of the river target. About 12% of vertex pairs sit closer than the
tolerance because `_merge_close_centroids` does not iterate to a fixed point,
but clipping that tail in the synthetic screen changed the polygon minimum
from 1.65e-03 to 1.80e-03, so it is not worth fixing on mesh-quality grounds.

### Screening a minimum needs a much larger sample than screening a bulk

Two methodological errors are worth recording. The first screen analyzed the
JIGSAW triangulation and never the Voronoi polygons, so the cell-polygon
failure mode was invisible to it. More importantly, CVT at its default 16
iterations produced a 0.579 outlier in one of five realizations, which was
read as under-convergence to be cured with more iterations rather than as
evidence of a heavy extreme tail. The cull diagnostic reports a *minimum*
over millions of edges; estimating that from a few realizations of a few
hundred thousand edges cannot resolve a defect rate near one in a million,
and a screen reporting only bulk percentiles will show a tail-heavy kernel as
an unambiguous win. Pool enough realizations that the combined edge count
approaches the target mesh, and report the pooled minimum and the counts
below the thresholds of interest.

A related trap: an identical sizing field at a point does not imply an
identical mesh at that point. JIGSAW's front advance and optimization are
global, so changing the field along every coastline moves the point
distribution everywhere, including where the field did not change.

### Divergence from the reference workflow

The standalone workflow Polaris' unified base mesh is based on,
[`mpas_land_mesh`](https://github.com/changliao1025/mpas_land_mesh), applies
an Eikonal gradient limiter to the spacing field before meshing —
`spac.slope = dhdx_lim` with a default of 0.25, then `jigsawpy.cmd.marche`.
Polaris does not. This was noted but not pursued.
