(ocean-analysis)=

# analysis

The `analysis` task group analyzes a simulation that has **already been run**,
rather than running one.  Its tasks are pointed at a completed Omega
simulation through a config file and produce plots and the netCDF data behind
them.

This makes it unlike the other pages in this section.  There is no mesh, no
vertical grid, no initial condition, no forcing and no time step to describe,
because no model is run: everything the analysis needs it reads from the
simulation's own output.

Analysis products are added over time; {ref}`ocean-analysis-products` lists
what is available so far.

## supported models

**Omega only.**  The analysis locates a simulation's output by reading the
simulation's own Omega configuration file, which is also how it learns the
mesh, the vertical coordinate and the output streams.  MPAS-Ocean describes
its output with namelists and streams files instead, and reading those would
require a translator into the same form, which does not exist.  A setup with
`[ocean] model` set to `mpas-ocean` reports that rather than failing later.

Neither an Omega nor an MPAS-Ocean build is needed, since no model is run.

(ocean-analysis-config)=

## pointing the analysis at a simulation

The user supplies a config file describing the simulation to analyze.  In the
common case it needs three things: where the simulation is, and the two ranges
of simulation years to analyze.

```cfg
[ocean_analysis]

# the simulation's own Omega configuration file
omega_config_filename = /path/to/run/omega.yml

# a short name used in plot titles and file names
simulation_name = my_run


[ocean_analysis_climatology]

# the first and last year of the climatology, inclusive
start_year = 21
end_year = 40


[ocean_analysis_time_series]

# the first and last year of the time series, inclusive
start_year = 1
end_year = 60
```

`omega_config_filename` is **required** and is the only description of where
the simulation's output lives.  Polaris reads the mesh, the vertical
coordinate and the output streams from it, so none of them have to be restated
by hand.  An Omega run always writes this file; it is in the run directory.

The two year ranges are independent.  The climatology range governs the
map-view products and the MOC; the time-series range governs the global
statistics and ocean heat content time series.  Changing one does not disturb
the other.

A few further options in `[ocean_analysis]` are worth knowing about, though
most simulations need none of them:

`simulation_path`
: The directory that relative file names in the Omega configuration are
  resolved against.  Defaults to the directory containing that file, which is
  the run directory.  Set it if the output has moved since the run.

`mesh_filename`, `vert_coord_filename`
: The horizontal mesh and vertical-coordinate files, absolute or relative to
  `simulation_path`.  Each defaults to the file the Omega configuration names.
  Set one if it has moved.

`output_path`
: Where plots and their netCDF files are published for browsing.  Defaults to
  `<work_dir>/analysis_output`.  Point it somewhere web-servable to share the
  results.

The remaining sections --- `[ocean_analysis_climatology]`,
`[ocean_analysis_ohc]`, `[ocean_analysis_time_series]` and
`[ocean_analysis_moc]` --- describe what each product computes and plots.  See
the comments in `polaris/tasks/ocean/analysis/analysis.cfg` for the full list
with its defaults.

## running the analysis

```bash
polaris suite -c ocean -t omega_analysis -w <work_dir> -f analysis.cfg \
    --model omega
polaris serial
```

Two things about that command differ from most Polaris suites:

- **`--model omega` is required** (or `model = omega` in an `[ocean]` section
  of the config file).  Polaris normally detects the model by finding a build,
  and there is no build here.
- **No `-p`/`--component_path`**, for the same reason.

The suite can be run on the machine where the simulation output lives, without
copying that output.

To run a single product rather than the whole suite, set up that task on its
own:

```bash
polaris setup -t ocean/analysis/global_stats -w <work_dir> -f analysis.cfg \
    --model omega
```

## where the results go

Two directory trees, with two audiences.

The **work directory** is built for predictability and for finding a step's
log, not for browsing.  It follows one rule, `<product>/<period>`, with a
third level only for the one product that is chunked by field group:

```none
ocean/analysis/
├── climatology/0021-0040/                (shared: ncclimo)
├── climatology_maps/0021-0040/
│   ├── temperature/ salinity/ velocity/
│   ├── ssh/ mixed_layer_depth/
│   └── heat_content/
├── heat_content_series/0001-0060/
├── global_stats/0001-0060/
└── moc/0021-0040/
```

The range in each path is the zero-padded first and last year, matching the
convention `ncclimo` uses in its own file names.

The **staging tree** under `output_path` is where results are published for
browsing.  It is shallow, with descriptive file names that carry the product,
the field, the season, the vertical reduction and the range, so that it is
easy to archive, to serve and to search:

```none
<output_path>/
├── index.html                                      (the gallery groups)
├── manifest.json                                   (what was published)
├── galleries/
│   └── climatology_maps_temperature_0021-0040.html
├── plots/
│   ├── climatology_maps_temperature_ANN_-100m_0021-0040.png
│   └── climatology_maps_temperature_ANN_-100m_0021-0040.nc
└── thumbnails/
    └── climatology_maps_temperature_ANN_-100m_0021-0040.jpg
```

`output_path` defaults to `analysis_output` at the root of the work
directory.  Point it somewhere a web server can reach if the results are to be
shared.

The plots and their netCDF files are **symlinks** into the step that made
them, so each file has one owner and the staging tree is a view rather than a
second copy.  Copying the tree to another machine therefore needs
`cp -rL`, or `rsync -L`, to follow them.

(ocean-analysis-gallery)=

## the published gallery

The suite's last step, `publish`, collects what every other step made,
publishes it into the staging tree, renders a thumbnail for each plot and
generates a static gallery over the result.  Open `index.html` in a browser,
from the filesystem or over a web server; there is nothing to build and no
JavaScript, and the pages look the same either way.

The landing page shows each **gallery group** --- a product for one range of
years, such as "Climatology maps, years 0021-0040" --- with one thumbnail per
gallery within it.  A gallery page shows every plot in that gallery, in the
order the step made them, and clicking a thumbnail opens the full image with
its netCDF file linked beside it.  Every page carries the simulation name, the
ranges and the Polaris provenance, so a page found later can be traced back to
what produced it.

Three config options control what a page costs to load, which matters on a
portal that throttles:

```cfg
[ocean_analysis]

# the box, in pixels, each thumbnail is scaled to fit inside
thumbnail_size = 320, 240

# jpeg or webp; webp is a third to a half smaller at the same quality
thumbnail_format = jpeg

# 1 to 100; above about 80 the bytes grow quickly and it looks no better
thumbnail_quality = 75
```

Reducing `thumbnail_size` is the first thing to try if gallery pages are slow
to appear.  Thumbnails are the only images a page fetches, they are one to two
hundred times smaller than the plots they stand for, and a browser fetches
only the ones that have been scrolled to.

Publishing again is cheap and safe.  A thumbnail is regenerated only when it
is missing or older than its plot, so adding one product to an analysis costs
one thumbnail rather than all of them, and results from different ranges
coexist because the range is in every published name.

A step that ran but made no products publishes nothing, and that is not an
error: every step that publishes leaves a manifest, with nothing in it when it
made nothing, and the gallery simply has nothing from that step in it.  The
`publish` step's log names those steps, since the gallery cannot.  A step that has not run at all is
different.  `publish` declares every step's manifest as an input and every
such step as a dependency, so Polaris refuses to run it and names what is
missing.

## analyzing the same simulation more than once

Every product lives at a directory named for the range it covers, and that is
what makes re-analysis behave sensibly:

- **A new range recomputes.**  It creates steps in directories that have never
  run, so they run.  Nothing has to be deleted and no flag has to be passed.
- **An unchanged range recomputes nothing.**  Those directories are already
  complete.
- **An earlier range's results survive.**  Two ranges never share a directory,
  so analyzing years 21--40 leaves the results for years 1--20 in place.  This
  also makes it impossible to get a plot labelled with one range whose
  contents came from another.

Re-running `polaris setup` rewrites the suite pickle at the root of the work
directory, so the range most recently set up is the one `polaris serial` will
run.  Step directories from earlier ranges are untouched, so returning to an
earlier range means re-running setup with that range's config.

Analyzing many ranges accumulates step directories and intermediate files,
which is what makes re-analyzing an earlier range nearly free.  It is worth
knowing about on a filesystem with a quota; the climatology files dominate.

(ocean-analysis-products)=

## products

The suite is being built up product by product.  What exists so far:

| task | product | status |
| --- | --- | --- |
| `climatology_maps` | map-view climatologies, one step per field group | {ref}`available <ocean-analysis-climatology-maps>` |
| `global_stats` | time series of the simulation's global statistics | {ref}`available <ocean-analysis-global-stats>` |
| `heat_content_series` | time series of globally integrated ocean heat content | not yet implemented |
| `moc` | latitude-elevation plot of the meridional overturning circulation | not yet implemented |
| `publish` | the staging tree and the {ref}`gallery <ocean-analysis-gallery>` over it | implemented |

A task that is not yet implemented resolves the simulation files it will read,
links them into its work directory and reports them in its log, which is
enough to check that a simulation is being located correctly.  No step
describes its products in a manifest yet, so `publish` generates an empty
gallery.

The `moc` task additionally depends on a diagnostic that Omega computes in
situ and does not yet provide.  A simulation without it is an ordinary case:
the step reports that no MOC output was written and produces nothing, rather
than failing the suite.

(ocean-analysis-climatology-maps)=

### climatology maps

The `climatology_maps` task computes a climatology of the simulation's
monthly-mean output and plots global maps from it, on the native MPAS mesh.
Nothing is remapped anywhere in the analysis.

It has a **shared climatology step** and then **one step per field group**.
The climatology runs once for a range of years no matter how many field
groups read it, and the groups are `temperature`, `salinity`, `velocity`,
`ssh`, `mixed_layer_depth` and `heat_content`.  A group is the unit of work
so that adding a field costs that field and not the others.

#### the climatology

The climatology is computed with `ncclimo` from the NCO package, which is what
the rest of the E3SM post-processing workflow uses, so that these
climatologies are comparable with the ones zppy produces.  It writes the
twelve monthly climatologies and one file per season in `seasons`, into
`ocean/analysis/climatology/<range>/`.

Two conventions are worth knowing:

- Seasons are weighted by the length of each month in the simulation's own
  calendar, and the annual mean is the same weighting over all twelve months.
- `DJF` takes its December from the same calendar year as its January and
  February, so every year in the range contributes exactly one December and
  no data from outside the range are needed.  This is what MPAS-Analysis
  does.

Only the variables the analysis needs are averaged, so the cost scales with
what is being plotted rather than with the size of the monthly means.  A
variable the simulation did not write is reported in the step's log and left
out.

#### the maps

Each field group's step writes, for every combination of season, field and
vertical reduction it was asked for, a PNG and a netCDF file with the same
base name holding exactly what was plotted:

```none
temperature_ANN_top.png     temperature_ANN_top.nc
temperature_DJF_bottom.png  temperature_DJF_bottom.nc
ssh_ANN.png                 ssh_ANN.nc
```

A field with no vertical dimension, such as `ssh`, is already a map, so its
files carry no reduction label.  The netCDF files carry the simulation name,
the field, the season, the vertical reduction and the range of years as
global attributes, so a plot cannot be mistaken for a different one.

#### the config options that govern it

All of these are in `[ocean_analysis_climatology]`:

`start_year`, `end_year`
: The range of years the climatology covers.  It is also the directory the
  results land in, so a different range recomputes rather than overwriting.

`seasons`
: The seasons to compute, beyond the twelve monthly climatologies, which are
  always computed.

`plot_seasons`
: The seasons to plot, which may include the monthly climatologies as `JAN`
  through `DEC`.  Every season here has to be one the climatology computed.

`fields`
: The fields to map, using MPAS-Ocean names whatever model produced the
  output.  This is what decides which field group steps exist.

`elevations`
: How to reduce a field with a vertical dimension to a map.  `top` and
  `bottom` are the topmost and bottommost valid layer of each column, so they
  respect ice-shelf cavities and partial bottom cells; `k<index>` is a fixed,
  zero-based vertical index, masked in columns where it falls outside the
  valid range; and a number is an elevation in m, positive up, so `-100.0` is
  100 m below the sea surface.

An elevation is interpolated linearly between the midpoints of the two layers
it falls between, using the layer elevations the simulation wrote.  Because
the input is a climatology, a `-100.0` map is a map on the climatological-mean
position of the -100 m surface rather than the time mean of maps on its
instantaneous position; the two differ only where the seasonal cycle in layer
thickness is large.

Two ends of a column are worth knowing about.  Above the midpoint of its
topmost layer the topmost value is used rather than the map being masked,
which is what makes `0.0` and `-5.0` mean what a near-surface map is asked
for; likewise below the midpoint of the bottommost layer, down to the
seafloor.  Below the seafloor the map is masked, so a column with partial
bottom cells ending at -97 m is blank at `-100.0` while `k9` still has a value
in it.

The colors come from one config section per field, so the color map and its
range can be set for each field independently.  A section is named for its
field with the field name in lower case with underscores, so `velocityZonal`
is configured by `[ocean_analysis_map_velocity_zonal]`.

#### what is not there yet

Two fields in the config file are asked for and reported as skipped rather
than silently dropped.  Each says so in the step's log:

- **`velocityZonal` and `velocityMeridional`** are not written by Omega yet.
  Polaris does not reconstruct them from the edge-normal velocity; the
  reconstruction belongs in the model, where it costs nothing in accuracy.
- **`mixedLayerDepth`** is likewise a diagnostic Omega does not compute yet.

The `heat_content` field group exists but derives nothing yet, so it produces
no maps.

(ocean-analysis-global-stats)=

### global statistics time series

Omega's `GlobalStats` analysis group reduces each field it is given to a
handful of numbers per output time --- the global mean, minimum, maximum and
standard deviation.  The `global_stats` task plots those against time, which
is the cheapest look at whether a simulation is drifting.

For each field it produces two files in
`ocean/analysis/global_stats/<range>/`:

`<field>.png`
: Two panels sharing a time axis in simulation years.  The upper one shows
  the statistics themselves, with the standard deviation as a shaded envelope
  around the mean.  The lower one shows the change in each statistic since
  the beginning of the series, since drift is usually what the reader is
  looking for and it is easy to miss at the scale of the absolute values.

`<field>.nc`
: Exactly the data that were plotted --- one variable per statistic, the time
  axis in simulation years, and the field, the statistics, the simulation
  name and the year range as global attributes.  It is there so the numbers
  can be inspected, compared against another tool, or re-plotted without
  re-reading the simulation.

Two options in `[ocean_analysis_time_series]` govern it, alongside the
`start_year` and `end_year` that every time series shares:

`fields`
: The fields to plot, using MPAS-Ocean (Polaris standard) names.  Leave it
  empty to plot every field the simulation wrote statistics for.

`stats`
: The statistics to plot for each field: any of `mean`, `min`, `max` and
  `std`.

**A field or statistic the simulation did not write is skipped with a message
in the step's log, not treated as an error.**  The defaults describe what we
would like to see, and any given simulation will have written some subset of
it --- which is no more under the user's control than it is under ours.  A
field with no surviving statistics is dropped entirely.  Only a file with
*none* of the requested variables stops the step, since that usually means
the year range does not overlap the simulation rather than that a variable is
missing.

Omega can write these statistics either as snapshots or as time means over a
period it is configured with, and it names the variables differently in the
two cases.  Polaris reads the simulation's Omega configuration to find out
which it wrote, so this needs no option of its own.

## troubleshooting

**`The data set has no zMid, zInterface`.**  The simulation did not write the
elevation of its layers, which every map at an elevation is a position in.
Polaris cannot reconstruct it: geometric thickness is derived from
pseudo-thickness through specific volume, and the monthly mean of that product
is not the product of the monthly means.  A run without it is out of spec
rather than merely configured without a field.

**`invalid interpolation syntax`** while reading the config file.  Polaris
config files use extended interpolation, so a bare `$` in a value is an error.
File-name templates containing `$Y` and `$M` belong in the simulation's Omega
configuration, not in a Polaris config file, and there is no option that takes
one.

**Missing input files at setup.**  The analysis checks that every file it will
read exists before anything runs, and reports the years and months that are
absent together with the Omega stream that named them.  The usual cause is a
year range that reaches beyond the simulation.

**`Could not detect ocean model`.**  `--model omega` was not passed and there
is no `[ocean] model` option in the config file.
