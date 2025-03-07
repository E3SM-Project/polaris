(ocean-suites)=

# Suites

The ocean component includes a number of {ref}`suites` that can be used to
run a series of ocean tasks and optionally compare them against a baseline
run of the same tasks.

(ocean-suite-cosine-bell)=

## cosine_bell suite

```bash
polaris suite -c ocean -t cosine_bell ...
```

The `cosine_bell` suite includes the following tasks:

```none
ocean/spherical/icos/cosine_bell/convergence_space
ocean/spherical/icos/cosine_bell/convergence_space/with_viz
ocean/spherical/icos/cosine_bell/convergence_time
ocean/spherical/icos/cosine_bell/convergence_time/with_viz
ocean/spherical/icos/cosine_bell/convergence_both
ocean/spherical/icos/cosine_bell/convergence_both/with_viz
ocean/spherical/icos/cosine_bell/decomp
ocean/spherical/icos/cosine_bell/restart
ocean/spherical/qu/cosine_bell/convergence_space
ocean/spherical/qu/cosine_bell/convergence_space/with_viz
ocean/spherical/qu/cosine_bell/convergence_time
ocean/spherical/qu/cosine_bell/convergence_time/with_viz
ocean/spherical/qu/cosine_bell/convergence_both
ocean/spherical/qu/cosine_bell/convergence_both/with_viz
ocean/spherical/qu/cosine_bell/decomp
ocean/spherical/qu/cosine_bell/restart
```

