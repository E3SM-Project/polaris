(dev-landice)=

# Land-ice component

The `landice` component runs MALI.  The component-wide config options say
which model it runs:

```cfg
# This config file has default config options for the landice component

# Options related the landice component
[landice]

# Which model is used.  MALI is currently the only option.
model = mali
```

The config options for MALI itself are in `mali.cfg`, added during setup by
`Landice.configure()`.  They point to the build's namelist, streams file,
processed registry and executable, as `mpas_ocean.cfg` does for MPAS-Ocean,
and set the build options:

```cfg
# Config options related to building components
[build]

# the branch to build from
branch = ${paths:polaris_branch}/e3sm_submodules/MALI-Dev

# whether to build MALI with Albany, which the first-order velocity solver
# needs: True, False or detect (with Albany if the environment provides it)
albany = detect
```

(dev-landice-build)=

## Building MALI

Polaris builds MALI during `polaris setup` or `polaris suite` whenever a task
has a {py:class}`polaris.landice.model.MaliModelStep` and no build is found
at `component_path`, which defaults to `${WORKDIR}/landice_build`.  The
default source is the `e3sm_submodules/MALI-Dev` submodule, which follows
MALI-Dev's `develop` branch, where MALI is developed.  Use
`--landice_branch` (or `--branch` when setting up landice tasks) to build
from another E3SM branch, such as FAnSSIE for ocean–ice-sheet coupling work.
The build flags described in {ref}`dev-build-components` apply, and
{ref}`dev-build` describes the build script.

```bash
source ./load_<env_name>_<machine>_<compiler>_<mpi>.sh
polaris suite -c landice -t mali_pr -m $MACHINE -w $WORKDIR
```

To build MALI by hand instead, run `make <mpas_make_target>` in
`components/mpas-albany-landice` of an E3SM branch, adding `ALBANY=true` and
`MPAS_EXTERNAL_LIBS="${POLARIS_ALBANY_LINK_LIBS}"` for a build with Albany,
then point Polaris to it with `-p`.

(dev-landice-albany)=

## Albany

MALI's first-order velocity solver comes from the Albany library, which is
built with Trilinos in a Polaris Spack library environment deployed with
`--with-albany`:

```bash
./deploy.py --compiler gnu --mpi openmpi --with-albany
```

Albany has its own library environments, named
`spack_env_albany_<compiler>_<mpi>`, so environments without it are not
modified.  Add `--deploy-spack` to build the environment rather than load an
existing one.  `deploy/albany_supported.txt` lists the machines, compilers
and MPI libraries that support Albany, and `deploy/pins.cfg` pins Albany and
Trilinos.

When the Spack library environment has Albany, the load script sets
`POLARIS_ALBANY_LINK_LIBS` to the libraries MALI links to.  Only MALI builds
use it, so MPAS-Ocean builds in the same environment are unchanged.  With
`albany = detect`, a MALI build has Albany whenever the environment provides
it, and one build serves the tasks for both velocity solvers.  Setup fails if
a step uses the first-order solver and the build will not have Albany, or an
existing build's source record says it has none.

```{toctree}
:titlesonly: true

framework
tasks/index
```
