(dev-machines)=

# Machines

Polaris attempts to be aware of the capabilities of the machine it is running 
on.  This  is a particular advantage for so-called "supported" machines with a 
config file defined for them in the `polaris` package.  But even for "unknown" 
machines,  it is not difficult to set a few config options in your user config 
file to  describe your machine.  Then, polaris can use this data to make sure 
test  cases are configured in a way that is appropriate for your machine.

(dev-supported-machines)=

## Supported Machines

If you follow the procedure in {ref}`dev-conda-env`, you will have an
activation script for activating the development conda environment, setting
loading system modules and setting environment variables so you can build
MPAS and work with polaris.  Just source the script that should appear in
the base of your polaris branch, e.g.:

```bash
source load_dev_polaris_0.1.0-alpha.1_anvil_intel_impi.sh
```

After loading this environment, you can set up test cases or test suites, and
a link `load_polaris_env.sh` will be included in each suite or test case
work directory.  This is a link to the activation script that you sourced when
you were setting things up.  You can can source this file on a compute node
(e.g. in a job script) to get the right polaris conda environment, compilers,
MPI libraries and environment variables for running polaris tests and
the MPAS model.

:::{note}
Albany (and therefore most of the functionality in MALI) is currently only
supported for those configurations with `gnu` compilers.
:::

```{eval-rst}
+--------------+------------+-----------+-------------------+
| Machine      | Compiler   | MPI lib.  |  MPAS make target |
+==============+============+===========+===================+
| anvil        | intel      | impi      | intel-mpi         |
|              |            +-----------+-------------------+
|              |            | openmpi   | ifort             |
|              +------------+-----------+-------------------+
|              | gnu        | openmpi   | gfortran          |
|              |            +-----------+-------------------+
|              |            | mvapich   | gfortran          |
+--------------+------------+-----------+-------------------+
| chicoma-cpu  | gnu        | mpich     | gnu-cray          |
+--------------+------------+-----------+-------------------+
| chrysalis    | intel      | openmpi   | ifort             |
|              |            +-----------+-------------------+
|              |            | impi      | intel-mpi         |
|              +------------+-----------+-------------------+
|              | gnu        | openmpi   | gfortran          |
+--------------+------------+-----------+-------------------+
| compy        | intel      | impi      | intel-mpi         |
|              +------------+-----------+-------------------+
|              | gnu        | openmpi   | gfortran          |
+--------------+------------+-----------+-------------------+
| cori-haswell | intel      | mpt       | intel-cray        |
|              +------------+-----------+-------------------+
|              | gnu        | mpt       | gnu-cray          |
+--------------+------------+-----------+-------------------+
| pm-cpu       | gnu        | mpich     | gnu-cray          |
+--------------+------------+-----------+-------------------+
```

Below are specifics for each supported machine

```{toctree}
:titlesonly: true

anvil
chicoma
chrysalis
compy
cori
perlmutter
```

(dev-other-machines)=

## Other Machines

If you are working on an "unknown" machine, the procedure is pretty similar
to what was described in {ref}`dev-conda-env`.  The main difference is that
we will use `mpich` or `openmpi` and the gnu compilers from conda-forge
rather than system compilers.  To create a development conda environment and
an activation script for it, on Linux, run:

```bash
./conda/configure_polaris_envs.py --conda <conda_path> -c gnu -i mpich
```

and on OSX run:

```bash
./conda/configure_polaris_envs.py --conda <conda_path> -c clang -i mpich
```

You may use `openmpi` instead of `mpich` but we have had better experiences
with the latter.

The result should be an activation script `load_dev_polaris_0.1.0-alpha.1_<mpi>.sh`.
Source this script to get the appropriate conda environment and environment
variables.

Under Linux, you can build the MPAS model with

```bash
make gfortran
```

Under OSX, you can build the MPAS model with

```bash
make gfortran-clang
```
