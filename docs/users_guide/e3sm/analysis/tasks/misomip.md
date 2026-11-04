(e3sm-analysis-misomip-tasks)=

# MISOMIP Analysis Tasks

The `e3sm/analysis` `misomip` tasks analyze the ISOMIP+ experiments
Ocean0–4 and the MISOMIP1 experiments IceOcean1r and IceOcean1ra run in
E3SM with MPAS-Ocean coupled to MALI, from the inputs and case
configurations of the {ref}`e3sm-init-misomip-tasks`, and the standalone
MPAS-Ocean runs on the same inputs.  They compare E3SM with the standalone
run and check the coupler's budgets for the melt the two models exchange.

## Tasks

There is a task for each experiment on each pair of ocean and MALI meshes:

- `e3sm/analysis/<mesh_name>/misomip/<experiment>`

where `<mesh_name>` is `misomip-o4km-li1km` or `misomip-o2km-li1km` and
`<experiment>` is one of `ocean0` through `ocean4`, `iceocean1r` or
`iceocean1ra`.  IceOcean1ra continues from IceOcean1r's restart, so its
task reads IceOcean1r's initial conditions and needs IceOcean1r's run in
the config too.

## Pointing the tasks at runs

A config file names the runs.  An E3SM run is given by its case directory,
from which Polaris reads the run and archive directories and the streams
the ocean wrote.  A standalone run is given by the work directory of the
`ocean/planar/misomip/<mesh_name>/<experiment>/forward` step.  Either may
be left out:

```cfg
[misomip_analysis]
# the years analyzed: each run contributes every monthly mean it has in
# this range
start_year = 1
end_year = 1

[misomip_analysis_misomip-o4km-li1km]
ocean0_e3sm_case = /home/<user>/e3sm_cases/misomip/<case>
ocean0_standalone = <work dir>/ocean/planar/misomip/misomip-o4km-li1km/ocean0/forward
```

Set up a task with this config:

```bash
polaris setup -t e3sm/analysis/misomip-o4km-li1km/misomip/ocean0 \
    -w <analysis work dir> -f analysis.cfg
```

The steps are named for the months each run has, such as
`e3sm/diagnostics_0001-01_0001-12`, so setting up again after a run has
gone further adds new steps rather than reusing the old ones.  A month
missing between the first and last month of a run is an error.

## What the tasks compute

For each run, from its monthly means:

- the total melt flux and the mean melt rate over the floating ice base,
  over all of it and where the draft is deeper than 300 m, and the mean
  thermal driving and friction velocity;
- the ranges under the ice of the barotropic streamfunction and of the
  overturning streamfunction across lines of constant $x$;
- the strongest gyre in the open ocean, the barotropic streamfunction of
  largest magnitude between the ice front and the restoring region;
- the open ocean's mean SSH there above the restoring region's, the height
  its density implies, and the residual, which is the excess pressure at
  the seafloor as a height of water;
- the part of that residual that the gyres make, the geostrophic height of
  the flow in a slab above the seafloor (`bottom_slab_thickness`, 100 m by
  default), and the rest, a uniform offset from the restoring region.
  Ageostrophic flow near the seafloor and the choice of slab make the split
  good to about 0.1–0.2 cm;
- the ocean's volume and mean temperature and salinity;
- with a thin film, the area of dry columns under grounded ice and the
  open ocean's mean sea-surface height;
- in an E3SM run, the share of MALI's floating area in cells next to the
  grounding line that the ocean holds at the thin film, and an estimate of
  the share of melt missed there;
- time-mean maps of melt rate, thermal and haline driving, friction
  velocity, the barotropic streamfunction, bottom temperature and
  salinity and SSH, sections of temperature and salinity at
  $y = 40$ km and $x = 520$ km, the overturning streamfunction, and the
  melt rate in bins of draft.

The time means are over the last 6 months of Ocean0, as the protocol's
tuning does, and the last 12 months of the other experiments, or all of a
shorter run.  Partly floating cells melt only over their floating fraction,
so means over the ice base are weighted by floating area.

For an E3SM run, MALI's history gives the ice sheet's volume, volume above
flotation, grounded area and grounding line along $y = 40$ km, from MALI's
thickness and bed with the densities in its namelist.  A map shows the
ocean's floating fraction with MALI's grounding line at the start and end
of the period drawn over it.

With both runs, a `comparison` step overlays their monthly and daily time
series and maps the E3SM run's difference from the standalone run in each
field, averaged over the months both have.  It writes the RMS and largest
difference of each field to `map_differences.csv`.

With `BUDGETS=TRUE` in the E3SM case, a `conservation` step reads the
coupler's daily (with `budget_daily = 1` in `user_nl_cpl`), monthly and
annual budgets from its log and plots the ocean's and
glc's columns of the ice-shelf water (`wpolar`) and heat (`hpolar`) rows
and their sum, as totals.  `exchange_residuals.csv` lists the sum relative
to the ocean's column for each budget.  The coupler prints global means to
8 decimals, which limits how small a residual it can show.  The monthly
water plot also shows the ocean's own melt and the frazil it forms under
the ice shelf, from its monthly means: the ocean's column is their sum, so
frazil the coupler doesn't pass to glc shows as a residual.

At an initial start, the driver skips the ocean's first coupling interval.
The coupler still books the ocean's initial export for that interval in
the ocean's column, and glc never receives it, so the first daily, monthly
and annual budgets of a run don't close by that amount.  `exchange_residuals.csv` marks them
in its `initial_start` column, and the step's log gives the largest
residual of the others.  Daily budgets show whether the rest of the first
month closes.

## Coupled experiments

In IceOcean1r and IceOcean1ra, where MALI evolves, a `model_exchange` step
compares the net mass flux out of the ice shelves that the ocean sends with
the melt MALI applies, each from its own model's output.  The ocean sends
its melt less the frazil under the land ice, and only where MALI floats
more than `config_glc_ice_shelf_coupling_min_floating_fraction`.  MALI's
global statistics give the melt it applies in each time step.  MALI's
step over each glc coupling interval applies the coupler's average of what
the ocean sent over the same interval, so each month of the ocean's means
is compared with the same month in MALI.  Where the case writes the
ocean's daily means, days are compared too, and the step's log gives the
RMS difference with MALI 0, 1 and 2 intervals later, which confirms the
alignment.  Without
`landIceFreshwaterFluxNotSentToGlc` in the ocean's output, the flux sent
is estimated from the floating fraction MALI gives the ocean, and the plots
say so.  `model_exchange.csv` lists every period, and a period that
contains the initial start, or that MALI's steps do not yet cover, is
reported apart.

An `ice_sheet_comparison` step plots MALI's grounding line on the
centerline, volume above flotation and grounded area against standalone
MALI runs of the matching MISMIP+ experiment, Ice1r or Ice1ra, and the
range of the entries of
[Cornford et al. (2020)](https://doi.org/10.5194/tc-14-2283-2020), against
the years since each experiment started.  The volume above flotation and
grounded area come from each MALI run's global statistics.  MALI writes its
history only at the end of a step, and the MISMIP+ runs take steps of
several months, so a run with steps forced to end on each month gives the
grounding line over the first years.  The primary reference is such a run
with MALI built from the coupled run's source, and the coupled run less it
is the main difference shown.  Runs with another MALI version are drawn as
secondary lines:

```cfg
[misomip_analysis_mismip_plus]
cornford2020_dir = <work dir>/landice/mismip_plus/cornford2020
ice1r_coupled_mali_monthly_forward = <work dir of a run with the coupled run's MALI and monthly-forced steps>
ice1r_forward = <work dir>/landice/mismip_plus/1km/ice1r/forward
ice1r_monthly_forward = <work dir of a run with monthly-forced steps>
```

To build MALI from the coupled run's source, set up the MISMIP+ task with
`--build --branch <E3SM source of the coupled run>`.

## Comparing experiments and resolutions

Two more tasks compare runs named in the same config, one kind of run at a
time:

- `e3sm/analysis/<mesh_name>/misomip/experiments` overlays the time series
  of every experiment with runs on that mesh;
- `e3sm/analysis/misomip/resolutions/<experiment>` overlays the time series
  of the experiment at 4 and 2 km and draws its time-mean maps side by
  side, each on its own mesh.

They share the diagnostics steps of the experiment tasks, so setting them
up together computes each run's diagnostics once.

## Published results

For Ocean0–2, a `published` step compares the runs with the COM results of
[Yung et al. (2026)](https://doi.org/10.5194/tc-20-2053-2026).  A shared
step, `e3sm/analysis/misomip/yung2026/<experiment>`, downloads each model's
submission for the experiment from the Open Science Framework into the
ocean database, at setup, and reduces it.  Each model's files are licensed
CC-BY 4.0 and the step's `README` gives the paper's citation and each
model's registration.  For COCO's and NEMO-CNRS's Ocean0, which have
several runs, the file is the one tuned to the protocol's target melt rate.

The step plots the runs' time series over the ensemble's range, with
MPAS-Ocean's 2019 entry marked, the melt rate by draft, the streamfunctions'
strengths against the mean melt rate, and the runs' time-mean melt rate
beside the ensemble's mean.  The runs use E3SM's physics, not the protocol's
COM physics, and are labeled as such: the comparison places them among the
COM models rather than validating them.

## Output on the protocol's grid

Set `write_protocol_fields = True` to also write each run's monthly means
on the output grid of the MISOMIP protocol
([Asay-Davis et al. 2016](https://doi.org/10.5194/gmd-9-2471-2016),
Sect. 3.3), 2 km in $x$ and $y$ and 5 m in $z$.  A `protocol_map` step
makes a conservative map from the run's mesh to the grid, and a
`protocol_fields_<months>` step writes `<Experiment>_TYP_Polaris-<kind>.nc`
with the protocol's variables.  Fields under the ice are averaged over the
floating area in each grid cell and the others over its ocean area.  The
overturning streamfunction is computed across each of the grid's lines of
constant $x$, and the sections take the nearest cell to each point of the
grid.  The tasks don't plot these files.

## Publishing

Each task's `publish` step copies its plots into a gallery under
`[misomip_analysis] output_path`, in a directory for the mesh and the
experiment.  Set `copy_netcdf = True` to publish the data of each plot as
well.
