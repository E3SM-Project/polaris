(ocean-suites)=

# Suites

The ocean component includes a number of {ref}`suites` that can be used to
run a series of ocean tasks and optionally compare them against a baseline
run of the same tasks.

(ocean-suite-cosine-bell)=

## cosine_bell and cosine_bell_cached_init suite

```bash
polaris suite -c ocean -t cosine_bell ...
```

```bash
polaris suite -c ocean -t cosine_bell_cached_init ...
```

Both `cosine_bell` suites include the following tasks:

```none
ocean/global_convergence/icos/cosine_bell
ocean/global_convergence/qu/cosine_bell
```

The `cosine_bell` suite runs both tasks from 
{ref}`ocean-cosine-bell` in full, whereas the
`cosine_bell_cached_init` suite only runs the ocean simulations from as set
of meshes and initial conditions that have been saved from a previous run
(see {ref}`dev-cache`).
