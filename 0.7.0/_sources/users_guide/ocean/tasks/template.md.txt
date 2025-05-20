(ocean-category-of-task)=

# <Category of task>

Description of common characteristics of the tasks.

(ocean-category-of-task-task-name)=

## suppported models

This section should have one of the following lines, as appropriate, or if
individual tasks support different models, each task should have a similar
section:

These tasks support both MPAS-Ocean and Omega.

These tasks support only MPAS-Ocean.

These tasks support only Omega.

## task_name

In cases where the test cases within a category share many characteristics,
it may be more appropriate to move the certain sections up one level to the
common subdirectory. In that case, the respective section should still be
included for each test case, specifying any or no differences from the section
in the shared framework level.

### description

Description of the test case. Images that show the test case configuration or
results are particularly welcome here.

```{image} images/cosine_bell_convergence.png
:align: center
:width: 500 px
```

### mesh

Specify whether the mesh is global or planar and the resolution(s) tested. If
planar, specify the mesh size. If global, specify whether the mesh is
icosohedral or quasi-uniform. Specify any relevant options in the config file
pertaining to setting up the mesh.

### vertical grid

If there are no restrictions on the vertical grid specifications inherent to
the test case, then the config section may be provided without any further
description.

Examples of restrictions or special conditions warranting description may
include:

* Whether the topography is variable
* Whether the test pertains to shallow water dynamics, in which case the
minimum number of vertical levels may be used
* Whether there are several test cases in the test group investigating the
effects of different vertical coordinates (`coord_type`)

```cfg
# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
grid_type = uniform

# Number of vertical levels
vert_levels = 3

# Depth of the bottom of the ocean
bottom_depth = 300.0

# The type of vertical coordinate (e.g. z-level, z-star)
coord_type = z-level

# Whether to use "partial" or "full", or "None" to not alter the topography
partial_cell_type = None

# The minimum fraction of a layer for partial cells
min_pc_fraction = 0.1
```

### initial conditions

The initial conditions should be specified for all variables requiring
initial conditions (see {ref}`dev-ocean-models`).

### forcing

If applicable, specify the forcing applied at each time step of the simulation
(in MPAS-Ocean, these are the variables contained in the `forcing` stream).
If not applicable, keep this section with the notation N/A.

### time step and run duration

The time step for forward integration should be specified here for the test
case's resolution. The run duration should also be specified.

### config options

Here, include the config section(s) that is specific to this test case. E.g.,

```cfg
# options for cosine bell convergence test case
[cosine_bell]

# time step per resolution (s/km), since dt is proportional to resolution
dt_per_km = 30

# the constant temperature of the domain
temperature = 15.0

# the constant salinity of the domain
salinity = 35.0
...


# options for visualization for the cosine bell convergence test case
[cosine_bell_viz]

# visualization latitude and longitude resolution
dlon = 0.5
dlat = 0.5

# remapping method ('bilinear', 'neareststod', 'conserve')
remap_method = conserve
```

Include here any further description of each of the config options.

### cores

Specify whether the number of cores is determined by `goal_cells_per_core` and
`max_cells_per_core` in the `ocean` section of the config file or whether the
default and minimum number of cores is given in arguments to the forward step,
and what those defaults are.
