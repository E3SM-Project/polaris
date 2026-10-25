# Perlmutter

## pm-cpu, gnu

If you've set things up for this compiler, you should be able to source a load
script similar to:

```bash
source load_polaris_pm-cpu_gnu_mpich.sh
```

Then, you can build the MPAS model with

```bash
make [DEBUG=true] [ALBANY=true] gnu-cray
```

## pm-cpu, intel

Similarly to `gnu`, for `intel`, if you've set things up right, sourcing the
load scrip will look something like:

```bash
source load_polaris_pm-cpu_intel_mpich.sh
```

To build MPAS components, use:

```bash
make [DEBUG=true] intel-cray
```

## pm-gpu, gnugpu

MALI is supported on Perlmutter's GPU nodes with a GPU build of Albany
(see {ref}`dev-landice-albany`).  Deploy with `--machine pm-gpu` and
`--with-albany`, then source a load script similar to:

```bash
source load_polaris_pm-gpu_gnugpu_mpich.sh
```

Then, you can build MALI with

```bash
make [DEBUG=true] ALBANY=true gnu-cray
```
