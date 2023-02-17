# Cori

## cori-haswell, intel

This is the default polaris architecture and compiler on Cori.  If the
environment has been set up properly (see {ref}`dev-conda-env`), you should be
able to source:

```bash
source load_dev_polaris_0.1.0-alpha.1_cori-haswell_intel_mpt.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] intel-cray
```

## cori-haswell, gnu

If you've set things up for this compiler, you should be able to:

```bash
source load_dev_polaris_0.1.0-alpha.1_cori-haswell_gnu_mpt.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [OPENMP=true] [ALBANY=true] gnu-cray
```
