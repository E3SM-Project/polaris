# MPAS-Ocean

The following are considerations that may be useful in developing a test case for MPAS-Ocean

## Initial conditions

The minimal set of initial state variables that must be defined in the `initial_state` step of each test case is:

* `temperature`
* `salinity`
* `normalVelocity`
* `fCell`
* `fEdge`
* `fVertex`

## Boundary conditions

The following horizontal boundary conditions are supported for planar domains

* periodic
* free slip (solid boundary, `normalVelocity = 0` at edges of the domain,
tangential force is 0)

These horizontal boundary conditions are enforced at the stage at which the
planar mesh is constructed, by specifying `nonperiodic` as true or false.

The following vertical boundary conditions are supported:

* free slip (tangential force is 0, drag is disabled). Generally only used for
the free surface.
* free surface with specified flux (of mass, momentum, and/or scalars).
Generally only possible at the top boundary.
* rigid surface with no slip (velocity normal to the surface is zero,
tangential force is non-zero because bottom or top drag is applied). While the
boundary is no-slip, `normalVelocity` is solved at the mid-point of the layer
and is generally non-zero.

## Forcing

Constant or time-varying forcing is possible for some properties. The forcing
fields (generally 2-d and applied at the surface) are generally read in from a
forcing stream. For more details, start by consulting the Registry under the
headings `forcing` and `tidal_forcing`.
