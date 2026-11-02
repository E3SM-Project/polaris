(e3sm-init-suites)=

# Suites

The `e3sm/init` component includes suites for running topography remap and
cull tasks in bulk.  To set them up, run:

```bash
polaris suite -c e3sm/init -t <suite_name> ...
```

The suites are split into two groups:

- **simple** suites cover the uniform quasi-uniform (`QU`) and icosahedral
  (`Icos`) base meshes.
- **unified** suites cover the named unified meshes (see
  {ref}`users-mesh-unified-base-mesh`).

(e3sm-init-suite-cull-topo-simple)=

## cull_topo_simple suite

Runs cull-topography tasks for all supported simple base meshes.

```none
e3sm/init/icos480km/topo/cull
e3sm/init/icos240km/topo/cull
e3sm/init/icos120km/topo/cull
e3sm/init/icos60km/topo/cull
e3sm/init/icos30km/topo/cull
e3sm/init/qu480km/topo/cull
e3sm/init/qu240km/topo/cull
e3sm/init/qu210km/topo/cull
e3sm/init/qu180km/topo/cull
e3sm/init/qu150km/topo/cull
e3sm/init/qu120km/topo/cull
e3sm/init/qu90km/topo/cull
e3sm/init/qu60km/topo/cull
e3sm/init/qu30km/topo/cull
```

(e3sm-init-suite-remap-topo-simple)=

## remap_topo_simple suite

Runs remap-topography tasks for all supported simple base meshes.

```none
e3sm/init/icos480km/topo/remap
e3sm/init/icos240km/topo/remap
e3sm/init/icos120km/topo/remap
e3sm/init/icos60km/topo/remap
e3sm/init/icos30km/topo/remap
e3sm/init/qu480km/topo/remap
e3sm/init/qu240km/topo/remap
e3sm/init/qu210km/topo/remap
e3sm/init/qu180km/topo/remap
e3sm/init/qu150km/topo/remap
e3sm/init/qu120km/topo/remap
e3sm/init/qu90km/topo/remap
e3sm/init/qu60km/topo/remap
e3sm/init/qu30km/topo/remap
```

(e3sm-init-suite-cull-topo-unified)=

## cull_topo_unified suite

Runs cull-topography tasks for all supported unified meshes.

```none
e3sm/init/u-oi-so12to30-lr10/topo/cull
e3sm/init/u-oi240-lr240/topo/cull
e3sm/init/u-oi30-lr10/topo/cull
e3sm/init/u-oi6to18-lr12p5/topo/cull
e3sm/init/u-oi6to18-lr25/topo/cull
```

(e3sm-init-suite-remap-topo-unified)=

## remap_topo_unified suite

Runs remap-topography tasks for all supported unified meshes.

```none
e3sm/init/u-oi-so12to30-lr10/topo/remap
e3sm/init/u-oi240-lr240/topo/remap
e3sm/init/u-oi30-lr10/topo/remap
e3sm/init/u-oi6to18-lr12p5/topo/remap
e3sm/init/u-oi6to18-lr25/topo/remap
```
