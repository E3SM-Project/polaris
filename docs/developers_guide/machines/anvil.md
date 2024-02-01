(dev-machine-anvil)=

# Anvil

## intel

This is the default polaris compiler on Anvil.  If the environment has
been set up properly (see {ref}`dev-conda-env`), you should be able to source:

```bash
source load_dev_polaris_0.1.0-alpha.1_anvil_intel_impi.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] intel-mpi
```

For other MPI libraries (`openmpi` instead of `impi`), use

```bash
make [DEBUG=true] [OPENMP=true] ifort
```

## gnu

If you've set things up for this compiler, you should be able to:

```bash
source load_dev_polaris_0.1.0-alpha.1_anvil_gnu_openmpi.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] [ALBANY=true] gfortran
```
