(dev-coriolis)=

# Coriolis

The module `polaris.coriolis` adds the Coriolis parameter to a horizontal
mesh dataset.  Each of its functions sets `fCell`, `fEdge` and `fVertex` on
the dataset it is given, with a `long_name`, a `standard_name` of
`coriolis_parameter` and units of `radians s^-1`, and returns the updated
dataset.

Nothing in the module is specific to a component: it reads the coordinates
that any MPAS mesh has (`xCell`, `yCell`, `lonCell`, `latCell` and their edge
and vertex counterparts) and writes mesh fields.  It is therefore available to
the ocean, sea ice and any future component.

## From config options

Most init steps use {py:func}`polaris.coriolis.add_coriolis_to_dataset()`,
which chooses the kind of Coriolis from the `[coriolis]` config section:

```python
import xarray as xr

from polaris.coriolis import add_coriolis_to_dataset
from polaris.step import Step


class Init(Step):
    def run(self):
        ds_mesh = xr.open_dataset('culled_mesh.nc')
        ds_mesh = add_coriolis_to_dataset(self.config, ds_mesh)
```

The `type` option selects one of five kinds, and each kind reads only the
parameters that belong to it:

| `type`           | parameters read                       |
|------------------|---------------------------------------|
| `zero`           | none                                  |
| `constant`       | `constant_f`                          |
| `beta_plane`     | `beta_plane_f0`, `beta_plane_beta`    |
| `spherical`      | none                                  |
| `rotated_sphere` | `rotated_sphere_alpha`                |

`polaris/default.cfg` declares all five options but gives none of them a
value.  A task that needs Coriolis has to say which kind it wants, and with
which parameters, in its own config file:

```cfg
[coriolis]

# type of Coriolis: zero, constant, beta_plane, spherical, or rotated_sphere
type = constant

# the constant Coriolis parameter
constant_f = 1.0e-4
```

A task that forgets gets a `ValueError` naming the option it left unset,
rather than a mesh that silently has no rotation.  A task that wants no
rotation says `type = zero`; that is a statement about the task rather than a
default it fell into.  The options it does not use may stay blank, since they
are never read.

An option can also be set at run time, when its value depends on something the
config file cannot express.  For example,
{py:class}`polaris.tasks.ocean.barotropic_gyre.init.Init` computes `f0` from
the domain size before adding the fields:

```python
config.set('coriolis', 'beta_plane_f0', str(f0))
ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
```

## Directly

A step that should not be configurable calls the helper for the kind it needs
and skips the config section altogether.  This suits steps whose output is a
released data product, where "not configurable" is a stronger guarantee than
"configured well by default":

* {py:func}`polaris.coriolis.add_zero_coriolis()`
* {py:func}`polaris.coriolis.add_constant_coriolis()` --- an f-plane
* {py:func}`polaris.coriolis.add_beta_plane_coriolis()` --- `f0 + beta * y`
* {py:func}`polaris.coriolis.add_spherical_coriolis()` --- `2 omega sin(lat)`
  for the Earth's rotation axis
* {py:func}`polaris.coriolis.add_rotated_sphere_coriolis()` --- the same for an
  axis tilted by `alpha` radians out of the geographic pole, used by the
  geostrophic test case

The two spherical helpers take an optional `omega`, defaulting to the Earth's
`angular_velocity` from {py:func}`polaris.constants.get_constant()`.
