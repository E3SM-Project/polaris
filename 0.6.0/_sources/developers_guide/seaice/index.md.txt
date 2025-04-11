(dev-seaice)=

# SeaIce component

The `seaice` component is defined by the {py:class}`polaris.seaice.SeaIce`
class. All tasks in the `seaice` component  are single column tests 
and contain very simple config options as follows:

```cfg
# This config file has default config options for MPAS-Seaice

# The paths section points polaris to external paths
[paths]

# the relative or absolute path to the root of a branch where MPAS-Seaice
# has been built
component_path = ${paths:polaris_branch}/e3sm_submodules/E3SM-Project/components/mpas-seaice

# The namelists section defines paths to example_compact namelists that will
# be used to generate specific namelists. By default, these point to the
# forward and init namelists in the default_inputs directory after a successful
# build of the seaice model.  Change these in a custom config file if you need
# a different location.
[namelists]
forward = ${paths:component_path}/default_inputs/namelist.seaice

# The streams section defines paths to example_compact streams files that will
# be used to generate specific streams files. By default, these point to the
# forward and init streams files in the default_inputs directory after a
# successful build of the seaice model. Change these in a custom config file if
# you need a different location.
[streams]
forward = ${paths:component_path}/default_inputs/streams.seaice

# The registry section points to a post-processed registry file that can
# be used to identify the types (var, var_array, var_struct) of variables in
# a stream
[registry]
processed = ${paths:component_path}/src/Registry_processed.xml

# The executables section defines paths to required executables. These
# executables are provided for use by specific tasks.  Most tools that
# polaris needs should be in the conda environment, so this is only the path
# to the MPAS-Seaice executable by default.
[executables]
component = ${paths:component_path}/seaice_model
```

The default location for MPAS-Seaice is in the
[git submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
`e3sm_submodules/E3SM-Project` in the directory `components/mpas-seaice`.  The 
submodule  may not point to the latest MPAS-Seaice code in on the E3SM
[master](https://github.com/E3SM-Project/E3SM/tree/master)
branch but the plan is to update the submodule frequently.  The current version
of the submodule should always be guaranteed to be compatible with the
corresponding version of polaris.

To make sure the code in the submodule has been cloned and is up-to-date, you
should run

```bash
git submodule update --init --recursive
```

in the base directory of your local clone of the polaris repo.  Then, you can
`cd` into the component's directory (e.g. 
`e3sm_submodules/E3SM-Project/components/mpas-seaice`) and build the code as
appropriate for whichever of the {ref}`machines` you are using.

```{toctree}
:titlesonly: true

tasks/index
framework
mpas_seaice
```
