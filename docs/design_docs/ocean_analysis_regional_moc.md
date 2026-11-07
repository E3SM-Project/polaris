(design-ocean-analysis-regional-moc)=

# Regional Overturning Circulation

Creation date: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

## Summary

This design adds the overturning streamfunction across configured lines to
Omega's in-situ analysis, and the overturning of named ocean basins to the
Polaris ocean analysis of Omega simulations. The line that matters most is
26.5°N across the Atlantic, the latitude of the RAPID array. Its maximum over
elevation, as a monthly time series, is the standard measure of the Atlantic
meridional overturning circulation (AMOC). Regional overturning is one of the
products the umbrella design defers from Phase 1
({ref}`design-ocean-analysis`).

Every streamfunction here has one definition: the transport across a line,
summed over the mesh edges between the cells on either side and integrated
to fixed elevations with each edge's own layer interfaces (D1, D2). The
MISOMIP analysis uses the same definition on MPAS-Ocean
([polaris#939](https://github.com/E3SM-Project/polaris/pull/939)). It needs
no southern transect, and it holds where layers tilt.

The work comes in two stages (D7):

- **Lines in Omega, now.** Omega computes the streamfunction across lines
  given in its YAML configuration, each a latitude and a longitude range
  (D8). RAPID is 26.5°N from 100°W to 0°. Global lines span all longitudes.
  Neither needs an input file, so every Omega run on any mesh can produce the
  AMOC and the global streamfunction.
- **Basins in Omega, later.** Basin streamfunctions need basin masks read
  into Omega. Until then, Polaris computes them offline from Omega's monthly
  means, with basin masks from its feature masks
  ([polaris#592](https://github.com/E3SM-Project/polaris/pull/592)).

Polaris's offline computation is also the reference that tests Omega's (D9).
Nothing here adds a region dimension to Omega. Every new Omega operator is a
general operation that the expression language proposed for E3SM diagnostics
(*Composable runtime diagnostics for the Energy Exascale Earth System Model*,
Mahfouz et al., in preparation) could name.

Success is an AMOC time series and a global streamfunction computed in situ
on a low-resolution Omega run, matching Polaris's offline computation from
the same run. The AMOC should have the sign and magnitude MPAS-Analysis
reports for comparable E3SM runs.

## Requirements

### Requirement: The analysis produces the overturning of the global ocean and named basins

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

For an Omega simulation, the analysis shall produce the climatological
meridional overturning streamfunction of the global ocean and of each
requested basin, as a function of latitude and elevation.

### Requirement: Omega computes the AMOC as it runs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

An Omega run shall compute the overturning streamfunction across the RAPID
line as it runs, on any mesh, with no input files beyond those it already
reads. The AMOC time series shall need no pass over three-dimensional
output.

### Requirement: Lines and basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Lines shall come from configuration, and basins from geometric data and
configuration. No code shall name a line or a basin, fix how many there are,
or add a region dimension.

### Requirement: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The streamfunction shall be correct where layers tilt, such as under ice
shelves, and on vertical coordinates other than z-star. Its time mean shall
not depend on how velocity and layer thickness vary together within the
averaging period.

### Requirement: Overturning has one definition

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Omega's in-situ streamfunction, Polaris's offline one and the MISOMIP
overturning shall follow the same definition. Polaris's two uses shall share
one computation.

### Requirement: The analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Products the analysis needs routinely shall come from in-situ output. Where
the analysis reads three-dimensional monthly means, its cost shall be
dominated by that reading, with each month read once per simulation.

### Requirement: Coupled runs compute what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

An E3SM run with Omega shall compute the AMOC and the global streamfunction
in situ by default. No mask file shall need to be staged for that.

### Requirement: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The analysis shall plot the climatological streamfunction of the global
ocean and of every requested basin. Each plot covers its basin's latitudes.
Every value is plotted and written at the latitude it represents.

### Requirement: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The analysis shall produce a monthly time series of the maximum over
elevation of the streamfunction across the RAPID line, with the data behind
it. The line shall be a config option.

## Algorithm Design

### Algorithm Design: The analysis produces the overturning of the global ocean and named basins

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Edge $e$ joins cells $c_1(e)$ and $c_2(e)$, and its normal velocity is
positive from $c_1$ to $c_2$. Cell $c$ has latitude $\phi(c)$ and longitude
$\lambda(c)$. A line $\ell$ is a latitude $\phi_\ell$, a longitude range
$\Lambda_\ell$ and a set of cells with $m_\ell(c) = 1$. In Omega, $m = 1$ in
every cell. Offline, $m$ is a basin mask and $\Lambda$ spans all longitudes.

The edges across line $\ell$ are those with both cells in the set and in the
longitude range, on opposite sides of $\phi_\ell$:

$$
E_\ell = \{e : m_\ell(c_i) = 1,\ \lambda(c_i) \in \Lambda_\ell
\text{ for } i = 1, 2,\ \phi_\ell \text{ lies between } \phi(c_1)
\text{ and } \phi(c_2)\},
$$

with $\phi(c) < \phi_\ell$ on one side and $\phi(c) \ge \phi_\ell$ on the
other. The sign $s_e$ is $+1$ where $\phi(c_1) < \phi(c_2)$ and $-1$
otherwise, so $s_e u > 0$ for northward flow. The northward transport of
layer $k$ across edge $e$ is

$$
T(e, k) = s_e\, \tilde{h}_e(e, k)\, u(e, k)\, \Delta v(e),
$$

where $\tilde{h}_e$ is the edge pseudo-thickness that Omega's continuity
equation uses, $u$ the normal transport velocity and $\Delta v$ the edge
length. Each edge's layer $k$ spans $z_{bot}(e, k)$ to $z_{top}(e, k)$, the
mean of its two cells' layer interfaces. The streamfunction at elevation $z$
is

$$
\Psi_\ell(z) = -\sum_{e \in E_\ell} \sum_k T(e, k)\, f_{e,k}(z),
\qquad
f_{e,k}(z) = \min\left(1, \max\left(0,
\frac{z - z_{bot}(e, k)}{z_{top}(e, k) - z_{bot}(e, k)}\right)\right).
$$

This is the core MISOMIP uses, minus sign included, with lines of constant
$x$ in place of latitudes. A streamfunction as a function of latitude is
$\Psi_\ell$ over a family of lines that share $m$ and $\Lambda$. Elevations
above or below all the water on the edges of $E_\ell$ are not ocean and are
masked.

> **Rationale.** The edges of $E_\ell$ separate the cells south of
> $\phi_\ell$ from those north of it, so their sum is the northward
> transport across the line. The factor $f$ counts each layer below $z$ in
> full and the layer $z$ falls in by the fraction of its height below $z$.
> The minus sign makes $\Psi$ minus the northward transport below $z$, so
> the transport per unit height is $-\partial \Psi / \partial z$. That is
> the MISOMIP protocol's definition (Asay-Davis et al., 2016) and the
> convention of Omega's current MOC and of MPAS-Analysis. A positive AMOC
> means northward flow above its maximum. By the discrete divergence
> theorem, the sum also equals the vertical flux through $z$ over the cells
> south of the line. Each interior edge's integral to $z$ is shared by its
> two cells with opposite signs, so it cancels however much the layers tilt.

### Algorithm Design: Omega computes the AMOC as it runs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Omega evaluates $\Psi_\ell$ at every sampled step, from that step's
$\tilde{h}_e u$ and interfaces, and averages it over the reduction period.
The only approximation is that each edge's flux is spread evenly over its
layer.

The RAPID line is 26.5°N from 100°W to 0°. At that latitude, the range holds
the Gulf of Mexico, the Florida Straits and the Atlantic, and no other ocean.
It stands in for the Atlantic basin there without a mask.

### Algorithm Design: Lines and basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Each line family in Omega's configuration has a name, a latitude range and
spacing, and a longitude range. A single line has equal minimum and maximum
latitudes. A longitude range runs east from its minimum to its maximum,
with longitudes compared modulo 360°, so it may cross 0° or 180°.

Offline, Polaris computes the `MOC Basins` cell masks of `geometric_features`
on the simulation's mesh, as polaris#592 does for a mesh it builds. A basin is
requested by the name `geometric_features` gives it, without the `_MOC`
suffix: `Atlantic`, `AtlanticMed`, `IndoPacific`, `Pacific` or `Indian`. The
mask's region dimension is whichever dimension of the mask field is not the
cell dimension.

### Algorithm Design: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Offline, Polaris needs the monthly mean of $\tilde{h}_e u$. It takes it from
one of two sources:

- a monthly mean of the product, which `analysis_output` writes as a check;
- otherwise, the monthly means of $u$ and $\tilde{h}$ weighted by
  pseudo-thickness, as [Omega#687](https://github.com/E3SM-Project/Omega/issues/687)
  proposes. $\hat{u} = \overline{\tilde{h}_e u} / \overline{\tilde{h}_e}$,
  so $\hat{u}\,\overline{\tilde{h}_e}$ is the mean flux. With the default
  `FluxThicknessType: Center`, $\tilde{h}_e$ is the mean of the two cells, so
  this is exact. With `Upwind` it is exact only if Omega#687 weights edge
  means by the upwind thickness, which is one of that issue's open questions.

Offline, the interfaces are monthly means, a second approximation. Since
$\tilde{h}$ is a mass per unit area divided by $\rho_0$, $\Psi$ is a mass
transport divided by $\rho_0$ (D6).

The normal transport velocity is the normal velocity plus any eddy-induced
velocity. Offline, a run with an eddy-induced velocity needs that velocity's
mean in its output.

The latitudes and elevations are uniform (D4). Omega's elevations are every
$\Delta z$ from 0 to the deepest sea floor, rounded down. Polaris's offline
elevations are the same.

> **Rationale.** Two other methods are set aside (D2). Interpolating each
> column's vertical velocity to fixed $z$ is wrong where layers tilt, since
> flux between two columns leaves one and enters the other at different
> depths. Summing each layer first and giving the sum one mean depth squeezes
> the streamfunction into the line's mean column.

### Algorithm Design: The analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

For each edge, the sum over $k$ in $\Psi$ is the edge's running transport
from the sea floor, interpolated linearly to $z$ between the edge's
interfaces. The running sum is known at the interfaces, and it is linear
within each layer because the flux is spread evenly over it. Computed that
way, an edge costs its layers plus the elevations, not their product. Omega
and Polaris both use this form.

> **Rationale.** The core as MISOMIP has it forms $f_{e,k}(z)$ for every edge,
> layer and elevation at once. That suits a few lines on a planar mesh. On a
> large global mesh, one line can cross tens of thousands of edges. With 80
> layers and 120 elevations, the array is over a gigabyte per line, and each
> month has hundreds of lines per basin.

### Algorithm Design: Coupled runs compute what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Omega's coupled configuration defines the `Global` and `RAPID` lines. Neither
needs a mask, so nothing is staged.

### Algorithm Design: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The global plot uses Omega's in-situ streamfunction on its `Global` lines.
Each basin's plot uses Polaris's offline streamfunction until Omega computes
basins.

A climatology is the mean of the monthly streamfunctions over the years,
weighted by the days in each month. It is plotted at the lines' latitudes.
Each basin's plot covers a configured latitude range. The default for the
three standard basins is 35°S to 70°N, as in MPAS-Analysis. The global plot
covers all latitudes.

> **Rationale.** Each month's streamfunction uses that month's interfaces. A
> streamfunction of climatological means would use climatological
> interfaces, and a product of separate climatologies of velocity and
> thickness would miss their correlation across months.

The Phase 1 step plots Omega's current global streamfunction at bin centers,
half a bin south of where each value belongs
([polaris#926](https://github.com/E3SM-Project/polaris/issues/926)). The
lines here have exact latitudes, so the step is replaced and the shift goes
with it.

### Algorithm Design: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

For each month $t$,

$$
\mathrm{AMOC}(t) = \max_z \Psi_R(z, t),
$$

where $\Psi_R$ is Omega's monthly-mean streamfunction across the RAPID line.
The maximum is over the whole column.

> **Rationale.** MPAS-Analysis takes the bin edge nearest 26.5°N. A line at
> exactly 26.5°N needs neither that nor interpolation. The maximum over the
> whole column of a monthly mean is what MPAS-Analysis computes, so the two
> can be compared.

## Implementation

### Implementation: The analysis produces the overturning of the global ocean and named basins

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Omega's `MOC` group computes $\Psi_\ell$ for every configured line family
and nothing else (D3). Its binned global chain and its transect chains are
removed, with the `Regions`, `Transects`, `NumBins`, `MinLat` and `MaxLat`
options. Omega#672, the sign error in the transect chain, goes with them.

A configuration with the two default line families:

```yaml
Omega:
  Analysis:
    MOC:
      Enable: true
      # elevations every ElevationSpacing (m), from 0 to the deepest sea floor
      ElevationSpacing: 50.0
      Lines:
        # every 0.5 degrees of latitude, across all longitudes
        Global:
          MinLat: -90.0
          MaxLat: 90.0
          LatSpacing: 0.5
        # the RAPID array: at 26.5N, 100W to 0E holds only the Gulf of Mexico,
        # the Florida Straits and the Atlantic
        RAPID:
          MinLat: 26.5
          MaxLat: 26.5
          MinLon: -100.0
          MaxLon: 0.0
      ReductionPeriod: [1Month]
```

Latitudes and longitudes are in degrees, and longitudes default to all of
them. Each family's output is `MOC_streamfunction_<Name>`, with
`_TimeMean<Period>` for a reduction. Its latitude and elevation coordinates
are attached to the stream, as `MOCLatBinBoundaries` is today. Their
dimension names are built from the family's name, as `BinnedAccumulator`
builds its own.

For each family, the group builds three chains:

- the edge transport,
  `FluxPseudoThickEdge_BinaryMultiply(NormalTransportVelocity)_BinaryMultiply(DvEdge)`;
- the edge interfaces, `GeomZInterface_CellToEdge`;
- the streamfunction, with the transport as input and two operands: the
  family's crossings and the edge interfaces.

### Implementation: Omega computes the AMOC as it runs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

Three new general operators:

- **`CellToEdge`**: the mean of a cell field's two cells on each edge, with
  the input's other dimensions.
- **`LineCrossings`**: computed once, as `CoordinateBinning` is. From
  `LatCell`, `LonCell` and a family's options, it gives each owned edge the
  first and last line it crosses and its sign. An edge that crosses none has
  an empty range.
- **`LineTransport(<Crossings>, <ZInterfaceEdge>)`**: for each owned edge
  with a nonempty range, the running transport from the sea floor,
  interpolated to the elevations and added with its sign to every line it
  crosses. The sum over ranks is Omega's reproducible `globalSum`, and the
  result is negated. The output has a line and an elevation dimension.

`LineTransport` fuses the vertical interpolation with the sum over edges, so
no array of edges by elevations is formed. Its atomic sums over edges on a
device have the order dependence of `BinnedAccumulator`'s
([Omega#661](https://github.com/E3SM-Project/Omega/issues/661)).

The chain parser changes in two ways. A parenthesized argument ends at its
matching parenthesis rather than the first `)`, so an operand may be a field
whose name holds parentheses. A token may take several operands, separated
by commas at the top level.

### Implementation: Lines and basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- `Default.yml` defines the `Global` and `RAPID` families as above, with
  comments, and leaves the `MOC` group disabled as today.
- Offline, a shared step runs polaris#592's `ComputeOceanFeatureMasksStep`
  for the `MOC Basins` group on `SimFiles.mesh_filename()`. Its southern
  transects are written but not read.
- `[ocean_analysis_moc] regions` lists the offline basins, by default
  `Atlantic, AtlanticMed, IndoPacific` (D5).

### Implementation: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- `ocean/realistic_global/analysis_output` adds
  `FluxPseudoThickEdge_BinaryMultiply(NormalTransportVelocity)` to the
  `Fields` of `MonthlyAverages`, as the offline reference's transport.
  `MonthlyAverages` takes chain stems as fields.
- Polaris reads that field's monthly mean when the file has it. Otherwise it
  reads `NormalTransportVelocity` (or `NormalVelocity`, the same field when
  no eddy-induced velocity is on) and `PseudoThickness`, which must be
  weighted by pseudo-thickness. It tells weighted means apart by the
  weighting Omega#687 records in each field's `cell_methods`. A simulation
  with neither is reported and its offline basins skipped.
- `[ocean_analysis_moc]` holds the offline `dlat = 0.5` and `dz = 50` (m).

### Implementation: Overturning has one definition

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

`polaris/ocean/overturning.py` comes from polaris#939. Its core,
`compute_overturning_from_edge_transport()`, takes a transport, the edges'
interface elevations and the target elevations. It reads no model's field
names. This design adds:

- `get_latitude_edges()`: the edges of $E_\ell$ for a cell mask, a latitude
  and a longitude range. It returns the same dataset as `get_line_edges()`,
  with the sign toward increasing latitude.
- Edge interfaces from cell interfaces that the model writes.
  `compute_line_interfaces()` stacks them from SSH and layer thickness, as
  MPAS-Ocean output needs. Omega writes `GeomZInterface`, which only needs
  interpolating to the edges.

The Omega names belong to the MOC steps, and the MPAS-Ocean names to
MISOMIP. Omega's operators follow the same definition and are tested
against these functions.

### Implementation: The analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- `compute_overturning_from_edge_transport()` gains the running-sum form,
  which MISOMIP then also uses.
- The global plot and the AMOC series read only Omega's in-situ output.
- A new `Accumulator` step, `MocSeries`, computes each month's offline
  streamfunction for every configured basin. It finds each basin's edges once
  and reads only those edges and the cells they join. It computes months in
  parallel across its cores. Its cache means each month is read once per
  simulation, whatever ranges later analyses cover.

### Implementation: Coupled runs compute what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

[Omega#663](https://github.com/E3SM-Project/Omega/pull/663) turned on the
`MOC` group for coupled runs. Its options there change to the two default
families.

### Implementation: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- The `Moc` step runs `ncclimo` on Omega's `MOC_streamfunction_Global`
  output and its coordinates, as it does today. It plots at the lines'
  latitudes and writes `global.png` and `global.nc`.
- For each offline basin, it reads the climatology of the `MocSeries` step
  for its year range and writes `<region>.png` and `<region>.nc`. Each region
  has one gallery.
- Each basin's plot range comes from `[ocean_analysis_moc_<region>]`, with
  `min_lat` and `max_lat`. The section name is the basin name in lower case
  with underscores, as for `[ocean_analysis_map_<field>]`. Defaults are given
  for `atlantic`, `atlantic_med` and `indo_pacific`.

### Implementation: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

A new task, `ocean/analysis/amoc_time_series`, takes its years from
`[ocean_analysis_time_series]` and joins the `omega_analysis` suite. Its step
reads `MOC_streamfunction_RAPID_TimeMean1Month` from each monthly MOC file and
takes the maximum over elevation. It writes `amoc.nc`, holding the series and
the line's latitude and longitude range, and plots the series. A new section,
`[ocean_analysis_amoc]`, holds `line = RAPID`. A simulation without that
output is reported and the series skipped.

### Implementation: order of work

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

In dependency order:

1. Polaris: the overturning core, with polaris#939.
2. Polaris: `get_latitude_edges()`, edge interfaces from cell interfaces and
   the running-sum form. These are the reference for item 3.
3. Omega: `CellToEdge`, `LineCrossings`, `LineTransport`, the parser
   changes, the `MOC` group and `Default.yml`, with CTests against values
   from item 2.
4. Polaris: `analysis_output` with the line families and the transport
   field, comparing Omega's streamfunctions with the offline ones.
5. Polaris: the global plot and the AMOC series from Omega's output, which
   fixes polaris#926.
6. Omega: the line families in the coupled configuration.
7. Polaris: the mask step and `MocSeries`, for offline basin plots.
8. Later, under its own design: basin masks in Omega (D7).

## Decisions

Alternatives considered and set aside, cited from the sections they affect.

### D1: The transport across a line, not vertical fluxes seeded by a transect

Xylar, 2026/11/08. Omega and Polaris both sum the transport across a line.
An earlier draft of this design kept Omega's current method for basins:
vertical fluxes summed in latitude bins over a basin's cells, seeded with
the transport through a southern transect.

Set aside: that method. It needs a transect per basin, read into Omega with
the basin masks. It is wrong north of any other opening the basin has, such
as Gibraltar for the Atlantic without the Mediterranean, or the Indonesian
Throughflow for the Pacific and Indian basins. Omega's transect chain also
has a sign error ([Omega#672](https://github.com/E3SM-Project/Omega/issues/672)).

### D2: Fixed elevations, with each edge's own interfaces

Xylar, 2026/11/08. This is the method chosen for the MISOMIP overturning.

Set aside: a depth axis from a horizontal mean of the layer interfaces, as
Omega's current MOC has, and interpolating each column's vertical velocity
to fixed $z$. Both are wrong where layers tilt.

### D3: Omega's MOC group computes only line families

Proposed, 2026/11/08. The global streamfunction then has the same method and
elevations as the AMOC and the offline basins.

Set aside: keeping the binned global chain beside the line families. It
would leave two global streamfunctions with different vertical axes, one of
them plotted half a bin out of place.

### D4: Latitudes and elevations are uniform

Proposed, 2026/11/08. Lines every 0.5° and elevations every 50 m by default,
in Omega and offline.

Set aside: the simulation's reference layer interfaces as the elevations,
and spacing per basin. Neither is needed for plots cropped to each basin,
and shared elevations keep every plot on one axis.

### D5: The default offline basins are Atlantic, AtlanticMed and IndoPacific

Xylar, 2026/11/02. These are the basins MPAS-Analysis plots, alongside the
global ocean.

Set aside: the Atlantic alone. The AMOC no longer needs it, and the basin
plots are what would be compared with MPAS-Analysis.

### D6: The streamfunction is a mass transport divided by $\rho_0$

Xylar, 2026/11/08. The transport is the pseudo-thickness flux that Omega's
continuity equation uses.

Set aside: a volume transport, from the geometric thickness flux. It needs a
conversion on every edge and layer, and offline one more field the size of
`NormalVelocity`. The two differ by the ratio of density to $\rho_0$, a few
percent.

### D7: Lines in Omega now, basins in Omega later

Xylar, 2026/11/08. The AMOC is too fundamental, and too heavy offline on the
largest meshes, to wait for basin masks in Omega.

Basins in Omega need the masks read from a file. The earlier draft designed
that: reworked dynamic input streams
([Omega#422](https://github.com/E3SM-Project/Omega/pull/422)) with labels
read from the file, a `Select` operator, and mask files staged for coupled
runs. `LineCrossings` would then take a cell mask as one more operand.

Set aside: Polaris computing everything offline, and Omega computing basins
now. The first is too slow for the AMOC on the largest meshes. The second
makes the AMOC wait on the mask infrastructure.

### D8: A line is a latitude and a longitude range

Xylar, 2026/11/08. Each is a YAML option, so the RAPID line is visible in the
configuration rather than built into the code.

Set aside: the RAPID line as the Atlantic basin's line at 26.5°N, which needs
the basin mask. The longitude range does the same job at 26.5°N. It also
serves other zonal arrays, such as SAMBA at 34.5°S, on any mesh.

### D9: Polaris's offline computation is the reference and the fallback

Xylar, 2026/11/08. It tests Omega's operators and streamfunctions, and it
gives the basin plots until Omega computes basins. It is also MISOMIP's
computation.

Set aside: using it only as a reference, which would leave no basin plots
until Omega reads masks.

## Testing

### Testing and Validation: The analysis produces the overturning of the global ocean and named basins

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- **Omega against Polaris.** On the coarsest mesh of
  `ocean/realistic_global/analysis_output`, Polaris recomputes the `Global`
  and `RAPID` streamfunctions offline from the transport field and compares
  them with Omega's. The two differ only by the monthly-mean interfaces
  Polaris uses. The difference is reported, and the test fails if it exceeds
  a tolerance set from the first runs.
- **Basins that tile.** Where AtlanticMed and IndoPacific hold every ocean
  edge across a latitude, their offline streamfunctions sum to the offline
  global one there to round-off.
- **The RAPID line is the Atlantic's.** Offline, the RAPID line and the
  Atlantic basin's line at 26.5°N have the same edges, so their
  streamfunctions agree to round-off.

### Testing and Validation: Omega computes the AMOC as it runs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

CTests on a small mesh with synthetic fields:

- `CellToEdge` gives the mean of each edge's two cells;
- `LineCrossings` keeps only edges whose cells straddle a line and lie in its
  longitude range, including a range across 180°, and every sign points
  north;
- `LineTransport` matches values from Polaris's core for a known transport
  and tilted layers;
- the parser accepts an operand holding parentheses, and several operands.

### Testing and Validation: Lines and basins are defined by data

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A CTest checks that a line family's output names and dimensions come from
  its name.
- A unit test on a small synthetic mask dataset checks that offline basins
  are found by name, whatever the region dimension is called.

### Testing and Validation: The streamfunction is correct for any vertical coordinate

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A unit test of `get_latitude_edges()` on a synthetic mesh checks the edges
  kept and their signs.
- A unit test with tilted layers and a known transport checks $\Psi$ at
  fixed elevations.
- A unit test checks that a simulation without a usable transport is
  reported and its offline basins skipped.
- Once Omega#687 is in, `analysis_output` checks that the transport from the
  weighted means matches the monthly mean of the product.

### Testing and Validation: Overturning has one definition

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

The MISOMIP tests from polaris#939 keep passing. They exercise the shared
core.

### Testing and Validation: The analysis is practical on the largest meshes

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A unit test checks that the running-sum form matches the form with
  $f_{e,k}(z)$ on random layers and transports.
- Omega's cost of the `MOC` group per sampled step, and `MocSeries`'s cost
  per month, are timed on a large mesh and reported.

### Testing and Validation: Coupled runs compute what the analysis needs

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

A short coupled run on oQU240 writes `MOC_streamfunction_RAPID` and
`MOC_streamfunction_Global`.

### Testing and Validation: Polaris plots each basin's streamfunction

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A unit test checks that values are plotted and written at the lines'
  latitudes.
- A unit test checks that a basin with no ocean edges across a line gives a
  masked column there rather than an error.

### Testing and Validation: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/08

Contributors: Xylar Asay-Davis, Claude

- A unit test builds a synthetic streamfunction with a known maximum and
  checks the series.
- The series from an Omega run is compared by eye with MPAS-Analysis's for an
  MPAS-Ocean run on the same mesh. As in the umbrella design, this is a check
  of sign and magnitude made by a scientist, not an automated test.
