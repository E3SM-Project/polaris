# Fleshing out the `init` Step

What we are adding here are details that are pretty specific to this particular
category of tasks: its vertical coordinate and initial condition.  It isn't
worth worrying too much about these details, as things will be different
for other types of tests and tasks.  It is just provided for completeness and
to provide some step-by-step explanation.  And it's necessary to have some
sort of vertical mesh and initial condition in order to be able to run
MPAS-Ocean and analyze the results in subsequentt steps.

## Creating a vertical coordinate

Ocean tasks typically need to define a vertical coordinate as we will
discuss here.  Land ice tasks use a different approach to creating
vertical coordinates, so this section will not apply to those tasks.
Returning to the `run()` method in the `init` step, the code
snippet below is an example of how to make use of the
{ref}`dev-ocean-framework-vertical` to create the vertical coordinate:

```bash
$ vim polaris/tasks/ocean/my_overflow/init.py
```
```{code-block} python
:emphasize-lines: 1-2, 8, 21-43

import numpy as np
import xarray as xr

...

from polaris import Step
from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.vertical import init_vertical_coord


class Init(Step):

    ...

    def run(self):

        ...

        write_netcdf(ds_mesh, 'culled_mesh.nc')

        max_bottom_depth = section.getfloat('max_bottom_depth')
        shelf_depth = section.getfloat('shelf_depth')
        x_slope = section.getfloat('x_slope')
        l_slope = section.getfloat('l_slope')

        ds = ds_mesh.copy()

        # Form a continental shelf-like bathymetry
        ds['bottomDepth'] = shelf_depth + 0.5 * (
            max_bottom_depth - shelf_depth
        ) * (
            1.0
            + np.tanh(
                (ds.xCell - ds.xCell.min() - x_slope * 1.0e3)
                / (l_slope * 1.0e3)
            )
        )

        # ssh is zero
        ds['ssh'] = xr.zeros_like(ds.xCell)

        init_vertical_coord(config, ds)
        write_netcdf(ds, 'vert_coord.nc')

```

This part of the step, too, relies on config options, this time from the
`vertical_grid` section (see {ref}`dev-ocean-framework-vertical` for more on
this):

Now we add the config options we need to the config file:

```bash
$ vim polaris/tasks/ocean/my_overflow/my_overflow.cfg
```
```{code-block} cfg
:emphasize-lines: 1-17, 27-37

# Options related to the vertical grid
[vertical_grid]

# Depth of the bottom of the ocean (m)
bottom_depth = 2000.0

# Number of vertical levels
vert_levels = 60

# The type of vertical grid
grid_type = uniform

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-star

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# Options related to the overflow case
[overflow]

...

# Distance from two cell centers (km)
resolution = 2.0

# Bottom depth at bottom of overflow
max_bottom_depth = ${vertical_grid:bottom_depth}

# Shelf depth (m)
shelf_depth = 500.0

# Lateral position of the shelf-break (km)
x_slope = 40.0

# Length-scale of the slope (km)
l_slope = 7.0
```

What we're doing here is defining a z-star coordinate with 60 uniform vertical
levels, a bottom depth of 2000 m (so each layer is 33 1/3 m thick) and without
any alteration of layer thickness for partial cells.  A major feature of the
`overflow` tests is that they have a `bottomDepth` field that that is shallow
on the left (depth given by `shelf_depth`) and deep on the right (depth given
by `max_bottom_depth`) with a `tanh` transition between the two centered at
`x_slope` with steepness define by `l_slope`.  The sea surface height (`ssh`)
is set to zero everywhere (this will nearly always be the case for any tasks
that don't include ice-shelf cavities, where the SSH is depressed by the weight
of the overlying ice). {py:func}`polaris.ocean.vertical.init_vertical_coord()`
takes care of most of the details for us once we have defined `bottomDepth` and
 `ssh`, adding the following fields to `ds`:

* `minLevelCell` - the index of the top valid layer
* `maxLevelCell` - the index of the bottom valid layer
* `cellMask` - a mask of where cells are valid
* `layerThickness` - the thickness of each layer
* `restingThickness` - the thickness of each layer stretched as if `ssh = 0`
* `zMid` - the elevation of the midpoint of each layer
* `refTopDepth` - the positive-down depth of the top of each ref. level
* `refZMid` - the positive-down depth of the middle of each ref. level
* `refBottomDepth` - the positive-down depth of the bottom of each ref. level
* `refInterfaces` - the positive-down depth of the interfaces between ref.
  levels (with `nVertLevels` + 1 elements).
* `vertCoordMovementWeights` - the weights (all ones) for coordinate movement

## Test Again

Repeat the testing procedure that you did in
[Testing the First Task and Step](testing_first_task.md).  You will probably
want to set up in a new work directory so you can test everything from the
beginning. This time, you should see `vert_coord.nc` in the `init`
subdirectory.  You can use `ncdump` to make sure it has the right fields in it
-- the ones listed above and also `ssh` and `bottomDepth`.

## Creating an initial condition

The next part of the `run()` method in the `init` step is to
define the initial condition:

```bash
$ vim polaris/tasks/ocean/my_overflow/init.py
```
```{code-block} python
:emphasize-lines: 3, 17-85

...

from polaris.ocean.eos import compute_density
from polaris.ocean.vertical import init_vertical_coord


class Init(Step):

    ...

    def run(self):

        ...

        write_netcdf(ds, 'vert_coord.nc')

        # initial temperature is constant except for a block of cold water on
        # the shelf
        x_dense = section.getfloat('x_dense')
        lower_temperature = section.getfloat('lower_temperature')
        higher_temperature = section.getfloat('higher_temperature')
        _, x = np.meshgrid(np.zeros(ds.sizes['nVertLevels']), ds.xCell)
        temperature = np.where(
            (x - ds.xCell.min().values) < x_dense * 1.0e3,
            lower_temperature,
            higher_temperature,
        )
        ds['temperature'] = (
            (
                'Time',
                'nCells',
                'nVertLevels',
            ),
            np.expand_dims(temperature, axis=0),
        )

        # initial salinity is constant
        salinity = section.getfloat('salinity') * np.ones_like(temperature)
        ds['salinity'] = salinity * xr.ones_like(ds.temperature)

        density = compute_density(config, temperature, salinity)
        ds['density'] = (
            (
                'Time',
                'nCells',
                'nVertLevels',
            ),
            np.expand_dims(density, axis=0),
        )

        # initial velocity on edges is stationary
        ds['normalVelocity'] = (
            (
                'Time',
                'nEdges',
                'nVertLevels',
            ),
            np.zeros([1, ds.sizes['nEdges'], ds.sizes['nVertLevels']]),
        )

        # Coriolis parameter is zero
        ds['fCell'] = (
            (
                'nCells',
                'nVertLevels',
            ),
            np.zeros([ds.sizes['nCells'], ds.sizes['nVertLevels']]),
        )
        ds['fEdge'] = (
            (
                'nEdges',
                'nVertLevels',
            ),
            np.zeros([ds.sizes['nEdges'], ds.sizes['nVertLevels']]),
        )
        ds['fVertex'] = (
            (
                'nVertices',
                'nVertLevels',
            ),
            np.zeros([ds.sizes['nVertices'], ds.sizes['nVertLevels']]),
        )

        # finalize and write file
        write_netcdf(ds, 'init.nc')
```

The details aren't critical for the purpose of this tutorial, though you may
find this example to be useful for developing other tasks, particularly
those for the `ocean` component.  The point is mostly to show how config
options are used to define the initial condition. Again, we use config options
from `my_overflow.cfg`, this time in a section specific to the test
group that we therefore call `my_overflow`:


Now we add the config options we need to the config file:

```bash
$ vim polaris/tasks/ocean/my_overflow/my_overflow.cfg
```
```{code-block} cfg
:emphasize-lines: 11-27

...

# Options related to the overflow case
[overflow]

...

# Length-scale of the slope (km)
l_slope = 7.0

# Cold water range (km)
x_dense = 20.0

# constant salinity (PSU)
salinity = 35.0

# Lower temperature (deg C)
lower_temperature = 10.0

# Higher temperature (deg C)
higher_temperature = 20.0

# Beta in eos
eos_linear_beta = 0.8

# Reference salinity (PSU)
eos_linear_Sref = ${overflow:salinity}
```

Again, the idea is that we make these config options rather than hard-coding
them in the task so that users can more easily alter the task and
also to provide a relatively obvious place to document these parameters.

## Test Once More

Repeat the testing procedure, again using a new work directory so you can
start fresh.. This time, you should see `init.nc` in the `init` subdirectory.
Again, you can use `ncdump` to make sure it has the right fields in it --
including the ones such as `temperature` and `fVertex` that we added above.

---

← [Back to *Testing the First Task and Step*](testing_first_task.md)

→ [Continue to *Adding Plots*](adding_plots.md)
