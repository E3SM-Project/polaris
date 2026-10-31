# Idealized Ice-Shelf Cases in E3SM

Creation date: 2026/10/31

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

E3SM will run the ISOMIP+ ocean experiments Ocean0–4 and the MISOMIP1
coupled experiments IceOcean1r and IceOcean1ra, with MPAS-Ocean and MALI as
its only active components. The MISOMIP plan
([E3SM-Project/polaris#858](https://github.com/E3SM-Project/polaris/pull/858))
sets out the work. [MISOMIP Inputs for E3SM](misomip_e3sm_init.md) designs the
meshes, maps, initial conditions and case configuration that Polaris
builds. This design covers the changes E3SM itself needs. None is specific
to ISOMIP+: any case with an active ocean and MALI and no atmosphere can
use them.

The changes land on FAnSSIE, the E3SM development branch for ocean–ice-sheet
coupling (`fanssie-ocn-glc-coupling` on E3SM-Ocean-Discussion/E3SM). A first
E3SM run of 4 km Ocean0 with a static MALI showed which changes a
hand-built case needs. It ran 5 days with the five changes marked "done"
below, plus the floating-fraction change, which made runs with geometry
import on and off bit for bit.

| Change                                                       | Status                |
|--------------------------------------------------------------|-----------------------|
| A prognostic ocean without an atmosphere                     | done, in PR           |
| Wetting and drying and tidal forcing in E3SM's ocean         | done, in PR           |
| Grids and input files that E3SM does not list                | done, in PR           |
| Wetting and drying that keeps the input's floating fraction  | done, in PR           |
| MALI's namelist without the removed lapse rate               | done, in PR           |
| The ocean's interior restoring and tidal mask by case variables | done, in PR        |
| An option that keeps glc's runoff out of the ocean           | done, branch          |
| The ocean's coupler areas from the glc-to-ocean map          | done, branch          |

Everything specific to the experiments comes from a case's user-mods
directory ([Requirements](#requirements)).

Success means:

- 4 km Ocean0 runs in E3SM with a static MALI, and runs with geometry
  import on and off are bit for bit;
- the coupler budgets close for the melt exchanged between the ocean and
  MALI;
- MALI's calving and face-melt runoff never reach the ocean, and no case
  needs a runoff map;
- a case is configured entirely from its user-mods directory, with no grid,
  compset or input-file entries in E3SM;
- existing E3SM configurations are bit for bit.

## Requirements

### Requirement: A prognostic ocean runs without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

A case can run an active ocean and glc with stub atmosphere, land, sea ice,
river and wave components. The ocean then receives fluxes only from glc.

### Requirement: Exchanged fluxes are conserved without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Without an atmosphere, the melt and heat exchanged between the ocean and glc
are conserved to the precision of the coupler budgets.

### Requirement: glc's runoff can be kept out of the ocean

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

A case can couple ice-shelf melt and geometry between the ocean and glc
while glc's calving and face-melt runoff reach no component. Such a case
needs no runoff map.

### Requirement: The ocean can use wetting and drying and an outflow

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

An E3SM case can turn on MPAS-Ocean's wetting and drying and its tidal
forcing, with the options and behavior of standalone MPAS-Ocean.

### Requirement: Partly floating cells melt over their floating fraction

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Under wetting and drying, a floating cell melts over the floating fraction
that its input gives, in E3SM and standalone alike. Importing a geometry
equal to the ocean's own changes nothing.

### Requirement: A case can use grids and input files that E3SM does not list

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

A case can use ocean and glc grids, initial conditions, graph partitions,
MALI data-mode files and the ocean's forcing files that have no entry in
E3SM.

### Requirement: Every E3SM case with MALI initializes

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Every E3SM case with MALI reaches its first time step on FAnSSIE.

### Requirement: Experiment-specific configuration stays outside E3SM

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Everything specific to an experiment comes from a case's user-mods
directory and the compset long name.

### Requirement: Existing configurations are unchanged

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Every existing E3SM configuration is bit for bit. Standalone and E3SM runs
change only where wetting and drying meets a fractional floating fraction.

## Algorithm Design

### Algorithm Design: A prognostic ocean runs without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

The MCT driver accepts a prognostic ocean without an atmosphere. Prognostic
sea ice and land still require one. Without an atmosphere:

- the driver computes no atmosphere–ocean fluxes, which keep the zeros they
  are initialized with;
- the ocean's merge therefore sets every input to zero except those from
  glc;
- ocean albedos are still computed, with no effect, since there is no
  shortwave ([D1](#decisions));
- fractions and history on the atmosphere's grid are skipped.

The MOAB driver is unchanged, since only the MCT driver couples ice-shelf
melt.

### Algorithm Design: Exchanged fluxes are conserved without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

The coupler corrects each flux by the ratio of a component's model area to
its coupler area. With an atmosphere, the ocean's coupler areas come from
the ocean-to-atmosphere map. Without one, they are the ocean's model areas,
while glc's come from the glc-to-ocean map. Map and model areas differ by up
to $4\times10^{-5}$ in these cases, so conservation is off by that much.

Without an atmosphere, the ocean's coupler areas come from the destination
areas of the glc-to-ocean map, as glc's come from its source areas
([D4](#decisions)). This holds whenever glc and the ocean exchange fields,
whether runoff, ice-shelf fields or both.

The coupler also corrects cells whose domain mask is zero, wherever both
the model and the coupler areas are nonzero ([D9](#decisions)). MPAS-Ocean
masks every cell with land ice, so that the atmosphere and sea ice reach no
ice-shelf cavity, but those cells exchange melt and heat with glc.

### Algorithm Design: glc's runoff can be kept out of the ocean

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

With MALI, the driver's flag that glc has ocean coupling fields is always
on. That one flag turns on both runoff to the ocean and, when the ocean
asks for it, ice-shelf coupling. A new driver option, on by default,
controls runoff alone ([D3](#decisions)). With it off:

- the coupler maps no runoff from glc to the ocean, and the ocean's runoff
  inputs from glc are zero;
- the coupler reads neither glc-to-ocean runoff map;
- ice-shelf coupling is unchanged;
- glc's coupler areas still come from the glc-to-ocean map.

```{admonition} Rationale
The protocol's calved ice adds no freshwater (Sects. 3.1.2 and 4). Static
and data-mode MALI have no other runoff, and the MALI meshes these cases use
have no runoff map.
```

### Algorithm Design: The ocean can use wetting and drying and an outflow

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

E3SM's MPAS-Ocean namelist gains the `wetting_drying` and `tidal_forcing`
groups, with the Registry's descriptions and defaults, which leave both
features off. E3SM's run loop builds the tidal forcing before every time
step, after the land-ice fluxes, as standalone MPAS-Ocean does.

### Algorithm Design: Partly floating cells melt over their floating fraction

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Wetting and drying decides only where the ice floats:

- where there is no land ice, or the ice draft is below the bed, the
  floating mask and fraction are 0;
- elsewhere, the floating mask is 1 and the floating fraction keeps the
  value its input gave.

The input is the initial condition, the time-varying land-ice forcing or
glc. Each input that sets the floating fraction also sets the land-ice
pressure, which decides where the ice is grounded. A cell that begins to
float therefore gets its fraction from the same input. This applies in
standalone runs as in E3SM, with no option ([D6](#decisions)).

```{admonition} Rationale
Wetting and drying used to set the floating fraction to 1 wherever ice
floats. Partly floating cells then melted over their whole area. The melt
sent to glc is divided by glc's own floating fraction, so glc received melt
rates inflated by that ratio. Each import also restored glc's fractional
values until the next reset, so runs with import on and off diverged.
```

### Algorithm Design: A case can use grids and input files that E3SM does not list

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Case variables name the ocean's and MALI's input files by full path
([D2](#decisions)):

| Case variable              | File                                             |
|----------------------------|--------------------------------------------------|
| `MPASO_IC_FILE`            | the ocean's mesh and initial condition           |
| `MPASO_DECOMP_FILE_PREFIX` | the ocean's graph partitions, before the task count |
| `MALI_IC_FILE`             | MALI's mesh and initial condition                |
| `MALI_DECOMP_FILE_PREFIX`  | MALI's graph partitions, before the task count   |
| `MALI_DATAMODE_FILE`       | the thickness MALI reads in data mode            |
| `MPASO_INTERIOR_RESTORING_FILE` | the ocean's interior restoring, `tracersInteriorRestoringFields` |
| `MPASO_TIDAL_MASK_FILE`    | the ocean's tidal mask, `tidalInputMask`         |

When set, each of the first five replaces the file `buildnml` would choose
for a listed grid. The last two have no listed counterpart: when one is
set, `buildnml` writes an input stream that reads its field once at the
start, and adds its file to the input-data list ([D8](#decisions)).
For a grid `buildnml` does not list, the initial conditions and partitions
are required, and the data-mode file is required in data mode. `buildnml`
stops with an error naming any that are missing. A path may begin with
`$DIN_LOC_ROOT`, which CIME expands. With Albany, such a grid has no Albany
input of its own, so one must come from `SourceMods/src.mali`.

`GLC_GRID` accepts any name, as the other components' grids do
([D7](#decisions)).

The grid file is a `config_grids.xml` in the user-mods directory, which
CIME uses in place of E3SM's ([D5](#decisions)). It holds only:

- E3SM's `model_grid_defaults` and `required_gridmaps`;
- the model grid, with null atmosphere, land, river and wave grids;
- the `null` domain and the ocean's and MALI's domains, with no domain
  files;
- one gridmap between the ocean and MALI grids, with `GLC2OCN_FMAPNAME`,
  `GLC2OCN_SMAPNAME`, `OCN2GLC_SHELF_FMAPNAME` and `OCN2GLC_SHELF_SMAPNAME`,
  and the runoff maps only if runoff stays on.

MCT's reader of `seq_maps.rc` stops at lines of 256 characters. Map paths
outside inputdata must be short enough to fit.

### Algorithm Design: Every E3SM case with MALI initializes

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

MALI's E3SM namelist files drop `config_surface_air_temperature_lapse_rate`
and the `lapse` value of `config_surface_air_temperature_source`, which
MALI's Registry no longer has
([MALI-Dev/E3SM#169](https://github.com/MALI-Dev/E3SM/pull/169)).

### Algorithm Design: Experiment-specific configuration stays outside E3SM

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

A case is created from a compset long name and a user-mods directory. E3SM
reads from the user-mods directory:

- `config_grids.xml`, the grid file above;
- `shell_commands`, which set the case variables above, the runoff option,
  the run length and the coupling intervals;
- `user_nl_mpaso` and `user_nl_mali`;
- no `streams.ocean`: `buildnml` writes the ocean's input streams from the
  case variables. A case may still supply a whole `streams.ocean` in
  `SourceMods/src.mpaso` for output that `buildnml` does not write, which
  replaces `buildnml`'s file.

`user_nl_mpaso` sets every option whose E3SM default differs from the
standalone run's, to the standalone value, except
`config_use_bulk_wind_stress` and `config_bulk_wind_stress_interp_isotropic`,
which keep E3SM's values. It also sets the options whose E3SM defaults
exist only for listed grids: `config_dt`, `config_hmix_scaleWithMesh`,
`config_mom_del4` and `config_AM_mocStreamfunction_enable`. `user_nl_mali`
sets MALI's ice density to the one the ocean's initial condition used.

```{admonition} Rationale
E3SM's defaults differ from the Registry's for options that matter here,
GM and Redi among them, which E3SM turns on and which read `sphere_radius`.
Writing every such option keeps the E3SM and standalone runs on one
physics, whatever the standalone tasks later choose. E3SM's ocean takes the
coupler's wind stress through its bulk forcing, and with that off it stops
at its first time step.
```

The compsets are:

| MALI       | Compset long name                                              |
|------------|----------------------------------------------------------------|
| static     | `2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIASTATIC_SWAV`     |
| data mode  | `2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI%SIADATA_SWAV`       |
| prognostic | `2000_SATM_SLND_SICE_MPASO%PISMF_SROF_MALI_SWAV`               |

`MPASO%PISMF` with MALI turns on ice-shelf coupling through the coupler.
Prognostic MALI uses Albany, which needs the GNU compilers on Chrysalis.

### Algorithm Design: Existing configurations are unchanged

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Every new option defaults to the current behavior: the case variables are
empty, the runoff option is on, and the new namelist groups default to off.
The driver changes apply only without an atmosphere. The floating-fraction
change applies only with wetting and drying and land ice.

## Implementation

### Implementation: A prognostic ocean runs without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Branch `cpl/allow-ocean-without-atmosphere`
([E3SM-Ocean-Discussion/E3SM#158](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/158)):

- `cime_comp_mod.F90` stops only for prognostic sea ice or land without an
  atmosphere, and calls `cime_run_atmocn_fluxes` only with one;
- `seq_frac_init` maps the ocean fraction to the atmosphere grid, and
  `seq_hist_write` writes `o2x_ax` and `xao_ax`, only with an atmosphere.

### Implementation: Exchanged fluxes are conserved without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Branch `cpl/ocean-coupler-areas-from-glc-map`, on top of the runoff
option's branch: without an atmosphere, and when glc sends the ocean runoff
or ice-shelf fields, `component_init_aream` reads the ocean's coupler areas
from the `area_b` of `glc2ocn_fmapname`. It does so before sea ice takes
its areas from the ocean's. `seq_domain_areafactinit` computes the area
factors of masked cells too, wherever both areas are nonzero.

### Implementation: glc's runoff can be kept out of the ocean

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Branch `cpl/glc-runoff-to-ocean-option`:

- a case variable `GLC_RUNOFF_TO_OCN` (`TRUE` or `FALSE`, default `TRUE`,
  in `env_run.xml`) sets `glc_runoff_to_ocn` in `seq_infodata_inparm`,
  which `seq_infodata` reads, broadcasts, logs and returns as it does
  `glc_renormalize_smb`;
- `cime_comp_mod.F90` sets `glc_c2_ocn` only when `glc_runoff_to_ocn` is
  true;
- `component_init_aream` receives `glcshelf_c2_ocn`, so glc's coupler
  areas do not depend on runoff.

### Implementation: The ocean can use wetting and drying and an outflow

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Branch `ocn/wetting-drying-tidal-forcing-in-e3sm`
([E3SM-Ocean-Discussion/E3SM#159](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/159)): the two groups are added
to `build-namelist`, `build-namelist-section`, `build-namelist-group-list`,
`namelist_defaults_mpaso.xml` and `namelist_definition_mpaso.xml`.
`ocn_comp_mct.F` calls `ocn_tidal_forcing_build_array` in its run loop.

### Implementation: Partly floating cells melt over their floating fraction

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Branch `ocn/keep-floating-fraction-with-wetting-drying`
([E3SM-Ocean-Discussion/E3SM#160](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/160)):
`ocn_wetting_drying_update_land_ice` no longer sets the floating fraction
to 1 in floating cells.

### Implementation: A case can use grids and input files that E3SM does not list

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

- Branch `ocn/inputs-named-by-case-variables`
  ([E3SM-Ocean-Discussion/E3SM#161](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/161)) adds `MPASO_IC_FILE` and
  `MPASO_DECOMP_FILE_PREFIX` to MPAS-Ocean's `config_component.xml`,
  `buildnml` and `build-namelist`, and removes `GLC_GRID`'s valid values
  from the MCT driver's `config_component.xml`. A further commit adds
  `MPASO_INTERIOR_RESTORING_FILE` and `MPASO_TIDAL_MASK_FILE` to
  `config_component.xml` and `buildnml`. The generated `streams.ocean`
  gains the `interior_restoring` and `tidal_forcing_mask` input streams,
  each in the package that uses its field, and the input-data list gains
  the two files.
- Branch `mali/inputs-named-by-case-variables` adds the three MALI
  variables to MALI's `config_component.xml`, `buildnml` and
  `build-namelist`
  ([MALI-Dev/E3SM#214](https://github.com/MALI-Dev/E3SM/pull/214),
  [E3SM-Ocean-Discussion/E3SM#157](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/157)).

`build-namelist` reads the partition prefixes from the case, so its command
line is unchanged.

### Implementation: Every E3SM case with MALI initializes

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Branch `mali/remove-lapse-rate-from-namelist`
([MALI-Dev/E3SM#213](https://github.com/MALI-Dev/E3SM/pull/213),
[E3SM-Ocean-Discussion/E3SM#156](https://github.com/E3SM-Ocean-Discussion/E3SM/pull/156)).

### Implementation: Experiment-specific configuration stays outside E3SM

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

The `case_config` step of [MISOMIP Inputs for E3SM](misomip_e3sm_init.md)
writes the user-mods directory. It reproduces the first run's hand-built
case, with a minimal grid file.

### Implementation: Existing configurations are unchanged

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Each change is its own branch off FAnSSIE, with its own pull request to
FAnSSIE. The coupler-area change builds on the runoff option. MALI's two
branches start from the MALI-Dev `develop` commit that FAnSSIE merged, so
each also has a pull request to MALI-Dev.

## Testing

### Testing and Validation: A prognostic ocean runs without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: 4 km Ocean0 ran 5 days with a static MALI. In the daily coupler
history, all 40 ocean inputs not from glc are zero.

### Testing and Validation: Exchanged fluxes are conserved without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: in 4 km Ocean0, the ocean's area factors in the coupler log range
from $1 + 5\times10^{-8}$ to $1 + 3.8\times10^{-5}$, so every cell is
corrected, those with land ice included. The E3SM tests without ice-shelf
coupling to glc, including ocean cavities with internal or prescribed melt,
are bit for bit. With ice-shelf coupling to MALI, the exchanged ice-shelf
fields change by up to $3\times10^{-8}$ relative.

To do: the ocean's melt and the melt glc receives agree to round-off,
computed from each model's own output. The coupler budgets cannot show
this, since they use coupler areas on both sides.

### Testing and Validation: glc's runoff can be kept out of the ocean

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: 4 km Ocean0 with the option off and no runoff maps in its grid file
initializes no runoff mappers. It is bit for bit over 5 days with the same
case with the option on and a stand-in runoff map, since static MALI has no
runoff. Glc's coupler areas still come from the map.

To do: cases with the default are bit for bit.

### Testing and Validation: The ocean can use wetting and drying and an outflow

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: the first run used both. E3SM's namelist comparison reports the two
new groups and nothing else.

### Testing and Validation: Partly floating cells melt over their floating fraction

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: 4 km Ocean0 with import on and off is bit for bit over 5 days. The
imported pressure, land-ice fraction and floating fraction equal the
initial condition bit for bit. Day-5 melt drops from 50.3 to
48.5 Gt yr⁻¹, nearly all in the 174 partly floating cells. In `fanssie_pr`,
only the ISOMIP+ forward steps change.

### Testing and Validation: A case can use grids and input files that E3SM does not list

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: the first run used all four required variables and a user grid file.
A case from the 118-line grid file in a user-mods directory sets up with
the right grids and maps. `buildnml` stops with its error when the
variables are missing. Values that begin with `$DIN_LOC_ROOT` expand in the
input-data lists and namelists.

To do: 4 km Ocean0 with the two forcing variables and no `streams.ocean` is
bit for bit with the first run, and its input-data list holds the forcing
file.

### Testing and Validation: Every E3SM case with MALI initializes

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: `ERS_Vmct.ne30pg2_r05_IcoswISC30E3r5_gis4to40.MALISIA` fails at
initialization on FAnSSIE and passes with the change.

### Testing and Validation: Experiment-specific configuration stays outside E3SM

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Done: 4 km Ocean0 from the user-mods directory that Polaris writes is bit
for bit over 5 days with a case written by hand from the same options.

To do: each other experiment's case is created from its user-mods directory
alone and passes the checks of the first run.

### Testing and Validation: Existing configurations are unchanged

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Each branch runs `fanssie_pr` against a baseline from FAnSSIE, and three
E3SM tests on Chrysalis with Intel:
`ERS_Ld5.T62_oQU120.CMPASO-NYF`,
`ERS_Vmct_Ld5.TL319_oQU240wLI_ais8to30.GMPAS-JRA1p5-DIB-PISMF-SIS.mpaso-ocn_glcshelf`
and `ERS_Vmct.ne30pg2_r05_IcoswISC30E3r5_gis4to40.MALISIA`. Done for the
first six branches together: all bit for bit, with namelist changes only
from the new groups.

## Decisions

### D1: Ocean albedos are still computed without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Only the atmosphere–ocean fluxes are skipped. Albedos only scale shortwave,
which is zero.

Rejected: skipping albedos too, a larger change for no effect.

### D2: Case variables hold full paths

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Each variable names one file, or a partition prefix, by full path. A path
may begin with `$DIN_LOC_ROOT`.

Rejected:

- a prefix and a date relative to the grid's inputdata directory, as
  `buildnml` stores them internally, which cannot name files before they
  are on inputdata;
- partitions through `config_block_decomp_file_prefix` in `user_nl_*`,
  which works for MPAS-Ocean but splits a case's files between two
  mechanisms.

### D3: A driver option turns off glc's runoff to the ocean

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Rejected:

- `GLC_TWO_WAY_COUPLING`, whose description mentions calving fluxes but
  which, for MALI, only selects the surface-mass-balance source;
- a MALI option that sends zero runoff, which would still need runoff maps;
- runoff left on with a stand-in map, as in the first run, which adds
  calving to the ocean once MALI calves.

### D4: The ocean's coupler areas come from the glc-to-ocean map without an atmosphere

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Rejected: the ocean's model areas, which leave conservation off by up to
$4\times10^{-5}$, and rescaling the ocean's areas in Polaris, which would
change the ocean's own physics.

### D5: The grid file is a minimal `config_grids.xml` in the user-mods directory

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

CIME uses a `config_grids.xml` from a user-mods directory, or one given to
`create_newcase --gridfile`, in place of E3SM's whole file. A minimal file
holds only what one case needs.

Rejected:

- grid entries in E3SM, which the MISOMIP plan rejects to keep the
  experiments' configuration in one place;
- a full copy of E3SM's 7,500-line file with the new grids added, which
  ties each user-mods directory to one E3SM version;
- a CIME change that merges a user grid file with E3SM's, which belongs
  upstream in CIME.

### D6: Wetting and drying keeps the input's floating fraction, with no option

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Standalone and E3SM runs take the same fraction, so comparing them tests
the coupling.

Rejected:

- applying the 0-or-1 fraction right after each import, which makes import
  on and off agree but keeps glc's inflated melt rates;
- an option that keeps the 0-or-1 fraction in standalone runs, which would
  make standalone and E3SM runs differ.

### D7: `GLC_GRID` accepts any name

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Rejected: adding each new glc grid to the list, which puts grid entries in
E3SM.

### D8: `buildnml` writes the ocean's interior-restoring and tidal-mask streams

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

Two case variables name the files, and `buildnml` writes the streams and
lists the files.

Rejected: a whole `streams.ocean` in each case's user-mods directory. It
must be written per case, since it holds the case name and the paths of the
initial condition. CIME does not download files named only there.

### D9: Masked cells get area corrections too

Date last modified: 2026/10/31

Contributors: Xylar Asay-Davis, Claude

The coupler corrects every cell whose model and coupler areas are both
nonzero, masked or not, for every component.

Rejected:

- the same, only for the ocean with ice-shelf coupling on, which leaves
  every other configuration bit for bit. The general rule turned out to
  change only cases with ice-shelf coupling to MALI;
- MPAS-Ocean's coupler mask set to 1 under the ice, which would also open
  the cavities to the atmosphere and sea ice;
- the error left in place, up to $4\times10^{-5}$ in these cases.
