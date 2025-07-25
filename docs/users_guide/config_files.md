(config-files)=

# Config Files

Polaris uses config files (with extension `.cfg`) to allow users to
control how {ref}`tasks` and {ref}`suites` get set up and run.

## A "user" config file

If you're running on one of the supported {ref}`machines`, and you provide a
path to where you build the MPAS model (with the `-p` flag to
`polaris setup` and `polaris suite`, see {ref}`setup-overview` and
{ref}`suite-overview`), you also won't need to create a config file to set up
tasks or suites.

If you're running on another machine like your own laptop, you will need to
provide some basic information for polaris to work properly.  Even if
you're running on one of the supported machines, you might find it convenient
to make your own changes to config options related to either setting up or
running suites and task.

Here is an example:

```cfg
# This file contains some common config options for machines that polaris
# doesn't recognize automatically

# The paths section describes paths where files are automatically downloaded
[paths]

# A root directory where data for polaris tasks can be downloaded. This
# data will be cached for future reuse.
database_root = /home/xylar/data/polaris/data

# The parallel section describes options related to running tests in parallel
[parallel]

# parallel system of execution: slurm, pbs or single_node
system = single_node

# whether to use mpirun or srun to run the model
parallel_executable = mpirun -host localhost

# total cores on the machine (or cores on one node if it is a multinode
# machine), detected automatically by default
cores_per_node = 8

```

The comments in this example are hopefully pretty self-explanatory.
You provide the config file to `polaris setup` and `polaris suite` with
the `-f` flag:

```bash
polaris setup -f my_machine.cfg ...
```

## Test-case config files

Once a task has been set up, its work directory will contain a config file
called `<task>.cfg`, where `<task>` is the name of the task.
As a user, you can typically leave the config options in a task as they
are to run the test in its default configuration.  But the config file is meant
to make it easier to modify the task to fit your needs without having to
dig into the polaris code.

Config options for a given task are built up from a number of different
sources:

- the default config file,
  [default.cfg](https://github.com/E3SM-Project/polaris/blob/main/polaris/default.cfg),
  which sets a few options related to downloading files during setup (whether
  to download and whether to check the size of files already downloaded)
- the [machine config file](https://github.com/E3SM-Project/polaris/blob/main/polaris/machines)
  (using [machines/default.cfg](https://github.com/E3SM-Project/polaris/blob/main/polaris/machines/default.cfg)
  if no machine was specified) with information on the parallel system and
  the paths to cached data files
- the component's config file.  For the {ref}`ocean` core, this sets default
  paths to the MPAS-Ocean model build (including the namelist templates).  It
  uses
  [extended interpolation](https://docs.python.org/3/library/configparser.html#configparser.ExtendedInterpolation)
  in the config file to use config options within other config
  options, e.g. `component = ${paths:component_path}/ocean_model`.
- a config file shared with other similar tasks if one is defined.  For
  idealized tests, these often include the size and resolution of the mesh as
  well as (for ocean initial conditions) the number of vertical levels.
- any number of config files from the task.  There might be different
  config options depending on how the task is configured (e.g. only if a
  certain feature is enabled.  For example, {ref}`ocean-global-ocean` loads
  different sets of config options for different meshes.
- a user's config file described above.

You are free to add any sections and config options to your config file,
in which case they will override the values specified in one of the other
config files listed above. Here is an example of some customization for the
{ref}`ocean-global-ocean` tasks:

```cfg
# options for global ocean testcases
[global_ocean]

# The following options are detected from .gitconfig if not explicitly entered
author = Xylar Asay-Davis
email = xylar@lanl.gov
pull_request = https://github.com/E3SM-Project/polaris/pull/28
```

In this example, the author's name and email address, and the path to a pull
request will be included in the metadata for output files from global ocean
tasks.

A typical config file resulting from combining all of the sources listed above
looks like:

```cfg
# Options related to the current task
[task]

# source: /home/xylar/code/polaris/customize_config_parser/polaris/setup.py
steps_to_run = mesh


# Options related to downloading files
[download]

# the base url for the server from which meshes, initial conditions, and other
# data sets can be downloaded
# source: /home/xylar/code/polaris/customize_config_parser/polaris/default.cfg
server_base_url = https://web.lcrc.anl.gov/public/e3sm/mpas_standalonedata

# whether to download files during setup that have not been cached locally
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
download = True

# whether to check the size of files that have been downloaded to make sure
# they are the right size
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
check_size = False

# whether to verify SSL certificates for HTTPS requests
# source: /home/xylar/code/polaris/customize_config_parser/polaris/default.cfg
verify = True

# the path on the server for MPAS-Ocean
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/ocean.cfg
core_path = mpas-ocean


# The parallel section describes options related to running tests in parallel
[parallel]

# the program to use for graph partitioning
# source: /home/xylar/code/polaris/customize_config_parser/polaris/default.cfg
partition_executable = gpmetis

# parallel system of execution: slurm, pbs or single_node
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
system = single_node

# whether to use mpirun or srun to run the model
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
parallel_executable = mpirun

# cores per node on the machine
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
cores_per_node = 8

# the number of multiprocessing or dask threads to use
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
threads = 8


# The io section describes options related to file i/o
[io]

# the NetCDF file format: NETCDF4, NETCDF4_CLASSIC, NETCDF3_64BIT, or
# NETCDF3_CLASSIC
# source: /home/xylar/code/polaris/customize_config_parser/polaris/default.cfg
format = NETCDF3_64BIT

# the NetCDF output engine: netcdf4 or scipy
# the netcdf4 engine is not performing well on Chrysalis and Anvil, so we will
# try scipy for now.  If we can switch to NETCDF4 format, netcdf4 will be
# required
# source: /home/xylar/code/polaris/customize_config_parser/polaris/default.cfg
engine = scipy


# This file contains some common config options you might want to set
# if you're working with the polaris ocean core and MPAS-Ocean.
# The paths section describes paths that are used within the ocean core test
# cases.
[paths]

# source: /home/xylar/code/polaris/customize_config_parser/polaris/setup.py
mpas_model = /home/xylar/code/polaris/customize_config_parser/E3SM-Project/components/mpas-ocean

# The root to a location where the mesh_database, initial_condition_database,
# and bathymetry_database for MPAS-Ocean will be cached
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
ocean_database_root = /home/xylar/data/mpas/mpas_standalonedata/mpas-ocean

# The root to a location where data files for MALI will be cached
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
landice_database_root = /home/xylar/data/mpas/mpas_standalonedata/mpas-albany-landice


# The namelists section defines paths to example_compact namelists that will be used
# to generate specific namelists. By default, these point to the forward and
# init namelists in the default_inputs directory after a successful build of
# the ocean model.  Change these in a custom config file if you need a different
# example_compact.
[namelists]

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/ocean.cfg
forward = /home/xylar/code/polaris/customize_config_parser/E3SM-Project/components/mpas-ocean/default_inputs/namelist.ocean.forward

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/ocean.cfg
init = /home/xylar/code/polaris/customize_config_parser/E3SM-Project/components/mpas-ocean/default_inputs/namelist.ocean.init


# The streams section defines paths to example_compact streams files that will be used
# to generate specific streams files. By default, these point to the forward and
# init streams files in the default_inputs directory after a successful build of
# the ocean model. Change these in a custom config file if you need a different
# example_compact.
[streams]

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/ocean.cfg
forward = /home/xylar/code/polaris/customize_config_parser/E3SM-Project/components/mpas-ocean/default_inputs/streams.ocean.forward

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/ocean.cfg
init = /home/xylar/code/polaris/customize_config_parser/E3SM-Project/components/mpas-ocean/default_inputs/streams.ocean.init


# The executables section defines paths to required executables. These
# executables are provided for use by specific tasks.  Most tools that
# polaris needs should be in the conda environment, so this is only the path
# to the MPAS-Ocean executable by default.
[executables]

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/ocean.cfg
model = /home/xylar/code/polaris/customize_config_parser/E3SM-Project/components/mpas-ocean/ocean_model


# Options relate to adjusting the sea-surface height or land-ice pressure
# below ice shelves to they are dynamically consistent with one another
[ssh_adjustment]

# the number of iterations of ssh adjustment to perform
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/ocean.cfg
iterations = 10


# options for global ocean testcases
[global_ocean]

## each mesh should replace these with appropriate values in its config file
## config options related to the mesh step
# number of cores to use
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
mesh_cores = 18

# minimum of cores, below which the step fails
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
mesh_min_cores = 1

# maximum memory usage allowed (in MB)
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
mesh_max_memory = 1000

# maximum disk usage allowed (in MB)
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
mesh_max_disk = 1000

## config options related to the init step
# number of cores to use
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
init_cores = 4

# minimum of cores, below which the step fails
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
init_min_cores = 1

# maximum memory usage allowed (in MB)
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
init_max_memory = 1000

# maximum disk usage allowed (in MB)
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
init_max_disk = 1000

# number of threads
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
init_threads = 1

## config options related to the forward steps
# number of cores to use
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
forward_cores = 4

# minimum of cores, below which the step fails
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
forward_min_cores = 1

# number of threads
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
forward_threads = 1

# maximum memory usage allowed (in MB)
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
forward_max_memory = 1000

# maximum disk usage allowed (in MB)
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
forward_max_disk = 1000

## metadata related to the mesh
# whether to add metadata to output files
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
add_metadata = True

## metadata related to the mesh
# the prefix (e.g. QU, EC, WC, SO)
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
prefix = QU

# a description of the mesh
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
mesh_description = MPAS quasi-uniform mesh for E3SM version 2 at
    240-km global resolution with autodetect vertical
    level

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/configure.py
bathy_description = Bathymetry is from GEBCO 2022, combined with BedMachine Antarctica v2 around Antarctica.

# a description of the mesh with ice-shelf cavities
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
init_description = <<<Missing>>>

# E3SM version that the mesh is intended for
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
e3sm_version = 2

# The revision number of the mesh, which should be incremented each time the
# mesh is revised
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
mesh_revision = 1

# the minimum (finest) resolution in the mesh
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
min_res = 240

# the maximum (coarsest) resolution in the mesh, can be the same as min_res
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
max_res = 240

# the maximum depth of the ocean, always detected automatically
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
max_depth = autodetect

# the number of vertical levels, always detected automatically
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
levels = autodetect

# the date the mesh was created as YYMMDD, typically detected automatically
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
creation_date = autodetect

# These options are used in the metadata for global ocean initial conditions.
# You can indicated that you are the "author" of a mesh and give your preferred
# email address for people to contact your if they have questions about the
# mesh.  Or you can let polaris figure out who you are from your git
# configuration
# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
author = Xylar Asay-Davis

# source: /home/xylar/code/polaris/customize_config_parser/inej.cfg
email = xylar@lanl.gov

# The URL of the pull request documenting the creation of the mesh
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
pull_request = <<<Missing>>>


# config options related to dynamic adjustment
[dynamic_adjustment]

# the maximum allowed value of temperatureMax in global statistics
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
temperature_max = 33.0


# config options related to initial condition and diagnostics support files
# for E3SM
[files_for_e3sm]

# whether to generate an ocean initial condition in E3SM
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
enable_ocean_initial_condition = true

# whether to generate graph partitions for different numbers of ocean cores in
# E3SM
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
enable_ocean_graph_partition = true

# whether to generate a sea-ice initial condition in E3SM
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
enable_seaice_initial_condition = true

# whether to generate SCRIP files for later use in creating E3SM mapping files
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
enable_scrip = true

# whether to generate region masks, transects and mapping files for use in both
# online analysis members and offline with MPAS-Analysis
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
enable_diagnostics_files = true

## the following relate to the comparison grids in MPAS-Analysis to generate
## mapping files for.  The default values are also the defaults in
## MPAS-Analysis.  Coarser or finer resolution may be desirable for some MPAS
## meshes.
# The comparison lat/lon grid resolution in degrees
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
comparisonlatresolution = 0.5

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
comparisonlonresolution = 0.5

# The comparison Antarctic polar stereographic grid size and resolution in km
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
comparisonantarcticstereowidth = 6000.

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
comparisonantarcticstereoresolution = 10.

# The comparison Arctic polar stereographic grid size and resolution in km
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
comparisonarcticstereowidth = 6000.

# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/global_ocean.cfg
comparisonarcticstereoresolution = 10.


# Options related to the vertical grid
[vertical_grid]

# the type of vertical grid
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
grid_type = tanh_dz

# Number of vertical levels
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
vert_levels = 16

# Depth of the bottom of the ocean
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
bottom_depth = 3000.0

# The minimum layer thickness
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
min_layer_thickness = 3.0

# The maximum layer thickness
# source: /home/xylar/code/polaris/customize_config_parser/polaris/ocean/tests/global_ocean/mesh/qu240/qu240.cfg
max_layer_thickness = 500.0
```

The comments are retained and the config file or python module where they were
defined is also included as a a comment for provenance and to make it easier
for users and developers to understand how the config file is built up.
