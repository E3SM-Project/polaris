(dev-ocean)=

# Ocean component

The `ocean` component is defined by the {py:class}`polaris.ocean.Ocean`
class. All test cases in the `ocean` component share the following set of
default config options:

```cfg
# This config file has default config options for the ocean component, which
# can either be MPAS-Ocean or OMEGA

# Options related the ocean component
[ocean]
# Which model, MPAS-Ocean or OMEGA, is used
model = mpas-ocean


# Options relate to adjusting the sea-surface height or land-ice pressure
# below ice shelves to they are dynamically consistent with one another
[ssh_adjustment]

# the number of iterations of ssh adjustment to perform
iterations = 10
```

MPAS-Ocean test cases also have these config options:
```cfg
# This config file has default config options for MPAS-Ocean

# The paths section points compass to external paths
[paths]

# the relative or absolute path to the root of a branch where MPAS-Ocean
# or OMEGA has been built
component_path = ${paths:compass_branch}/e3sm_submodules/E3SM-Project/components/mpas-ocean

# The namelists section defines paths to example_compact namelists that will
# be used to generate specific namelists. By default, these point to the
# forward and init namelists in the default_inputs directory after a successful
# build of the ocean model.  Change these in a custom config file if you need
# a different location.
[namelists]
forward = ${paths:component_path}/default_inputs/namelist.ocean.forward
init    = ${paths:component_path}/default_inputs/namelist.ocean.init

# The streams section defines paths to example_compact streams files that will
# be used to generate specific streams files. By default, these point to the
# forward and init streams files in the default_inputs directory after a
# successful build of the ocean model. Change these in a custom config file if
# you need a different location.
[streams]
forward = ${paths:component_path}/default_inputs/streams.ocean.forward
init    = ${paths:component_path}/default_inputs/streams.ocean.init


# The executables section defines paths to required executables. These
# executables are provided for use by specific test cases.  Most tools that
# compass needs should be in the conda environment, so this is only the path
# to the MPAS-Ocean or OMEGA executable by default.
[executables]
component = ${paths:component_path}/ocean_model
```

The default location for MPAS-Ocean is in the
[git submodule](https://git-scm.com/book/en/v2/Git-Tools-Submodules)
`e3sm_submodules/E3SM-Project` in the directory `components/mpas-ocean`.  The 
submodule  may not point to the latest MPAS-Ocean code in on the E3SM
[master](https://github.com/E3SM-Project/E3SM/tree/master)
branch but the plan is to update the submodule frequently.  The current version
of the submodule should always be guaranteed to be compatible with the
corresponding version of polaris.

Similarly, the `e3sm_submodules/Omega` submodule is where you can find
a verison of OMEGA that is compatible with the current polaris.  The model
can be built from the `components/omega` directory.  The  submodule may not 
point to the latest OMEGA code in on the `Omega`
[develop](https://github.com/E3SM-Project/Omega/tree/develop)
branch but, again, the plan is to update the submodule frequently and to
maintain compatibility of the submodule with polaris.

To make sure the code in the submodule has been cloned and is up-to-date, you
should run

```bash
git submodule update --init --recursive
```

in the base directory of your local clone of the polaris repo.  Then, you can
`cd` into the component's directory (e.g. 
`e3sm_submodules/E3SM-Project/components/mpas-ocean`) and build the code as
appropriate for whichever of the {ref}`machines` you are using.

```{toctree}
:titlesonly: true

test_groups/index
framework
models/index
```
