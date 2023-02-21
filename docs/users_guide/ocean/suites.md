(ocean-suites)=

# Test suites

The ocean component includes a number of {ref}`test-suites` that can be used to
run a series of ocean test cases and optionally compare them against a baseline
run of the same tests.

(ocean-suite-cosine-bell)=

## cosine_bell and cosine_bell_cached_init test suite

```bash
polaris suite -c ocean -t cosine_bell ...
```

```bash
polaris suite -c ocean -t cosine_bell_cached_init ...
```

Both `cosine_bell` test suites include the following test cases:

```none
ocean/global_convergence/icos/cosine_bell
ocean/global_convergence/qu/cosine_bell
```

The `cosine_bell` suite runs both tests from 
{ref}`ocean-global-convergence-cosine-bell` in full, whereas the
`cosine_bell_cached_init` suite only runs the ocean simulations from as set
of meshes and initial conditions that have been saved from a previous run
(see {ref}`dev-cache`).
