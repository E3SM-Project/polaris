(dev-machine-aurora)=

# Aurora

## oneapi-ifx

This is the default polaris compiler on Aurora.  If the environment has
been set up properly (see {ref}`dev-conda-env`), you should be able to source:

```bash
source load_polaris_aurora_oneapi-ifx_mpich.sh
```

## oneapi-ifxgpu

To build Omega with GPU support on Aurora, use the `oneapi-ifxgpu` compiler
instead.  If the environment has been set up properly (see
{ref}`dev-conda-env`), you should be able to source:

```bash
source load_polaris_aurora_oneapi-ifxgpu_mpich.sh
```

MPAS components do not yet support Aurora, but Omega does.
