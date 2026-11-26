(design-ocean-analysis-observations)=

# Comparison with Observations

Creation date: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

## Summary

This design adds comparison with observations to the Polaris analysis of
Omega simulations. It is the core of Phase 2 of {ref}`design-ocean-analysis`.
Phase 1 maps each simulated climatology on its own. Phase 2 puts it beside an
observational climatology, maps the difference, and reports the area-weighted
mean and root-mean-square difference.

The first comparisons are:

| Field | Reference | Period |
| --- | --- | --- |
| Temperature and salinity at depth | WOA23 1991–2020 normal | 1991–2020 |
| Sea surface temperature | ESA CCI SST v3.0 climatology | 1991–2020 |
| Sea surface salinity | ESA CCI SSS v5.5 | 2010–2023 |
| Mixed-layer depth | de Boyer Montégut et al., v2023 | profiles from 1970–2021 |
| Sea surface height | Copernicus Marine DUACS DT2024 | 1993–2022 |
| AMOC and Ekman transport at 26.5°N | RAPID v2024-2 | 2004–2024 |

WOA23 is also the second reference for sea surface temperature and salinity.

Comparison happens on the simulation's own mesh, as
{ref}`design-ocean-analysis` requires, and in Omega's own variables,
conservative temperature and absolute salinity. No model field is
interpolated horizontally. The observations are converted and remapped
instead (D1).

Each dataset is processed once into a product on its own grid, cached in the
Polaris database, as WOA23 already is for initial conditions. An analysis
remaps the products it needs to its simulation's mesh, once. No user
downloads or processes raw observations (D9).

The comparisons are the first demanding workload for Phase C of task
parallelism ([polaris#892](https://github.com/E3SM-Project/polaris/pull/892)),
which lets a step hand out the items of its loop as pieces that run on any
node. Each comparison figure, and each remapped season of a product, is such
a piece (D14).

Two pieces of Omega work are dependencies. Omega must compute mixed-layer
depth as it runs, with the reference's criterion (D10). The AMOC comparison
needs the transport across the line at 26.5°N, which is being added to Omega
as part of the tail of Phase 1 ({ref}`design-ocean-analysis-regional-moc`).

Success is that the analysis of an Omega run on any mesh produces these
comparisons, with no observational data on the machine beyond what Polaris
downloads from its own database.

Out of scope:

- matching the observations' period to a simulation's, which is Phase 3
  (D2);
- velocity, eddy kinetic energy, meridional heat transport, transports
  through sections, and Antarctic products;
- regional metrics, and comparison of one run with another.

### Open questions

1. **Remapping method.** D11 proposes bilinear weights for state fields and
   conservative weights for fluxes. The best weights depend on both the
   source and the mesh, so is one rule per product enough, or should the
   choice also depend on the mesh's resolution relative to the source?
2. **Sea surface height corrections.** Which sea surface height does Omega
   write in a coupled run, and does it respond to atmospheric and sea-ice
   pressure loading? The answer decides whether an inverse-barometer or
   sea-ice loading correction is made before comparison with absolute
   dynamic topography.
3. **Sea surface temperature under sea ice.** Should it be compared where the
   observations are ice-covered and both fields are near freezing?
4. **Caching remapped products across analyses.** Production meshes are
   analyzed many times. Should products remapped to released E3SM meshes be
   cached in the database, with a check that the mesh matches (D13)?
5. **Monthly maximum mixed-layer depth.** None of the chosen references has
   one. Should Omega write it anyway, for model-only maps of convection?
6. **RAPID seasonal cycle and profile.** Should the AMOC comparison add the
   mean seasonal cycle and the mean overturning profile at 26.5°N?
7. **Applying the weights.** `ncremap` has been much faster than in-process
   remapping in MPAS-Analysis. In-process remapping, with pyremap's
   `Remapper.remap_numpy()`, starts no process from a piece, which handing
   out work prefers. Task parallelism may change which is faster, so both are
   measured on these steps before one is chosen.

## Requirements

### Requirement: Each comparison maps the model, the observations and their difference

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

For each compared field, season and elevation, the analysis shall map the
simulated climatology, the observational climatology and the simulated minus
the observed. It shall report the area-weighted mean and root-mean-square
difference over the ocean both cover. The data behind every map and metric
shall be written beside it.

### Requirement: The comparison is on the simulation's mesh, in the model's variables

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

No model field shall be interpolated horizontally for a comparison.
Observations shall be brought to the simulation's mesh and to the variables
Omega carries.

### Requirement: The first comparisons cover the main upper-ocean fields and the AMOC

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The analysis shall compare these with observational climatologies:

- temperature and salinity at the sea surface and at configured elevations;
- mixed-layer depth;
- sea surface height.

It shall compare the AMOC and the Ekman transport at 26.5°N with the RAPID
array. A field may have more than one reference.

### Requirement: Observations are prepared once and shared

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

No user shall need to download or process an observational dataset. Each
observational product shall be prepared once and shared by every analysis.
An analysis shall remap a product to its mesh once, however many date ranges
it analyzes.

### Requirement: The comparison work can run on any node

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The comparison work shall divide into independent pieces that task
parallelism can run on any node of an allocation. The results shall be the
same under `polaris serial`, under `polaris parallel` on one node, and under
`polaris parallel` across several.

### Requirement: Hosted products may be redistributed and name their source

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Polaris shall host only observational products whose licence permits
redistributing a processed derivative. Every product, and every plot made
from it, shall name its source dataset, version and period, and carry the
credit its licence asks for.

### Requirement: References are present-day climatologies

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Each comparison shall use a present-day observational climatology and state
its period. Matching the observations' period to a simulation's is deferred
to Phase 3 (D2).

### Requirement: Omega computes mixed-layer depth as it runs

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

*This requirement describes work in Omega.*

An Omega run shall compute the mixed-layer depth from its instantaneous state,
with the observational reference's criterion, and write its monthly mean. The
analysis shall not compute mixed-layer depth from monthly-mean profiles
(D10).

### Requirement: Observational uncertainty is kept

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Each product shall keep the uncertainty or sampling information its source
provides, so that a later display can show where a difference exceeds it.

## Algorithm Design

### Algorithm Design: Each comparison maps the model, the observations and their difference

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

For a field with simulated value $f^m_i$ and observed value $f^o_i$ on cell
$i$ of area $A_i$, the difference is $d_i = f^m_i - f^o_i$ on the set $V$ of
cells where both are valid. The metrics are

$$
\bar{d} = \frac{\sum_{i \in V} A_i \, d_i}{\sum_{i \in V} A_i},
\qquad
d_\mathrm{rms} =
\left( \frac{\sum_{i \in V} A_i \, d_i^2}{\sum_{i \in V} A_i} \right)^{1/2}.
$$

A cell is valid for the observations when at least a configured fraction of
its remapping weight falls on valid observations, 0.5 by default. A cell is
valid for the model at an elevation when Phase 1's elevation selection gives
it a value there ({ref}`design-ocean-analysis-initial`).

The observations' seasons are means of their monthly climatology weighted by
the days in each month, the weighting `ncclimo` gives the model's seasons.

Each comparison is one figure with three panels: model, observations and
difference. The first two share the field's colormap from its Phase 1 map
section. The difference has a diverging colormap from a section of its own.
The metrics appear in the figure and in its manifest entry. Each comparison
is a product with a `reference` facet. Under principle 4 of
{ref}`design-ocean-analysis`, the climatology map step loops over references
rather than having a step for each.

### Algorithm Design: The comparison is on the simulation's mesh, in the model's variables

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A comparison passes through four stages:

1. **Native product**, once per dataset and cached. The source is reduced to a
   monthly climatology on its own grid, converted to Omega's variables, and
   written with Polaris's variable names and CF metadata.
2. **Selection**, per analysis. The seasons to be plotted are formed on the
   product's grid. For three-dimensional fields, so are the configured
   elevations, by linear interpolation in $z$ between the product's levels,
   where $z$ is minus the product's depth.
3. **Remapping**, per analysis. The selected two-dimensional fields are
   remapped to the mesh, with bilinear weights for state fields and
   conservative weights for fluxes (D11), and renormalized by the valid
   fraction. Every Phase 2 product is a state field. Only what will be
   plotted is remapped (D12).
4. **Comparison**, per analysis, inside the climatology map step.

Conversions use TEOS-10 through `gsw`:

| Source variable | Becomes | Function | Also needs |
| --- | --- | --- | --- |
| In-situ temperature (WOA23) | conservative temperature | `CT_from_t(SA, t, p)` | absolute salinity, pressure from `p_from_z` |
| Practical salinity (WOA23, CCI SSS) | absolute salinity | `SA_from_SP(SP, p, lon, lat)` | location, pressure |
| Sea surface temperature (CCI SST) | conservative temperature | `CT_from_pt(SA, SST)` | a surface absolute salinity |

The WOA23 conversion is the one init's WOA23 product already makes.

The CCI SST product has no salinity. Its companion absolute salinity is
WOA23's at the surface for the same month, filled from the nearest valid
value where WOA23 has none. An error of 1 g kg⁻¹ in it changes conservative
temperature by at most 0.04 K at 28 °C, and by 0.004 K near freezing.

At the sea surface, conservative temperature is within 0.1 K of potential
temperature for open-ocean water. A surface map therefore reads as the
familiar sea surface temperature difference to within 0.1 K. In the deep
ocean, conservative temperature is below in-situ temperature by 0.15 K at
2000 m and 0.44 K at 5000 m. That conversion is needed whichever side is
converted (D1).

The model side is Phase 1's elevation selection. The `top` elevation is
compared with the surface products. The `bottom` and `k<index>` elevations
have no observational counterpart, so they are not compared and the step logs
that it skipped them.

### Algorithm Design: The first comparisons cover the main upper-ocean fields and the AMOC

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

**Temperature and salinity, WOA23** (D3). The product is the 1991–2020
normal, `decav91C0`, which NCEI provides at 0.25° and 1°. Monthly fields
cover 57 levels to 1500 m. Annual and seasonal fields cover 102 levels to
5500 m. Below 1500 m every season uses the annual field, as init's product
does for its month. WOA23's own seasons run January–March to
October–December, so they do not match the analysis's seasons. The
observation mask is kept, and nothing is extrapolated, unlike init's product.

**Sea surface temperature, ESA CCI SST v3.0** (D4). The product averages the
1991–2020 daily climatology at 0.05° into calendar months. A 0.25° copy is
made too (see the requirement that observations are prepared once).

**Sea surface salinity, ESA CCI SSS v5.5** (D5). The product averages the
monthly fields of 2010–2023 into a monthly climatology. Cells flagged for land
or sea-ice contamination are invalid. WOA23 at the surface is the second
reference. It is the better of the two in cold water and near coasts, where
satellite salinity is weakest.

**Mixed-layer depth, de Boyer Montégut et al. v2023** (D6). The field is
`mld_dr003`: the shallowest depth below 10 m where potential density exceeds
its value at 10 m by 0.03 kg m⁻³. It is computed for each profile and mapped
monthly on a 1° grid. Cells outside its `mask` are invalid, and its `n_obs`
is kept. There is no conversion.

**Sea surface height, DUACS DT2024** (D7). The product averages the monthly
absolute dynamic topography of 1993–2022 into a monthly climatology. Absolute
dynamic topography has an arbitrary global offset, and the global mean of the
model's sea surface height plays no part in this comparison. Each field
therefore has its area-weighted mean over $V$ removed, per season, before the
difference is taken. Corrections for atmospheric and sea-ice loading are open
question 2.

**AMOC and Ekman transport, RAPID v2024-2** (D8). The monthly AMOC and Ekman
series of {ref}`design-ocean-analysis-regional-moc` gain RAPID's mean as a
line and its mean plus or minus one standard deviation of annual means as a
band. A table gives the mean and the standard deviation of annual means for
the model and for RAPID. The model's years do not correspond to RAPID's, so
no series is compared month by month. No remapping is involved.

### Algorithm Design: Observations are prepared once and shared

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Products come in two layers, as WOA23 does for init:

- **Native products** are shared steps whose outputs are cached in the
  Polaris database. A user's setup downloads the product, not the source.
  A maintainer builds each product once per dataset version.
- **Remapped products** are shared steps in the analysis work directory. One
  analysis covers one simulation, so one mesh, and its mapping weights and
  remapped fields serve every date range. Each remapped file carries the
  identity of the mesh it was made for. A step that finds a different mesh
  recomputes it, under principle 7 of {ref}`design-ocean-analysis`.

A product made from a source finer than 0.25° also has a 0.25° copy. The
analysis uses the fine copy only when the mesh's finest cells are smaller
than a configured width, 25 km by default. Weights from 26 million 0.05°
source cells to a 240 km mesh cost much and gain nothing.

### Algorithm Design: The comparison work can run on any node

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The work falls into three kinds, each with its own unit:

| Work | Unit | Runs as |
| --- | --- | --- |
| Mapping weights | one product to the mesh | an MPI step |
| Remapping | one product and season, at every selected elevation | a piece of the product's remapping step |
| Comparison | one field, season, elevation and reference: a figure, its netCDF file and its metrics | a piece of the climatology map step |

A piece reads its inputs from files and writes its outputs to files. It is
given file names and option values, and it returns file names and metrics,
never arrays. Whether a remapping piece applies the weights itself or calls
`ncremap` is open question 7.

A piece repeats its own setup, such as opening the mesh and, for a
comparison, building the plotting descriptor. At high resolution that setup
may rival the work itself. These steps are where Phase C measures that cost
(D14). The measurement decides whether a field's elevations should be
batched into one piece, and what memory the steps declare.

### Algorithm Design: Hosted products may be redistributed and name their source

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Each product's global attributes give its source's name, version, DOI,
period, licence and citation, and the credit line its licence asks for. A
comparison's netCDF file and manifest entry copy them, and the gallery shows
the credit line with each comparison.

| Product | Licence | Source access |
| --- | --- | --- |
| WOA23 | US government work, public domain | HTTPS |
| ESA CCI SST v3.0 | CC-BY 4.0 | HTTPS from CEDA |
| ESA CCI SSS v5.5 | ESA CCI terms: any purpose, with acknowledgement | HTTPS from CEDA |
| de Boyer Montégut et al. v2023 | CC-BY 4.0 | HTTPS from SEANOE |
| DUACS DT2024 | Copernicus Marine licence, which allows distributing derivative work | free Copernicus Marine account |
| RAPID v2024-2 | Open Government Licence v3.0 | RAPID's request form |

Copernicus Marine asks for the line "Generated using E.U. Copernicus Marine
Service Information" with the product's DOI. Only the maintainer who builds a
product needs the account or the request form.

### Algorithm Design: Omega computes mixed-layer depth as it runs

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The criterion is the reference's, and the one
[Treguier et al. (2023)](https://doi.org/10.5194/gmd-16-3849-2023) recommend
for ocean model intercomparison:

1. Compute potential density referenced to the surface, from Omega's TEOS-10
   equation of state.
2. Take the reference density at 10 m below the sea surface, interpolated
   linearly between layer centres.
3. The mixed-layer depth is the shallowest depth below 10 m at which potential
   density exceeds the reference by 0.03 kg m⁻³, interpolated linearly
   between the layer centres that bracket it.
4. A column that never exceeds the threshold has the depth of its deepest
   valid layer centre.

Omega's Analysis module takes the monthly mean of the instantaneous value.

### Algorithm Design: Observational uncertainty is kept

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Native products keep these fields, month by month, as the source provides
them:

| Product | Fields |
| --- | --- |
| WOA23 | standard error of the mean (`_se`), number of observations (`_dd`) |
| ESA CCI SST v3.0 | `analysed_sst_uncertainty` |
| ESA CCI SSS v5.5 | `sss_random_error` |
| de Boyer Montégut et al. v2023 | `n_obs` |
| DUACS DT2024 | `err_sla` |

Remapping and displaying them is deferred.

## Implementation

### Implementation: Each comparison maps the model, the observations and their difference

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- The metrics are a component-neutral kernel in `polaris/analysis/`, taking a
  model field, an observed field, cell areas and validity.
- The three-panel figure is a plotting primitive in `polaris/viz/`, beside
  `plot_global_mpas_field()`.
- The climatology map step loops over each field's references, as principle 4
  of {ref}`design-ocean-analysis` asks. A field with no reference is mapped
  as in Phase 1.
- Each comparison's manifest entry has `reference` and `credit` facets.
  `Product` already takes arbitrary facets, so only the site templates change,
  to show the credit.

The config options sketched here go in `analysis.cfg`:

```cfg
[ocean_analysis_map_temperature]
# observational references at the sea surface (the "top" elevation); the
# first is the primary reference
surface_references = esa_cci_sst, woa23
# observational references at other elevations
references = woa23

[ocean_analysis_observations]
# the fraction of a cell's area that valid observations must cover
valid_fraction = 0.5
# use the fine copy of a product only on meshes whose finest cells are
# narrower than this, in km
fine_copy_below_km = 25.0
```

### Implementation: The comparison is on the simulation's mesh, in the model's variables

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- The conversion in init's WOA23 `CombineStep` moves to a shared leaf
  module, which init and the observational products both call.
- The mapping step is a `MappingFileStep` with `method='bilinear'`, as
  init's `LatLonMapStep` is, or `method='conserve'` for a flux product. The
  remapping step applies the weights with
  `ncremap` or with pyremap's `Remapper.remap_numpy()` (open question 7).
  Both take a renormalization threshold, which is `valid_fraction`.
- Selection of seasons and elevations on the product's grid reuses Phase 1's
  elevation helpers in `polaris/ocean/vertical/elevation.py` where they fit.

### Implementation: The first comparisons cover the main upper-ocean fields and the AMOC

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A new package, `polaris/tasks/ocean/observations/`, has one subpackage per
dataset: `woa23`, `esa_cci_sst`, `esa_cci_sss`, `dbm_mld`, `duacs_ssh` and
`rapid`. Each provides a `get_<dataset>_steps()` like `get_woa23_steps()`,
and a task that builds and plots its product, as the WOA23 hydrography task
does with `Woa23VizStep`.

- The WOA23 product declares the same raw files, under the same database
  names, as init's `CombineStep`, so the two share downloads.
- The DUACS and RAPID products read their raw files from a local path the
  maintainer sets in config. Only the processed product is uploaded.
- The AMOC comparison extends the AMOC series step of
  [polaris#995](https://github.com/E3SM-Project/polaris/pull/995), with the
  RAPID product as an input.

### Implementation: Observations are prepared once and shared

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- Native product steps set `default_cached = True`. Their work directories
  are `ocean/observations/<dataset>/<step>`, and their outputs are listed in
  `polaris/ocean/cached_files.json`.
- Remapped product steps are shared steps under
  `ocean/analysis/observations/<dataset>/`. Each stamps its output with the
  mesh's identity through the provenance-stamp helpers in
  `polaris/tasks/ocean/analysis/accumulate.py`: the mesh file, its cell
  count, and a checksum of its cell coordinates.

### Implementation: The comparison work can run on any node

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- Each comparison and each remapped season is a function at module scope,
  not a method, taking file names and option values. That is what handing
  out work requires ([polaris#892](https://github.com/E3SM-Project/polaris/pull/892)),
  and Phase 1's `ClimatologyMaps._plot_field()` becomes such a function.
- Until polaris#892 merges, `run()` calls these functions in a loop. Once it
  merges, the steps override `run_pieces()` and hand the same calls to
  `pieces.map()`, with no change to the functions.
- The steps follow
  [Task-Parallel-Safe Analysis Steps](task_parallel_analysis_steps.md) and
  declare `cores`, `min_cores` and, once measured, `memory`.

### Implementation: Hosted products may be redistributed and name their source

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A helper in the observations package writes the attribution attributes, and
every product step calls it. The table under the algorithm design becomes a
page of the User's Guide.

### Implementation: Omega computes mixed-layer depth as it runs

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- Omega's Analysis module gains the diagnostic, and the coupled configuration
  writes its monthly mean.
- `polaris/ocean/model/mpaso_to_omega.yaml` maps Omega's name to
  `mixedLayerDepth`.
- `analysis.cfg` loses `compute_mixed_layer_depth` and
  `mixed_layer_depth_threshold`, which no code reads.

### Implementation: order of work

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

In dependency order:

1. The shared conversion module and the comparison metrics.
2. The remapping steps and the comparison in the climatology map step, with
   WOA23, which needs no new download.
3. The CCI SST and CCI SSS products.
4. The DUACS product, once open question 2 is settled.
5. RAPID on the AMOC series, after polaris#995 and Omega's line transport.
6. The mixed-layer depth product, and its comparison once Omega's diagnostic
   exists.

## Decisions

Alternatives considered and set aside, cited from the sections they affect.

### D1: The comparison is in Omega's variables

Xylar, 2026/11/26. Observations are converted to conservative temperature
and absolute salinity, and the model is left as Omega wrote it.

For:

- The simulated field in a comparison is exactly the one Omega wrote and
  Phase 1's maps show.
- The conversion is made once per dataset, in the cached product, rather than
  in every analysis.
- It is init's conversion, so a run initialized from WOA23 starts close to
  zero difference from it. That makes a test (see Testing).
- Omega's developers reason in conservative temperature and absolute
  salinity.

Against:

- A product without salinity needs a companion field. The cost is at most
  0.04 K per g kg⁻¹ of error in it.
- Surface maps are in conservative temperature, up to 0.1 K from the
  potential temperature of published SST differences.
- The hosted product is derived from the source, not the source's own
  variable.

Set aside: converting the model to each product's variables. That needs no
companion field, and the maps would follow published conventions. But the
model would be converted differently for each product, in every analysis,
and the same simulated field would appear in different variables on
different pages.

### D2: Present-day references, with period matching in Phase 3

Xylar, 2026/11/26. The period of Omega's first coupled runs is not yet known.

Set aside: an early-period SST, such as HadISST1 over 1870–1900, for
pre-industrial runs. Observations from that period are sparse. Long records
such as HadISST1 and EN4 belong with period matching.

### D3: WOA23 for temperature and salinity

Xylar, 2026/11/26: datasets are chosen on merit, not for comparability with
MPAS-Analysis. WOA23 covers the full depth, is monthly to 1500 m, has
standard errors and is public domain. It is the CMIP7 Rapid Evaluation
Framework's reference for surface temperature and salinity, and it shares
its download with init.

Set aside:

- EN4, at 1° under a non-commercial licence. Its monthly series from 1900 is
  the candidate for period matching.
- IAPv4, whose licence is listed inconsistently.
- Roemmich-Gilson Argo, which states no licence and stops at 2000 dbar.
- MIMOC, whose licence is non-commercial.
- ISAS20, which is Argo-only for 2002–2020.
- WAGHC, an isopycnal average over 1985–2016, which is a candidate second
  reference.

### D4: ESA CCI SST v3.0 for sea surface temperature

Its 0.05° grid resolves fronts on eddy-resolving meshes. It has per-pixel
uncertainty and comes from satellites alone, so it is independent of WOA23.
It is CC-BY 4.0, downloads without a login, and has a ready 1991–2020
climatology.

Set aside:

- OISST v2.1, whose effective resolution is coarser than its 0.25° grid. Its
  44 MB monthly mean would make a cheap extra reference.
- HadISST1, at 1° with no uncertainty, which the Met Office plans to replace
  in 2026.
- ERSSTv6, at 2°.
- The Hadley-NOAA/OI merged product that MPAS-Analysis uses, chosen there
  for comparability with other models.

### D5: ESA CCI SSS v5.5 for sea surface salinity

It merges SMOS, Aquarius and SMAP over 2010–2023 at 50 km resolution, with
uncertainty and contamination flags, under a licence that allows any use.

Set aside:

- SMAP from RSS, v6, whose terms say nothing about redistribution and whose
  files need a login.
- SMAP from JPL, which starts in 2015 and needs an Earthdata login.
- Aquarius V5, which covers only 2011–2015.
- WOA23 alone, which is smoothed. It stays as the second reference.

### D6: de Boyer Montégut et al. v2023 for mixed-layer depth

It has the most profiles, 7.3 million from Argo and the World Ocean Database
over 1970–2021. It uses the criterion recommended for ocean model
intercomparison, and it is CC-BY 4.0.

Set aside:

- Holte et al.'s Argo climatology. It is "All Rights Reserved", has not been
  updated since 2022, and leaves 1° bins unfilled. It does have the monthly
  maximum this reference lacks (open question 5).
- GOSML, which uses an algorithm-based depth and a non-commercial licence.

### D7: DUACS DT2024 for sea surface height

It is at 0.125°, covers 1993 to the present, has an error field, and its
licence allows distributing derivative work.

Set aside:

- The CNES-CLS22 mean dynamic topography alone. It is one mean over
  1993–2012 with no seasons, and DUACS's absolute dynamic topography is built
  on it.
- The obs4MIPs AVISO sea surface height, at 1° over 1993–2010.

### D8: RAPID v2024-2 for the AMOC

It is the reference array at 26.5°N, under the Open Government Licence.

Set aside:

- The Rapid Evaluation Framework's obs4REF copy, RAPID-2023-1a. It needs no
  request form, but it ends in February 2023.
- MOVE, SAMBA and OSNAP, which can come later. OSNAP's overturning is in
  density space.

### D9: Maintainers build the products, and users download them from Polaris

Set aside: each user downloading from the sources. Two sources need an
account or a request form. The downloads are large, 14 GB for the SST
climatology and 11.6 GB for WOA23 temperature at 0.25°. Every user would
repeat the processing.

### D10: Mixed-layer depth comes only from Omega

Xylar, 2026/11/26. Phase 1 shipped no mixed-layer depth. Treguier et al.
(2023) found that mixed-layer depth computed from monthly-mean rather than
daily fields has a rectified bias that exceeds 100 m in places. They
recommend computing it as the model runs, with this criterion.

Set aside: the offline computation from monthly means designed in
{ref}`design-ocean-analysis-initial`, which was never built.

### D11: Bilinear weights for state fields, conservative weights for fluxes

Proposed, 2026/11/26. Xylar's preference, not yet settled (open question 1).
The best weights depend on both the source and the mesh. Conservative weights
are costly and poor from a coarse source to a fine mesh, and noisy from a
fine source to a fine mesh. They do better from a fine source to a coarse
mesh, but coarse meshes are the analysis's lowest priority, since they are
the least scientifically valid. A flux needs its area integral preserved,
which only conservative weights do.

Set aside: conservative weights for every product, which keep area means on
every mesh at the costs above.

### D12: Seasons and elevations are selected before remapping

Proposed, 2026/11/26. Remapping only the plotted slices keeps the remapped
products small on any mesh.

Set aside: remapping the full three-dimensional product and selecting on the
mesh. For WOA23 on a 6 km mesh, that is tens of gigabytes per analysis.

### D13: Remapped products belong to an analysis, not to the database

Proposed, 2026/11/26. The mesh comes from the simulation, so a database key
by mesh name could match a different mesh of the same name.

Set aside, for now: caching products remapped to released E3SM meshes in the
database. See open question 4.

### D14: Comparisons and remapped seasons are pieces of a step, not steps

Proposed, 2026/11/26. Phase C of task parallelism (polaris#892) runs a
step's pieces on any node, so a loop inside a step no longer confines its
work to one node. The comparisons are many short, independent items of the
size analysis work has, which is the workload Phase C was designed for and
has not yet measured.

Set aside: a step for each comparison. Fields, seasons, elevations and
references multiply, and principles 4 and 9 of {ref}`design-ocean-analysis`
keep that product off the step axis.

## Testing

### Testing and Validation: Each comparison maps the model, the observations and their difference

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Unit tests check the metrics on synthetic fields with analytic answers,
including partial validity and unequal cell areas. A smoke test draws the
three-panel figure.

### Testing and Validation: The comparison is on the simulation's mesh, in the model's variables

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- Unit tests check each conversion against `gsw` check values, and check
  that the companion salinity's effect stays within the stated bound.
- A constant field with a partial mask stays constant through remapping with
  renormalization, with either kind of weights.
- Bilinear weights reproduce a linear field away from masks, and
  conservative weights preserve the area-weighted mean on a test mesh.
- End to end: a low-resolution Omega run initialized from WOA23 has small
  temperature and salinity differences from WOA23 at −500 m and −2000 m in
  its first year. Init remaps the same source with the same bilinear weights,
  so what remains is mostly the first year's drift.

### Testing and Validation: The first comparisons cover the main upper-ocean fields and the AMOC

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Each product's task plots the product on its own grid, as `Woa23VizStep` does.
The analysis of a one-year `e3sm-qu240` run from the `analysis_output` task
produces every comparison. Known bias patterns in E3SM coupled runs are
judged by eye at higher resolution, which is a science check rather than an
automated test.

### Testing and Validation: Observations are prepared once and shared

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- A setup against an empty local database downloads products, not sources,
  as its log shows.
- A second date range reuses the remapped products, as its log reports.
- Pointing the work directory at a run on another mesh recomputes them.

### Testing and Validation: The comparison work can run on any node

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

- The comparison of one run writes identical netCDF files and metrics under
  `polaris serial`, under `polaris parallel` on one node, and across two
  nodes.
- The comparison of a high-resolution Omega run is the analysis workload for
  Phase C's validation, which runs it three ways (polaris#892).
- Each piece's setup time and peak memory are recorded, to size pieces and
  set the steps' `memory`.
- Remapping a product's seasons is timed with `ncremap` and with
  `remap_numpy()`, under `polaris serial` and handed out as pieces, to settle
  open question 7.

### Testing and Validation: Hosted products may be redistributed and name their source

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A unit test checks that every product step writes the attribution attributes.
The gallery is checked by eye for the credit lines.

### Testing and Validation: References are present-day climatologies

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

A unit test checks that each comparison's title and attributes state the
observations' period.

### Testing and Validation: Omega computes mixed-layer depth as it runs

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

Omega tests the diagnostic on columns with analytic answers. Polaris checks
that the monthly mean is read and compared, end to end on a low-resolution
run.

### Testing and Validation: Observational uncertainty is kept

Date last modified: 2026/11/26

Contributors: Xylar Asay-Davis, Claude

The products' CF checks cover the uncertainty fields.
