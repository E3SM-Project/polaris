(design-ocean-analysis-regional-moc)=

# Regional Overturning Circulation

Creation date: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

## Summary

This design adds the overturning streamfunction of named ocean basins to
Omega's in-situ analysis and to the Polaris ocean analysis that reads it. The
basin that matters most is the Atlantic. From its streamfunction, Polaris
derives the standard measure of the Atlantic meridional overturning
circulation (AMOC): the maximum of the streamfunction at 26.5°N, the latitude
of the RAPID array, as a monthly time series. Regional overturning is one of
the products the umbrella design defers from Phase 1
({ref}`design-ocean-analysis`).

Most of the computation exists. Omega's `MOC` analysis group accepts a list of
regions, and it seeds each region's latitude integral with the transport
through the region's southern boundary. What is missing is the masks: nothing
puts a basin's cells and boundary edges into Omega's field registry. Polaris
computes such masks
([polaris#592](https://github.com/E3SM-Project/polaris/pull/592)) and stages
them for MPAS-Ocean
([polaris#921](https://github.com/E3SM-Project/polaris/pull/921)). An early
Omega draft, [Omega#422](https://github.com/E3SM-Project/Omega/pull/422),
reads fields like them from a file whose field and dimension names Omega does
not know in advance. That draft is reworked here rather than merged as is.

The design joins these pieces. Its challenges are:

- **Regions are named by data, not code.** Omega's source names no region, no
  number of regions and no region dimension. The masks, their dimension names
  and the region labels all come from the file.
- **The path stays open for an expression language.** A proposal for E3SM,
  *Composable runtime diagnostics for the Energy Exascale Earth System Model*
  (Mahfouz et al., in preparation), would let a user request a diagnostic as
  an expression over model fields. Every new piece here is a general
  operation such an expression could name. None of it is logic private to the
  MOC group.
- **The southern boundary has the right sign.** Omega adds the
  southern-boundary term with the opposite sign from MPAS-Analysis
  ([Omega#672](https://github.com/E3SM-Project/Omega/issues/672)). The
  regional path has not run on real masks, so nothing has shown it.

Success is an Atlantic streamfunction from a low-resolution Omega run that
matches an offline recomputation from the same model state. Its AMOC time
series should have the sign and magnitude MPAS-Analysis reports for comparable
E3SM runs.

## Requirements

### Requirement: Omega computes the overturning streamfunction of named basins

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Omega shall compute the meridional overturning streamfunction of each
requested basin as a function of latitude and elevation. A basin is a set of
ocean cells bounded to the south by a transect. Its streamfunction shall
include the transport through that transect. It shall be written with the
same temporal reductions, units and axes as the global streamfunction.

### Requirement: Basins are defined by input data

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

The basins to compute, and the cells and transect edges that define each, shall
come from an input file and the run's configuration. Omega shall not need to
know in advance the basins' names, how many there are, or the names of the
dimensions they are stored along. Adding a basin, renaming one or changing the
mesh shall not require a change to Omega.

### Requirement: Polaris produces basin masks for Omega meshes

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Polaris shall produce the basin masks and southern-boundary transects for an
Omega mesh in a form Omega reads directly. A second mask file read by the same
run, such as one for regional statistics, shall not conflict with the first.

### Requirement: Coupled runs can compute the regional streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

An E3SM run with Omega shall compute the regional streamfunction on any mesh
whose mask file is staged in E3SM's input data. On a mesh without one, the run
shall compute the global streamfunction only, as it does today.

### Requirement: Polaris plots each basin's streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

The analysis shall plot the climatological streamfunction of every basin the
simulation wrote, beside the global one. Each plot covers its basin's
latitudes. Every value is plotted and written at the latitude it represents.

### Requirement: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

The analysis shall produce a monthly time series of the maximum over
elevation of the Atlantic streamfunction at 26.5°N, with the data behind it.
The latitude and the basin shall be config options.

### Requirement: The regional streamfunction is composed of general operations

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Each intermediate quantity of the regional streamfunction shall come from an
operation that a configuration could request on its own. These are selecting
one region, masking to it, summing across a transect, summing in latitude bins
and accumulating along a dimension. The MOC group shall assemble such
operations and compute nothing itself.

> **Rationale.** The proposed expression language turns an expression into a
> graph of the model's existing compiled diagnostics, resolving each operand
> by name. An operation hidden inside the MOC group cannot be reached that
> way. It would have to be rewritten before the language could produce the
> MOC.

## Algorithm Design

### Algorithm Design: Omega computes the overturning streamfunction of named basins

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Layers $k = 0, \ldots, K-1$ count down from the surface. Interface $k$ is the
top of layer $k$, and interface $K$ is the sea floor. Latitude bin $i$ spans
$[b_i, b_{i+1})$. For basin $r$, $m_r(c) \in \{0, 1\}$ marks its cells and
$s_r(e) \in \{-1, 0, 1\}$ marks its southern transect. The sign is chosen so
that $s_r u > 0$ for flow into the basin.

The transport into the basin through layer $k$ of its southern transect is

$$
T_r(k) = \sum_e s_r(e)\, u(e, k)\, h(e, k)\, \Delta v(e),
$$

where $u$ is the normal velocity, $h$ the geometric layer thickness at the edge
and $\Delta v$ the edge length. The streamfunction on the southern boundary is
minus the transport below each interface:

$$
B_r(k) = -\sum_{k' \ge k} T_r(k'), \qquad B_r(K) = 0.
$$

The upward volume flux through interface $k$ of the basin's cells in bin $i$
is

$$
F_r(i, k) = \sum_{c \,:\, m_r(c) = 1,\ \phi(c) \in [b_i, b_{i+1})}
w(c, k)\, A(c),
$$

and the streamfunction at the northern edge of bin $i$ is

$$
\Psi_r(b_{i+1}, k) = B_r(k) + \sum_{j \le i} F_r(j, k).
$$

The global streamfunction is the case $m = 1$, $B = 0$, which Omega computes
today. All basins share the global latitude bins (D5). South of a basin's
cells, its streamfunction is $B_r$ in every bin.

Omega's `MOC::buildTransectBCChain()` seeds the latitude sum with
$+\sum_{k' \ge k} T_r(k')$ in place of $B_r$ (Omega#672). The chain gains a
factor of $-1$.

> **Rationale.** Take the part of basin $r$ that lies below interface $k$ and
> between the transect and $b_{i+1}$. In steady state it gains $-B_r(k)$
> through the transect and loses $\sum_{j \le i} F_r(j, k)$ upward through the
> interface. The remainder leaves northward across $b_{i+1}$, so $\Psi_r$ is
> minus the northward transport below interface $k$. That is the convention
> of Omega's global streamfunction. Summing from the sea floor, where nothing
> crosses, keeps the free surface out of the sum. MPAS-Analysis uses the same
> formula in `_compute_moc()` of
> [`streamfunction_moc.py`](https://github.com/MPAS-Dev/MPAS-Analysis/blob/develop/mpas_analysis/ocean/streamfunction_moc.py).
> With Omega's current sign, the Atlantic streamfunction is wrong by $2B_r$,
> an error as large as the AMOC itself.

### Algorithm Design: Basins are defined by input data

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

The input file holds two families of fields, each along a dimension the file
names:

- cell masks on (cells, $D_r$), with a label for each entry of $D_r$;
- transect edge signs on (edges, $D_t$), with a label for each entry of
  $D_t$.

The run's configuration names the basins by label and names the mask and sign
fields. Basin $r$'s mask is the entry of the mask field labeled $r$. Its
southern transect is the entry of the sign field with the same label (D1).
Omega reads $D_r$ and $D_t$ from the fields' own dimensions and looks the
labels up at initialization.

A transect's edges are those where its sign is nonzero. There is no separate
transect mask.

Fields keep the type they have in the file, so masks and signs are integers
(D2).

### Algorithm Design: Polaris produces basin masks for Omega meshes

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Polaris computes the masks as it does for MPAS-Ocean (polaris#592). For an
Omega file it renames the region and transect families by a fixed rule, given a
region family name $R$ and a transect family name $T$ (D3):

| MPAS-Ocean file | Omega file |
| --- | --- |
| `nRegions` | `N<R>s` |
| `region<X>` | `<R><X>` |
| `nTransects` | `N<T>s` |
| `transect<X>` | `<T><X>` |

Mesh dimensions take Omega's names, as they do today. For the MOC group,
$R$ is `MocBasin` and $T$ is `MocTransect`, giving for example:

| MPAS-Ocean file | Omega file |
| --- | --- |
| `regionCellMasks(nCells, nRegions)` | `MocBasinCellMasks(NCells, NMocBasins)` |
| `regionNames(nRegions, StrLen)` | `MocBasinNames(NMocBasins, StrLen)` |
| `transectEdgeMaskSigns(nEdges, nTransects)` | `MocTransectEdgeMaskSigns(NEdges, NMocTransects)` |
| `transectNames(nTransects, StrLen)` | `MocTransectNames(NMocTransects, StrLen)` |

Labels in an Omega MOC file drop the `_MOC` suffix that `geometric_features`
gives each basin. The labels are `Atlantic`, `AtlanticMed`, `IndoPacific`,
`Pacific` and `Indian`. The region-group variables, which only MPAS-Ocean
reads, are dropped. MPAS-Ocean files are unchanged.

> **Rationale.** Omega registers the fields and dimensions of every input
> file in one namespace per run. A repeated name with a different size or
> content is an error. A family name per mask group keeps two mask files
> apart without any Omega configuration.

### Algorithm Design: Coupled runs can compute the regional streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Each mesh's Omega MOC mask file is staged with its other Omega inputs. Omega's
build-namelist step lists the file against the mask stream for that mesh, and
it turns that stream on only when the mesh has such a file. The mesh's
configuration override lists the Atlantic, AtlanticMed and IndoPacific basins
(D8). A mesh without a mask file keeps `Regions: [Global]`.

### Algorithm Design: Polaris plots each basin's streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

The basins are those the simulation's own Omega configuration lists, following
the umbrella design's rule of reading what a simulation says about itself.
Value $i$ of a streamfunction Omega writes is placed at $b_{i+1}$, the
northern edge of bin $i$, in both the plot and the data file. Each basin's plot
covers a configured latitude range. The default for the three standard basins
is 35°S to 70°N, as in MPAS-Analysis. The global plot covers all latitudes.

The Phase 1 step places value $i$ at the center of bin $i$, half a bin south
of where it belongs, in both the plot and `global.nc`
([polaris#926](https://github.com/E3SM-Project/polaris/issues/926)). The
shift is 0.5° with the default 180 bins and 1.5° on oQU240, where Omega#663
uses 60. The global streamfunction moves to the bin edges along with the
regional ones.

### Algorithm Design: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

For each month $t$ of monthly-mean output,

$$
\mathrm{AMOC}(t) = \max_k \Psi_A(\phi_R, k, t),
$$

where $\Psi_A(\phi_R, k, t)$ is the Atlantic streamfunction interpolated
linearly in latitude between the two bin edges on either side of $\phi_R$. The
defaults are $\phi_R = 26.5$°N and the `Atlantic` basin. The maximum is over
the whole column.

> **Rationale.** MPAS-Analysis takes the bin edge nearest 26.5°N.
> Interpolating keeps the metric from jumping when the bin width changes,
> and the bin width differs between meshes: 180 bins by default, 60 on oQU240
> in Omega#663. The maximum over the whole column of a monthly mean is what
> MPAS-Analysis computes, so the two can be compared. Computing it in Polaris
> follows the umbrella design's division of labor (D6).

### Algorithm Design: The regional streamfunction is composed of general operations

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Each term of the formula above is one chain of operators. The right-hand
column gives the same term in xarray spelling, which the proposed expression
language follows where it can.

| Term | Omega chain | xarray spelling |
| --- | --- | --- |
| $m_r$ | `MocBasinCellMasks_Select(NMocBasins=Atlantic)` | `MocBasinCellMasks.sel(NMocBasins='Atlantic')` |
| $s_r$ | `MocTransectEdgeMaskSigns_Select(NMocTransects=Atlantic)` | `MocTransectEdgeMaskSigns.sel(NMocTransects='Atlantic')` |
| $T_r$ | `<uhΔv>_TransectAccumulator(<s_r>)` | `(uhdv * s_r).sum('NEdges')` |
| $B_r$ | `<T_r>_ScalarMultiply(-1.0)_PrefixSum`, from the bottom | cumulative sum of `-T_r` over `NVertLayers`, from the bottom |
| $F_r$ | `<wA>_ExtractRegion(<m_r>)_BinnedAccumulator(LatCell_BinIndex)` | `wA.where(m_r == 1).groupby_bins(LatCell, bins).sum()` |
| $\Psi_r$ | `<F_r>_PrefixSum(BC=<B_r>)` | `F_r.cumsum('lat') + B_r` |

Only `Select` is new. The operators follow three rules, which later sections
cite by name:

- **Explicit operands.** Every input an operator reads is named in its token.
  No operator builds an input name from a convention.
- **Canonical names.** An operator's output name depends only on its inputs
  and arguments. The same request in two chains is then one field.
- **Labeled dimensions.** An operator refers to a dimension by the name the
  field carries.

> **Rationale.** These are the properties the proposal relies on. Fields carry
> labeled layouts, operands resolve by name, and a canonical rendering of an
> expression is its key. An operator that meets them can become one of the
> language's primitives without change. Carrying the region dimension through
> the whole chain, as xarray broadcasting would, is left to the language
> (D4).

## Implementation

### Implementation: Omega computes the overturning streamfunction of named basins

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Changes to `MOC.cpp`:

- Entries of `Regions` other than `Global` are labels. Two new options,
  `RegionMasks` and `TransectSigns`, name the mask and sign fields. A
  non-global region without them aborts with a message naming the missing
  option.
- `Transects` is removed. A basin's transect is found by its label rather
  than by its position in a list.
- For each basin, the group builds the two `Select` chains of the table
  above. It passes the selected mask to `ExtractRegion` and the selected
  signs to `TransectAccumulator`.
- The southern-boundary chain gains `ScalarMultiply(-1.0)` before its
  `PrefixSum`, which fixes Omega#672. `PrefixSum` applies the `OutputName`
  alias, so the alias still names the chain's output.
- The regional depth axis gets a name built from the label,
  `GeomZInterface_HorzMean_<Region>`. Today `buildDepthCoordChain()` returns
  `GeomZInterface_<Mask>_HorzMean`, but the chain parser names that field
  `GeomZInterface_ExtractRegion(<Mask>)_HorzMean`. The global axis keeps the
  name Polaris reads, `GeomZInterface_HorzMean`.

Output names do not change: `MOC_streamfunction_<Region>`, with
`_TimeMean<Period>` for a reduction.

A configuration that computes the Atlantic and Indo-Pacific streamfunctions:

```yaml
Omega:
  IOStreams:
    MocBasinsAndTransects:
      UsePointerFile: false
      Filename: mocBasinsAndTransects.nc
      Mode: read
      Freq: 1
      FreqUnits: OnStartup
      DynamicFields: true
      Contents: [MocBasinCellMasks, MocBasinNames,
                 MocTransectEdgeMaskSigns, MocTransectNames]
  Analysis:
    MOC:
      Enable: true
      Regions: [Global, Atlantic, IndoPacific]
      RegionMasks: MocBasinCellMasks
      TransectSigns: MocTransectEdgeMaskSigns
```

`Default.yml` defines this stream with `FreqUnits: Never`. It sets
`RegionMasks` and `TransectSigns` to the names above and keeps
`Regions: [Global]`.

### Implementation: Basins are defined by input data

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

**Dynamic input streams.** Omega#422 is rebased onto `develop`, which has
gained the Analysis module since the draft. It then changes as follows:

- A field keeps the type it has in the file. Integers stay integers, and
  floating-point data are stored as `Real`. The draft's promotion of every
  field to R8 is dropped (D2).
- A character variable whose dimensions are a non-mesh dimension $D$ and a
  string length is read on every task, if listed in `Contents`. Its strings
  become the labels of $D$. Looking up a label that $D$ lacks aborts, and the
  message lists the labels $D$ has.
- Two streams that declare the same dimension must agree on its labels as
  well as its size.
- `Dimension` gains labels: `setLabels()`, `getLabels()` and
  `getLabelIndex()`.

The draft's other rules stand. A field has one mesh dimension and at most one
other. Names come from the file, and a repeated field name is an error.
Dynamic streams are read after `HorzMesh::init()` and before Analysis.

**`Select`.** A new analysis operator with the token `Select(<Dim>=<Label>)`:

- Its input has dimensions (mesh, `<Dim>`). Its output is the slice labeled
  `<Label>`, on the mesh dimension alone, with the input's type.
- Its output is named `<Input>_Select(<Dim>=<Label>)` (canonical names).
- It is computed once, at initialization, as `CoordinateBinning` is, since
  its input does not change.

The MOC group reads `<Dim>` from the field's dimensions, so neither code nor
configuration names it.

**`TransectAccumulator`.** The token becomes `TransectAccumulator(<Signs>)`,
naming the sign field (explicit operands). The operator reads the transport
and the signs, and treats edges with a zero sign as off the transect. The
parser stops building `TransectEdgeMask<Name>` and
`TransectEdgeMaskSign<Name>` from a transect name.

**Parser.** A parenthesized argument ends at its matching parenthesis rather
than the first `)`. An argument may then be a field whose name contains
parentheses, such as a `Select` output.

### Implementation: Polaris produces basin masks for Omega meshes

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

- When the model is Omega, `ComputeOceanFeatureMasksStep._write_mask_dataset()`
  applies the family rule after `map_to_native_model_vars()`.
- `[feature_masks]` gains `omega_region_name` and `omega_transect_name`. They
  default to `MocBasin` and `MocTransect` for the `MOC Basins` group and are
  required for any other group written for Omega.
- For Omega, the MOC path drops `_MOC` from the labels and drops the
  region-group variables.
- `ocean/realistic_global/analysis_output` gains a MOC mask step on the
  forward step's mesh. `monthly_output.yaml` gains the stream and the
  options above. A new option, `[analysis_output] moc_regions`, lists the
  basins and defaults to `Global, Atlantic, AtlanticMed, IndoPacific`.

### Implementation: Coupled runs can compute the regional streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

This builds on [Omega#663](https://github.com/E3SM-Project/Omega/pull/663),
which turns the MOC group on in coupled runs.

- The `e3sm/init` component inputs from polaris#921 stage an Omega MOC mask
  file once they support Omega. They raise `NotImplementedError` for Omega
  today.
- Omega's `input_files.yaml` lists that file for each mesh with
  `streams: [MocBasinsAndTransects]`.
- `build_runtime_overrides()` sets `FreqUnits: OnStartup` on a dynamic stream
  whose file `input_files.yaml` supplies. Without a file, the stream stays
  `Never`.
- `config_overrides.yaml` sets
  `Regions: [Global, Atlantic, AtlanticMed, IndoPacific]` under each mesh that
  has a mask file (D8). Per-mesh overrides may set `Analysis`, though not
  `IOStreams`, so this fits the existing rule.

### Implementation: Polaris plots each basin's streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

- `SimFiles` reads `Regions` from the simulation's MOC group.
- The `Moc` step loops over those basins. For each it reads
  `MOC_streamfunction_<Region>` and the basin's depth axis, then writes
  `<region>.png` and `<region>.nc` and one gallery. The step already expects
  one gallery per region.
- `_bin_centers()` is replaced by the northern bin edges, `boundaries[1:]`,
  for every basin and for the global streamfunction. This fixes
  [polaris#926](https://github.com/E3SM-Project/polaris/issues/926).
- Each basin's plot range comes from `[ocean_analysis_moc_<region>]`, with
  `min_lat` and `max_lat`. The section name is the label in lower case with
  underscores, as for `[ocean_analysis_map_<field>]`. Defaults are given for
  `atlantic`, `atlantic_med` and `indo_pacific`.
- A configured basin with no output is reported and skipped, as a missing
  global streamfunction is today.

### Implementation: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

A new task, `ocean/analysis/amoc_time_series`, takes its years from
`[ocean_analysis_time_series]` and joins the `omega_analysis` suite. Its one
step reads the Atlantic streamfunction from each monthly MOC file in the
range. It writes `amoc.nc`, holding the series and the latitude used, and
plots the series. Each month costs a read of one small array, so the step is
not split into an accumulator and a plot (principle 10 of the umbrella
design). A new section, `[ocean_analysis_amoc]`, holds `region = Atlantic` and
`latitude = 26.5`.

### Implementation: The regional streamfunction is composed of general operations

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Met by the `Select`, `TransectAccumulator` and parser changes above. Nothing
further is needed.

### Implementation: order of work

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Omega pull requests for items 2–4 and 8 cite this document as their design
(D7). In dependency order:

1. Polaris: place the global streamfunction at the northern bin edges, fixing
   polaris#926. This changes merged code and depends on nothing below.
2. Omega: dynamic input streams, reworked from Omega#422.
3. Omega: `Select`, the `TransectAccumulator` operand and the parser fix.
4. Omega: the MOC group changes, including the fix for Omega#672, and
   `Default.yml`.
5. Polaris: Omega names for mask files. This can land at any point before
   item 6.
6. Polaris: regional MOC in `analysis_output`, once items 2–4 are in the
   Omega submodule.
7. Polaris: regional plots and the AMOC time series.
8. Coupled runs: Omega mask files in the component inputs, then Omega's
   `input_files.yaml`, `build_runtime_overrides()` and
   `config_overrides.yaml`.

## Decisions

Alternatives considered and set aside, cited from the sections they affect.

### D1: Basins are selected from the file by label

Xylar, 2026/11/02. The file's label variables become labels on its
dimensions, and the configuration names basins by label.

Set aside: an index per basin in the MOC configuration. It restates the
file's order, and nothing would check it. Also set aside: one variable per
basin, such as `RegionMaskAtlantic(NCells)`, with no region dimension. It
fits Omega's current names with no new operator, but the Omega file would
diverge from MPAS-Ocean's. A basin's identity would then live in a naming
convention, and regional statistics would list dozens of variables.

### D2: Fields keep the file's type

Xylar, 2026/11/02. Masks and signs are read as integers, which
`ExtractRegion` and `TransectAccumulator` already require.

Set aside: promoting every field to R8, as Omega#422 drafted, and changing
both operators and their attached regional masks to take `Real` weights. That
changes more existing code, and a field's type would depend on its reader
rather than its data.

### D3: Omega mask files use a family name per mask group

Xylar, 2026/11/02. Polaris names the region and transect families of each
mask group, from config options.

Set aside: keeping the MPAS-Ocean names in Omega files, as polaris#592 does
today. A second mask file would repeat `regionCellMasks` and `nRegions` with a
different size, which Omega rejects. Also set aside: renaming on read in each
stream's Omega configuration. The configuration would have to restate the
file's names.

### D4: One basin per chain, with no region dimension through the operators

Proposed, 2026/11/02. Each basin's chain works on a slice of the masks, and
the output is one variable per basin, as today.

Set aside: carrying the region dimension through `ExtractRegion`,
`BinnedAccumulator`, `PrefixSum` and `TransectAccumulator`, so that the
output is one variable with a region dimension, as in MPAS-Ocean. Four
operators would need a higher rank, and the region and transect dimensions
would have to be paired. Every basin in the file would be computed, whether
requested or not. Broadcasting over a dimension is a rule the expression
language would supply for all operators at once.

### D5: All basins share the global latitude bins

Proposed, 2026/11/02. This is how Omega and MPAS-Ocean's analysis member work
today.

Set aside: bins per basin, as MPAS-Analysis uses when post-processing, at
0.5° from the basin's southernmost cell. That needs a bin assignment and a
latitude axis per basin. Plots are cropped instead.

### D6: Polaris computes the AMOC time series

Proposed, 2026/11/02. The metric is a maximum of monthly means, which Polaris
can take without loss from the monthly MOC output.

Set aside: an in-situ Omega diagnostic, such as a transect at 26.5°N. The
binned streamfunction already gives the transport across that latitude, and
the umbrella design puts metrics derived from monthly means in Polaris.

### D7: This document is the design of the Omega parts

Xylar, 2026/11/02. Omega pull requests for this work cite this document. A
design in Omega's repository is written only for Omega work that outgrows what
this document specifies. Omega#422's draft design is superseded.

Set aside: rewriting Omega#422's design to match this one, and adding `Select`
and the MOC changes to Omega's Analysis design. Two designs of one change
would have to be kept in step.

### D8: Coupled runs compute the Atlantic, AtlanticMed and IndoPacific basins

Xylar, 2026/11/02. These are the basins MPAS-Analysis plots. They are also
the default of `[analysis_output] moc_regions`. The cost per basin in Omega
has not been measured.

Set aside: the Atlantic alone. It is enough for the AMOC time series, but not
for the basin plots that would be compared with MPAS-Analysis.

## Testing

### Testing and Validation: Omega computes the overturning streamfunction of named basins

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

- **CTest of the southern boundary.** On synthetic fields with a known
  transect transport, the regional streamfunction at the southern boundary
  equals $B_r$. The existing masked-MOC system test,
  `testMaskedMOCChainConstruction`, checks only that the output fields exist.
  It is extended to check values. Any value check with a nonzero transport
  would have caught Omega#672.
- **Offline recomputation.** On the coarsest mesh of
  `ocean/realistic_global/analysis_output`, Omega writes MOC snapshots and
  the model state at the same step. A Polaris step recomputes $\Psi_r$ from
  the formula above and compares. The tolerance is set by running the same
  comparison on the global streamfunction, which is computed the same way
  with $B = 0$.
- **Basins that tile.** If AtlanticMed and IndoPacific together cover the
  ocean north of 34°S, their streamfunctions sum to the global one there.
  The sum holds up to the change in layer thickness over the period.

### Testing and Validation: Basins are defined by input data

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

CTests, each on a small synthetic file:

- an integer field is read as an integer;
- labels are attached to their dimension and looked up by name;
- an unknown label aborts;
- two streams with the same dimension but different labels abort;
- `Select` returns the labeled slice;
- `TransectAccumulator` sums only the edges with a nonzero sign, each with
  its sign.

The draft's existing tests for field and dimension collisions are kept.

### Testing and Validation: Polaris produces basin masks for Omega meshes

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Unit tests on a small synthetic mask dataset check three things. The family
rule renames what the tables say. Labels lose their `_MOC` suffix. An
MPAS-Ocean file is unchanged.

### Testing and Validation: Coupled runs can compute the regional streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

- A unit test in `omega_buildnml/tests` checks that a dynamic stream is
  turned on only for a mesh whose `input_files.yaml` entry supplies its file.
- A short coupled run on oQU240 writes `MOC_streamfunction_Atlantic`.

### Testing and Validation: Polaris plots each basin's streamfunction

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

- A unit test checks that value $i$ is placed at $b_{i+1}$ in the data file,
  for the global streamfunction and a regional one.
- A unit test checks that basins come from the simulation's Omega
  configuration, and that a basin with no output is reported rather than
  raising an error.

### Testing and Validation: Polaris plots an AMOC time series at the RAPID latitude

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

- A unit test builds a synthetic streamfunction whose maximum lies between two
  bin edges, and checks the interpolated maximum.
- The series from an Omega run is compared by eye with MPAS-Analysis's for an
  MPAS-Ocean run on the same mesh. As in the umbrella design, this is a check
  of sign and magnitude made by a scientist, not an automated test.

### Testing and Validation: The regional streamfunction is composed of general operations

Date last modified: 2026/11/02

Contributors: Xylar Asay-Davis, Claude

Covered by the operator CTests above.
