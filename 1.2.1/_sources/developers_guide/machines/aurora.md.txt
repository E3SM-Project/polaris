(dev-machine-aurora)=

# Aurora

## intel

This is the default polaris compiler on Aurora.  If the environment has
been set up properly (see {ref}`dev-conda-env`), you should be able to source:

```bash
source load_polaris_aurora_intel_mpich.sh
```

## intelgpu

To build Omega with GPU support on Aurora, use the `intelgpu` compiler
instead.  If the environment has been set up properly (see
{ref}`dev-conda-env`), you should be able to source:

```bash
source load_polaris_aurora_intelgpu_mpich.sh
```

MPAS components do not yet support Aurora, but Omega does.
