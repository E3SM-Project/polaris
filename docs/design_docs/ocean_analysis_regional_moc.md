(design-ocean-analysis-regional-moc)=

# Regional Overturning Circulation

Creation date: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

## Summary

This design adds the overturning streamfunction of named ocean basins to the
Polaris ocean analysis of Omega simulations. The basin that matters most is
the Atlantic. From its streamfunction, Polaris derives the standard measure
of the Atlantic meridional overturning circulation (AMOC): the maximum of the
streamfunction at 26.5°N, the latitude of the RAPID array, as a monthly time
series. Regional overturning is one of the products the umbrella design
defers from Phase 1 ({ref}`design-ocean-analysis`).

Polaris computes the streamfunction itself, from the transport across each
mesh edge that Omega's monthly means give (D1). It uses the overturning
computation of the MISOMIP analysis ([polaris#939](https://github.com/E3SM-Project/polaris/pull/939)),
which reads the same kind of transport from MPAS-Ocean. One computation then
serves both: MISOMIP's overturning on MPAS-Ocean and the MOC on Omega. Basin
masks come from Polaris's feature masks
([polaris#592](https://github.com/E3SM-Project/polaris/pull/592)).

The method sums the transport across a latitude line between cells of the
basin. Its challenges are:

- **No southern transect.** The transport across each latitude is measured
  directly, so a basin needs only its cell mask. This holds whatever other
  openings the basin has.
- **Layers that tilt.** Each edge's transport is integrated to fixed
  elevations with that edge's own layer interfaces. The streamfunction is
  then correct under ice shelves and on vertical coordinates other than
  z-star.
- **An exact time mean.** With mass-weighted time means
  ([Omega#687](https://github.com/E3SM-Project/Omega/issues/687)), Omega's
  monthly-mean velocity times its monthly-mean layer thickness is the mean
  transport. It carries the correlation of velocity and thickness, which a
  product of plain means misses.

Omega needs no change of its own beyond Omega#687. Its monthly output already
holds the velocity, the layer thickness and the layer interfaces, in
standalone and coupled runs. Omega therefore gains no region dimension, and
nothing here stands in the way of the expression language proposed for E3SM
diagnostics (*Composable runtime diagnostics for the Energy Exascale Earth
System Model*, Mahfouz et al., in preparation).

Success is an Atlantic streamfunction and an AMOC time series from a
low-resolution Omega run, with the sign and magnitude MPAS-Analysis reports
for comparable E3SM runs.

## Requirements

### Requirement: Polaris computes the overturning streamfunction of named basins

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

For an Omega simulation, Polaris shall compute the climatological meridional
overturning streamfunction of each requested basin as a function of latitude
and elevation. The global ocean is one such basin.

### Requirement: Basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The basins shall come from geometric data and configuration. Neither Omega
nor Polaris code shall name a basin, fix the number of basins or name the
dimension they are stored along.

### Requirement: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The streamfunction shall be correct where layers tilt, such as under ice
shelves, and on vertical coordinates other than z-star. Its time mean shall
not depend on how velocity and layer thickness vary together within the
averaging period.

### Requirement: Overturning has one computation in Polaris

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The MOC on Omega and the MISOMIP overturning on MPAS-Ocean shall come from
the same computation, given each model's transport and layer interfaces.

### Requirement: The MOC analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

On the largest E3SM ocean meshes, the cost of the MOC analysis shall be
dominated by reading the monthly means it needs, each read once per
simulation.

### Requirement: Coupled runs write what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

An E3SM run with Omega shall write the monthly output the MOC analysis
needs. No mask file shall need to be staged for the run.

### Requirement: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The analysis shall plot the climatological streamfunction of every requested
basin, the global ocean among them. Each plot covers its basin's latitudes.
Every value is plotted and written at the latitude it represents.

### Requirement: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

The analysis shall produce a monthly time series of the maximum over
elevation of the Atlantic streamfunction at 26.5°N, with the data behind it.
The latitude and the basin shall be config options.

## Algorithm Design

### Algorithm Design: Polaris computes the overturning streamfunction of named basins

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Edge $e$ joins cells $c_1(e)$ and $c_2(e)$, and its normal velocity is
positive from $c_1$ to $c_2$. Cell $c$ has latitude $\phi(c)$. Basin $r$ is
the set of cells with $m_r(c) = 1$. For the global ocean, $m = 1$ in every
cell.

The edges across latitude $\phi$ in basin $r$ are those with both cells in
the basin, on opposite sides of $\phi$:

$$
E_r(\phi) = \{e : m_r(c_1) = m_r(c_2) = 1,\ \phi \text{ lies between }
\phi(c_1) \text{ and } \phi(c_2)\},
$$

with $\phi(c) < \phi$ on one side and $\phi(c) \ge \phi$ on the other. The
sign $s_e$ is $+1$ where $\phi(c_1) < \phi(c_2)$ and $-1$ otherwise, so
$s_e u > 0$ for northward flow. The northward transport of layer $k$ across
edge $e$ is

$$
T(e, k) = s_e\, \hat{u}(e, k)\, \overline{\tilde{h}}(e, k)\, \Delta v(e),
$$

where $\hat{u}$ is the monthly mean of the normal transport velocity,
weighted by pseudo-thickness, and $\overline{\tilde{h}}$ is the mean of the
two cells' monthly-mean pseudo-thickness. $\Delta v$ is the edge length.
Each edge's layer $k$ spans $z_{bot}(e, k)$ to $z_{top}(e, k)$, the mean of
its two cells' monthly-mean layer interfaces. The streamfunction at
elevation $z$ is

$$
\Psi_r(\phi, z) = -\sum_{e \in E_r(\phi)} \sum_k T(e, k)\, f_{e,k}(z),
\qquad
f_{e,k}(z) = \min\left(1, \max\left(0,
\frac{z - z_{bot}(e, k)}{z_{top}(e, k) - z_{bot}(e, k)}\right)\right).
$$

This is the core MISOMIP uses, minus sign included, with lines of constant
$x$ in place of latitudes. Elevations above or below all the
water on the edges of $E_r(\phi)$ are not ocean and are masked.

> **Rationale.** The edges of $E_r(\phi)$ separate the basin's cells south of
> $\phi$ from those north of it, so their sum is the northward transport
> across $\phi$ within the basin. The factor $f$ counts each layer below $z$
> in full and the layer $z$ falls in by the fraction of its height below $z$.
> The minus sign makes $\Psi$ minus the northward transport below $z$, so
> the transport per unit height is $-\partial \Psi / \partial z$. That is
> the MISOMIP protocol's definition (Asay-Davis et al., 2016) and the
> convention of Omega's in-situ MOC and of MPAS-Analysis. A positive AMOC
> means northward flow above its maximum. By the discrete
> divergence theorem, the sum also equals the vertical flux through $z$ over
> the basin's cells south of $\phi$. Each interior edge's integral to $z$ is
> shared by its two cells with opposite signs, so it cancels however much the
> layers tilt. The two approximations are that each edge's flux is spread
> evenly over its layer and that the interfaces are monthly means.

### Algorithm Design: Basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Polaris computes the `MOC Basins` cell masks of `geometric_features` on the
simulation's mesh, as polaris#592 does for a mesh it builds. A basin is
requested by the name `geometric_features` gives it, without the `_MOC`
suffix: `Atlantic`, `AtlanticMed`, `IndoPacific`, `Pacific` or `Indian`.
`Global` needs no mask. The mask's region dimension is whichever dimension of
the mask field is not the cell dimension.

### Algorithm Design: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Omega's continuity equation moves pseudo-thickness with the flux
$\tilde{h}_e u$, where $\tilde{h}_e$ is the edge pseudo-thickness and $u$ the
normal transport velocity. Under Omega#687, $\hat{u}$ is
$\overline{\tilde{h}_e u} / \overline{\tilde{h}_e}$. With the default
`FluxThicknessType: Center`, $\tilde{h}_e$ is the mean of the two cells, so
$\hat{u}\,\overline{\tilde{h}}$ is the mean flux exactly. With `Upwind` it is
exact only if Omega#687 weights edge means by the upwind thickness, which is
one of that issue's open questions. Since $\tilde{h}$ is a mass per unit area
divided by $\rho_0$, $\Psi$ is a mass transport divided by $\rho_0$ (D6).

The normal transport velocity is the normal velocity plus any eddy-induced
velocity. A run that turns on an eddy-induced velocity also needs that
velocity's monthly mean in its output.

The latitude lines and the elevations are uniform and shared by every basin
(D4). The lines are every $\Delta\phi$ from $\phi_{min}$ to $\phi_{max}$. The
elevations are every $\Delta z$ from the highest sea surface, rounded up, to
the deepest sea floor, rounded down, as in the MISOMIP analysis.

> **Rationale.** Two other methods are set aside (D2). Interpolating each
> column's vertical velocity to fixed $z$ is wrong where layers tilt, since
> flux between two columns leaves one and enters the other at different
> depths. Summing each layer first and giving the sum one mean depth squeezes
> the streamfunction into the line's mean column.

### Algorithm Design: The MOC analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

For each edge, the sum over $k$ in $\Psi$ is the edge's running transport
from the sea floor, interpolated linearly to $z$ between the edge's
interfaces. The running sum is known at the interfaces, and it is linear
within each layer because the flux is spread evenly over it. Computed that
way, an edge costs its layers plus the elevations, not their product.

> **Rationale.** The core as MISOMIP has it forms $f_{e,k}(z)$ for every edge,
> layer and elevation at once. That suits a few lines on a planar mesh. On a
> large global mesh, one line can cross tens of thousands of edges. With 80
> layers and 120 elevations, the array is over a gigabyte per line, and each
> month has hundreds of lines per basin.

### Algorithm Design: Coupled runs write what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The coupled configuration of Omega's `MonthlyAverages` group already writes
the normal velocity, the pseudo-thickness and the layer interfaces. With
Omega#687, those means are weighted, and they are all the analysis needs.
Polaris computes the masks from the run's mesh, so nothing is staged.

### Algorithm Design: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The climatology $\overline{\Psi}_r$ is the mean of the monthly $\Psi_r$ over
the years, weighted by the days in each month. It is plotted at the lines
$\phi_j$. Each basin's plot covers a configured latitude range. The default
for the three standard basins is 35°S to 70°N, as in MPAS-Analysis. The
global plot covers all latitudes.

> **Rationale.** Each month's $\Psi_r$ uses that month's interfaces. A
> streamfunction of climatological means would use climatological
> interfaces, and a product of separate climatologies of $\hat{u}$ and
> $\overline{\tilde{h}}$ would miss their correlation across months.

The Phase 1 step plots Omega's in-situ global streamfunction at bin centers,
half a bin south of where each value belongs
([polaris#926](https://github.com/E3SM-Project/polaris/issues/926)). The
global plot now comes from the same computation as the basins (D3), so this
step is replaced, which fixes the shift.

### Algorithm Design: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

For each month $t$ of monthly-mean output,

$$
\mathrm{AMOC}(t) = \max_z \Psi_A(\phi_R, z, t),
$$

where $\phi_R = 26.5$°N is a latitude line of its own and $A$ is the
`Atlantic` basin. The maximum is over the whole column.

> **Rationale.** MPAS-Analysis takes the bin edge nearest 26.5°N. A line at
> exactly $\phi_R$ needs neither that nor interpolation between lines. The
> maximum over the whole column of a monthly mean is what MPAS-Analysis
> computes, so the two can be compared.

## Implementation

### Implementation: Overturning has one computation in Polaris

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

`polaris/ocean/overturning.py` comes from polaris#939. Its core,
`compute_overturning_from_edge_transport()`, takes a transport, the edges'
interface elevations and the target elevations. It reads no model's field
names. This design adds:

- `get_latitude_edges()`: the edges of $E_r(\phi)$ for a cell mask and a
  latitude. It returns the same dataset as `get_line_edges()`, with the sign
  toward increasing latitude.
- A way to get the edges' interfaces from cell interfaces that the model
  writes. `compute_line_interfaces()` stacks them from SSH and layer
  thickness, as MPAS-Ocean output needs. Omega writes `GeomZInterface`, which
  only needs interpolating to the edges.

The Omega names belong to the MOC steps, and the MPAS-Ocean names to
MISOMIP.

### Implementation: Basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A shared step runs polaris#592's `ComputeOceanFeatureMasksStep` for the
  `MOC Basins` group on `SimFiles.mesh_filename()`. Its southern transects
  are written but not read.
- `[ocean_analysis_moc] regions` lists the basins, by default
  `Global, Atlantic, AtlanticMed, IndoPacific` (D5).

### Implementation: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- The MOC steps read `NormalTransportVelocity`, `PseudoThickness` and
  `GeomZInterface` from the monthly means, each with the `_TimeMean1Month`
  suffix. Where the file has no `NormalTransportVelocity`, they read
  `NormalVelocity`, which is the same field when no eddy-induced velocity is
  on.
- A simulation whose monthly means are not weighted by pseudo-thickness is
  reported and its MOC skipped, as a missing streamfunction is today. The
  steps tell the two apart by the weighting Omega#687 records in each
  field's `cell_methods`.
- `[ocean_analysis_moc]` holds `dlat = 0.5`, `min_lat = -90` and
  `max_lat = 90` for the lines, and `dz = 50` (m) for the elevations.

### Implementation: The MOC analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- `compute_overturning_from_edge_transport()` gains the running-sum form
  above, which MISOMIP then also uses.
- `MocSeries` finds the edges of every line and basin once, from the mesh and
  masks. Each month it reads only those edges and the cells they join.
- `MocSeries` computes months in parallel across its cores. Each month is
  independent until the months are combined.
- The `Accumulator` cache means each month is read once per simulation,
  whatever ranges later analyses cover.

### Implementation: Coupled runs write what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

[Omega#663](https://github.com/E3SM-Project/Omega/pull/663) set Omega's
default analysis for coupled runs, with the three fields above in
`MonthlyAverages`. Nothing more is needed once Omega#687 is in, unless a
coupled configuration turns on an eddy-induced velocity. That configuration
adds `NormalTransportVelocity` to `MonthlyAverages`.

### Implementation: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A new step, `MocSeries`, is an `Accumulator`. Each month it computes
  $\Psi_r$ for every configured basin and writes it to its cache. It depends
  on the mask step. Its lines include $\phi_R$, so the AMOC needs no pass of
  its own over the monthly means.
- The `Moc` step depends on the `MocSeries` step for its year range. It
  writes `<region>.png`, `<region>.nc` and one gallery for each basin. It no
  longer runs `ncclimo` or reads Omega's MOC files. Omega's `MOC` group is
  unchanged.
- Each basin's plot range comes from `[ocean_analysis_moc_<region>]`, with
  `min_lat` and `max_lat`. The section name is the basin name in lower case
  with underscores, as for `[ocean_analysis_map_<field>]`. Defaults are given
  for `atlantic`, `atlantic_med` and `indo_pacific`.

### Implementation: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

A new task, `ocean/analysis/amoc_time_series`, takes its years from
`[ocean_analysis_time_series]` and joins the `omega_analysis` suite. Its step
reads $\Psi_A(\phi_R, z, t)$ from the `MocSeries` step for its year range and
takes the maximum over $z$. It writes `amoc.nc`, holding the series and the
latitude used, and plots the series. A new section, `[ocean_analysis_amoc]`,
holds `region = Atlantic` and `latitude = 26.5`.

### Implementation: order of work

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

In dependency order:

1. Polaris: the overturning core, with polaris#939.
2. Polaris: `get_latitude_edges()` and edge interfaces from cell interfaces.
   Items 1 and 2 need nothing from Omega.
3. Omega: mass-weighted time means, Omega#687.
4. Polaris: the mask step and the `Moc` step for every basin, which fixes
   polaris#926. This needs item 3 in the Omega submodule.
5. Polaris: the AMOC time series.
6. Polaris: time `MocSeries` on a year of output from a large mesh. The result
   says how soon Omega's in-situ version (D7) is needed.

## Decisions

Alternatives considered and set aside, cited from the sections they affect.

### D1: Polaris computes the streamfunction from Omega's output

Xylar, 2026/11/08. Polaris computes the transport from Omega's mass-weighted
monthly means (Omega#687). It computes every basin's streamfunction with the
overturning core it shares with MISOMIP.

Set aside: computing the regional streamfunction in Omega, as an earlier
draft of this design did. That draft read basin masks and southern transects
into Omega through reworked dynamic input streams
([Omega#422](https://github.com/E3SM-Project/Omega/pull/422)). It needed a
new `Select` operator, changes to the `MOC` group and its operator parser,
and mask files staged for coupled runs. It also kept a sign error in the
southern-boundary term
([Omega#672](https://github.com/E3SM-Project/Omega/issues/672)). The
algorithm would have existed in both Omega and Polaris. An in-situ version
of this design's method is deferred rather than set aside (D7).

### D2: Transport across latitude lines, at fixed elevations

Xylar, 2026/11/08. This is the method chosen for the MISOMIP overturning.

Set aside: summing vertical fluxes over a basin's cells in latitude bins,
seeded with the transport through a southern transect, as Omega's in-situ
MOC and MPAS-Analysis do. It needs a transect per basin. It is wrong north
of any other opening the basin has, such as Gibraltar for the Atlantic
without the Mediterranean, or the Indonesian Throughflow for the Pacific and
Indian basins. Its depth axis is a horizontal mean of the layer interfaces.
Also set aside: interpolating each column's vertical velocity to fixed $z$,
which is wrong where layers tilt.

### D3: The global streamfunction uses the same computation

Proposed, 2026/11/08. Every basin, global included, has the same method and
elevations, so the plots compare directly.

Set aside: plotting Omega's in-situ global streamfunction, with polaris#926
fixed. Its vertical axis is the horizontal mean of the layer interfaces, and
its method differs from the basins'.

### D4: Latitude lines and elevations are uniform and shared by every basin

Proposed, 2026/11/08. Lines every 0.5° and elevations every 50 m by default.

Set aside: lines or elevations per basin, and the simulation's reference
layer interfaces as the elevations. Neither is needed for plots cropped to
each basin. Shared elevations also keep the global and basin plots on one
axis.

### D5: The default basins are Atlantic, AtlanticMed and IndoPacific

Xylar, 2026/11/02. These are the basins MPAS-Analysis plots, alongside the
global ocean.

Set aside: the Atlantic alone. It is enough for the AMOC time series, but not
for the basin plots that would be compared with MPAS-Analysis.

### D6: The streamfunction is a mass transport divided by $\rho_0$

Xylar, 2026/11/08. The transport is the pseudo-thickness flux that Omega's
continuity equation uses, rebuilt from mass-weighted means.

Set aside: a volume transport, from a monthly mean of the geometric thickness
flux. Omega would write one more field the size of `NormalVelocity` for it.
The two differ by the ratio of density to $\rho_0$, a few percent.

### D7: Omega's in-situ version of the method is deferred

Xylar, 2026/11/08. Omega will compute the same $\Psi_r$ in situ for the
largest meshes, likely soon after Polaris's version works. Polaris's version
stays the reference. The `Moc` and AMOC steps will read Omega's output when a
simulation wrote it, and compute their own otherwise. Comparing the two on
one run then tests Omega's version.

The in-situ version needs:

- the basin masks in Omega, with the dynamic input streams and `Select`
  operator of the earlier draft (D1);
- general operators for edge interfaces, the running transport at fixed
  elevations, and a sum over the edges crossing each line;
- a reproducible global sum of lines × elevations × basins each sampled
  step.

It needs no southern transects. It uses each step's own interfaces, so it is
more accurate than Polaris's version, and it does not depend on Omega#687. It
is a natural thing to build through the expression language when that is
ready.

Set aside for now: building both versions at once. Polaris's version is
needed for MISOMIP anyway, and it covers the meshes most analysis runs on.

## Testing

### Testing and Validation: Polaris computes the overturning streamfunction of named basins

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- **Comparison with Omega's in-situ MOC.** On the coarsest mesh of
  `ocean/realistic_global/analysis_output`, the global streamfunction is
  compared with Omega's `MOC_streamfunction_Global`, which that task still
  writes. The comparison uses lines at Omega's bin boundaries and Omega's
  values interpolated to the same elevations. Omega's is a volume transport,
  so the two also differ by the ratio of density to $\rho_0$ (D6). The
  difference is reported rather than tested against a tolerance.
- **Basins that tile.** Where AtlanticMed and IndoPacific hold every ocean
  edge across a latitude line, their streamfunctions sum to the global one
  there to round-off.

### Testing and Validation: Basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

A unit test on a small synthetic mask dataset checks that basins are found by
name, whatever the region dimension is called.

### Testing and Validation: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A unit test of `get_latitude_edges()` on a synthetic mesh checks that only
  edges with both cells in the basin are kept and that every sign points
  north.
- A unit test with tilted layers and a known transport checks $\Psi$ at
  fixed elevations.
- A unit test checks that unweighted monthly means are reported and the MOC
  skipped.
- Once Omega#687 is in, `analysis_output` checks on its output that the
  transport from the weighted means matches the monthly mean of
  $\tilde{h}_e u$, written there as a check.

### Testing and Validation: Overturning has one computation in Polaris

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The MISOMIP tests from polaris#939 keep passing. They exercise the shared
core.

### Testing and Validation: The MOC analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A unit test checks that the running-sum form matches the form with
  $f_{e,k}(z)$ on random layers and transports.
- `MocSeries` is timed on a year of output from a large mesh, with the time
  spent reading reported separately. The timing is reported, not tested
  against a limit.

### Testing and Validation: Coupled runs write what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

A short coupled run on oQU240 writes weighted monthly means, and the MOC
analysis runs on its output.

### Testing and Validation: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

A unit test checks that a basin with no ocean edges across a line gives a
masked column there rather than an error.

### Testing and Validation: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A unit test builds a synthetic transport with a known maximum and checks
  the series.
- The series from an Omega run is compared by eye with MPAS-Analysis's for an
  MPAS-Ocean run on the same mesh. As in the umbrella design, this is a check
  of sign and magnitude made by a scientist, not an automated test.
