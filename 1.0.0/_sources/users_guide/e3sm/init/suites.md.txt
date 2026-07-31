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
e3sm/init/Icos480km/topo/cull
e3sm/init/Icos240km/topo/cull
e3sm/init/Icos120km/topo/cull
e3sm/init/Icos60km/topo/cull
e3sm/init/Icos30km/topo/cull
e3sm/init/QU480km/topo/cull
e3sm/init/QU240km/topo/cull
e3sm/init/QU210km/topo/cull
e3sm/init/QU180km/topo/cull
e3sm/init/QU150km/topo/cull
e3sm/init/QU120km/topo/cull
e3sm/init/QU90km/topo/cull
e3sm/init/QU60km/topo/cull
e3sm/init/QU30km/topo/cull
```

(e3sm-init-suite-remap-topo-simple)=

## remap_topo_simple suite

Runs remap-topography tasks for all supported simple base meshes.

```none
e3sm/init/Icos480km/topo/remap
e3sm/init/Icos240km/topo/remap
e3sm/init/Icos120km/topo/remap
e3sm/init/Icos60km/topo/remap
e3sm/init/Icos30km/topo/remap
e3sm/init/QU480km/topo/remap
e3sm/init/QU240km/topo/remap
e3sm/init/QU210km/topo/remap
e3sm/init/QU180km/topo/remap
e3sm/init/QU150km/topo/remap
e3sm/init/QU120km/topo/remap
e3sm/init/QU90km/topo/remap
e3sm/init/QU60km/topo/remap
e3sm/init/QU30km/topo/remap
```

(e3sm-init-suite-cull-topo-unified)=

## cull_topo_unified suite

Runs cull-topography tasks for all supported unified meshes.

```none
e3sm/init/u.oi.so12to30.lr10/topo/cull
e3sm/init/u.oi240.lr240/topo/cull
e3sm/init/u.oi30.lr10/topo/cull
e3sm/init/u.oi6to18.lr6to10/topo/cull
```

(e3sm-init-suite-remap-topo-unified)=

## remap_topo_unified suite

Runs remap-topography tasks for all supported unified meshes.

```none
e3sm/init/u.oi.so12to30.lr10/topo/remap
e3sm/init/u.oi240.lr240/topo/remap
e3sm/init/u.oi30.lr10/topo/remap
e3sm/init/u.oi6to18.lr6to10/topo/remap
```
