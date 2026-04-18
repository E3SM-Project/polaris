(dev-e3sm-init-tasks)=

# Tasks

## Topography Tasks

Topography tasks under `polaris.tasks.e3sm.init.topo` provide the task-family
implementation for processing, modifying, and combining topography datasets to
create inputs for E3SM components such as MPAS-Ocean, MPAS-Seaice, MOSART,
and ELM.

Shared topography-resolution utilities used across task families and
components live in `polaris.e3sm.init.topo`, not in
`polaris.tasks.e3sm.init.topo`. See {ref}`dev-e3sm-init-framework` for the
shared resolution constants and helper functions.

```{toctree}
:titlesonly: true

topo/combine
topo/remap
topo/cull
```
