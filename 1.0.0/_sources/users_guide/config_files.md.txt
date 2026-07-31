(config-files)=

# Config Files

Polaris uses config files (with extension `.cfg`) to allow users to
control how {ref}`tasks` and {ref}`suites` get set up and run.

## A "user" config file

If you're running on one of the supported {ref}`machines`, and you provide a
path to where you build the MPAS model (with the `-p` flag to
`polaris setup` and `polaris suite`, see {ref}`quick-start` and
{ref}`suites`), you also won't need to create a config file to set up
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

# total cores on one node
cores_per_node = 8

# GPUs per node (optional)
gpus_per_node = 0

# optional compiler-specific overrides
[parallel.gnu]
parallel_executable = mpirun

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
  the paths to cached data files. Parallel options can also come from
  compiler-specific sections such as `[parallel.gnu]` or `[parallel.intel]`
  (from mache machine configs)
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
  certain feature is enabled.  For example, {ref}`ocean-geostrophic` loads
  different sets of config options for different meshes.
- a user's config file described above.

You are free to add any sections and config options to your config file,
in which case they will override the values specified in one of the other
config files listed above. Here is an example of some customization for
ocean tasks:

```cfg
# Options related to generating a reusable WOA23 hydrography product
[woa23]

# target depths for horizontal plots of the extrapolated product (m)
horizontal_plot_depths = 0.0, 250.0, 500.0
```

In this example, the default depths for WOA23 horizontal plots are overridden.

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
# the netcdf4 engine is not performing well on Chrysalis, so we will
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
# polaris needs should be in the deployment environment, so this is only the path
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


# Options related to generating a reusable WOA23 hydrography product
[woa23]

# source: /home/xylar/code/polaris/customize_config_parser/polaris/tasks/ocean/realistic_global/hydrography/woa23/woa23.cfg
extrap_threshold = 0.01

# source: /home/xylar/code/polaris/customize_config_parser/polaris/tasks/ocean/realistic_global/hydrography/woa23/woa23.cfg
horizontal_plot_depths = 0.0, 200.0, 400.0, 600.0, 800.0

# source: /home/xylar/code/polaris/customize_config_parser/polaris/tasks/ocean/realistic_global/hydrography/woa23/woa23.cfg
section_max_depth = 2000.0
```

The comments are retained and the config file or python module where they were
defined is also included as a a comment for provenance and to make it easier
for users and developers to understand how the config file is built up.
