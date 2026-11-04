(landice)=

# Land-ice component

The `landice` component in polaris contains tasks for
[MALI](https://mpas-dev.github.io/land_ice/land_ice.html), the MPAS-Albany
Land Ice model.  MALI's first-order velocity solver comes from the
[Albany](https://github.com/sandialabs/Albany) library, so tasks that use it
need a Polaris environment deployed with Albany (see
{ref}`dev-landice-albany`).

Some helpful external links related to MALI:

- MPAS website: <https://mpas-dev.github.io>

- MALI development happens on the `develop` branch of
  <https://github.com/MALI-Dev/E3SM>

- [Hoffman et al. (2018)](https://doi.org/10.5194/gmd-11-3747-2018)
  describe the model.

```{toctree}
:titlesonly: true

tasks/index
suites
```
