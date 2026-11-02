(landice-suites)=

# Suites

The landice component includes {ref}`suites` that run a series of landice
tasks and optionally compare them against a baseline run of the same tasks.
To set one up, run:

```bash
polaris suite -c landice -t <suite_name> ...
```

(landice-suite-mali-pr)=

## mali_pr suite

The `mali_pr` suite is for testing pull requests that change MALI or the
Polaris framework.  Its tasks check that MALI's results do not depend on the
domain decomposition or on restarts, with the shallow-ice and first-order
velocity solvers.  The first-order tasks need a Polaris environment with
Albany (see {ref}`dev-landice-albany`).

```none
landice/dome/2km/sia/decomp
landice/dome/2km/sia/restart
landice/dome/2km/fo/decomp
landice/dome/2km/fo/restart
```

(landice-suite-mismip-plus)=

## mismip_plus suite

The `mismip_plus` suite runs the MISMIP+ experiments that end by 200 years
from the cached steady state (see {ref}`landice-mismip-plus`).  Each
experiment takes hours on several nodes, so the suite is not meant for
testing pull requests.

```none
landice/mismip_plus/1km/ice0
landice/mismip_plus/1km/ice1r
landice/mismip_plus/1km/ice1ra
landice/mismip_plus/1km/ice2r
landice/mismip_plus/1km/ice2ra
```
