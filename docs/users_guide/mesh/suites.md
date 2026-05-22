(mesh-suites)=

# Suites

The mesh component includes suites for running the standalone unified-mesh
workflow tasks.  To set them up, run:

```bash
polaris suite -c mesh -t <suite_name> ...
```

(mesh-suite-coastline)=

## coastline suite

The `coastline` suite runs all standalone coastline-preparation tasks, one for
each supported latitude-longitude target-grid resolution.

```none
mesh/spherical/unified/coastline/0.03125_degree/task
mesh/spherical/unified/coastline/0.06250_degree/task
mesh/spherical/unified/coastline/0.12500_degree/task
mesh/spherical/unified/coastline/0.25000_degree/task
```

(mesh-suite-river)=

## river suite

The `river` suite runs all standalone river-network tasks, one for each
supported unified mesh.

```none
mesh/spherical/unified/u.oi.so12to30.lr10/river/task
mesh/spherical/unified/u.oi240.lr240/river/task
mesh/spherical/unified/u.oi30.lr10/river/task
mesh/spherical/unified/u.oi6to18.lr6to10/river/task
```

(mesh-suite-sizing-field)=

## sizing_field suite

The `sizing_field` suite runs all standalone sizing-field tasks, one for each
supported unified mesh.

```none
mesh/spherical/unified/u.oi.so12to30.lr10/sizing_field/task
mesh/spherical/unified/u.oi240.lr240/sizing_field/task
mesh/spherical/unified/u.oi30.lr10/sizing_field/task
mesh/spherical/unified/u.oi6to18.lr6to10/sizing_field/task
```

(mesh-suite-base-mesh)=

## base_mesh suite

The `base_mesh` suite runs all standalone base-mesh tasks, one for each
supported unified mesh.

```none
mesh/spherical/unified/u.oi.so12to30.lr10/base_mesh/task
mesh/spherical/unified/u.oi240.lr240/base_mesh/task
mesh/spherical/unified/u.oi30.lr10/base_mesh/task
mesh/spherical/unified/u.oi6to18.lr6to10/base_mesh/task
```
