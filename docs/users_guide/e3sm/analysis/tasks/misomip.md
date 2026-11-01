(e3sm-analysis-misomip-tasks)=

# MISOMIP Analysis Tasks

The `e3sm/analysis` `misomip` tasks analyze the ISOMIP+ experiments
Ocean0–4 run in E3SM with MPAS-Ocean coupled to MALI, from the inputs and
case configurations of the {ref}`e3sm-init-misomip-tasks`, and the
standalone MPAS-Ocean runs on the same inputs.  They compare E3SM with the
standalone run and check the coupler's budgets for the melt the two models
exchange.

## Tasks

There is a task for each experiment on each pair of ocean and MALI meshes:

- `e3sm/analysis/<mesh_name>/misomip/<experiment>`

where `<mesh_name>` is `misomip-o4km-li1km` or `misomip-o2km-li1km` and
`<experiment>` is one of `ocean0` through `ocean4`.

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
- the ocean's volume and mean temperature and salinity;
- with a thin film, the area of dry columns under grounded ice and the
  open ocean's mean sea-surface height;
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
coupler's monthly and annual budgets from its log and plots the ocean's and
glc's columns of the ice-shelf water (`wpolar`) and heat (`hpolar`) rows
and their sum, as totals.  `exchange_residuals.csv` lists the sum relative
to the ocean's column for each budget.  The coupler prints global means to
8 decimals, which limits how small a residual it can show.

## Publishing

Each task's `publish` step copies its plots into a gallery under
`[misomip_analysis] output_path`, in a directory for the mesh and the
experiment.  Set `copy_netcdf = True` to publish the data of each plot as
well.
