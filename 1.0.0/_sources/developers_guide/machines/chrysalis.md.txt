(dev-machine-chrysalis)=

# Chrysalis

## oneapi-ifx

This is the default polaris compiler on Chrysalis.  If the environment has
been set up properly (see {ref}`dev-conda-env`), you should be able to source:

```bash
source load_polaris_chrysalis_oneapi-ifx_openmpi.sh
```

You cannot build standalone MPAS components with this compiler at this time.

## gnu

If you've set things up for this compiler, you should be able to:

```bash
source load_polaris_chrysalis_gnu_openmpi.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] [ALBANY=true] gfortran
```

## intel

If the environment has been set up properly, you should be able to source:

```bash
source load_polaris_chrysalis_intel_openmpi.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] ifort
```

