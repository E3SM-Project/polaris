(dev-machine-compy)=

# CompyMcNodeFace

## intel

This works to build (but not yet run) standalone MPAS.  Again, we will update
as soon as we have a solution.

This is the default polaris compiler on CompyMcNodeFace.  If the
environment has been set up properly (see {ref}`dev-conda-env`), you should be
able to source:

```bash
source load_dev_polaris_0.1.0-alpha.1_compy_intel_impi.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] intel-mpi
```

## gnu

If you've set things up for this compiler, you should be able to:

```bash
source load_dev_polaris_0.1.0-alpha.1_compy_gnu_openmpi.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] [ALBANY=true] gfortran
```
