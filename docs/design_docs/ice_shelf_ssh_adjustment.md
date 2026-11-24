# Solving for SSH Under Ice Shelves

Creation date: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

## Summary

Tasks with ice-shelf cavities need a sea-surface height (SSH) under the ice
that is in dynamic balance with the land-ice pressure. Otherwise, the first
hours of a simulation are spent in a large adjustment of SSH, with fast
barotropic currents and waves. Polaris currently gets there by iterating: it
runs the model for an hour, takes the SSH at the end (or changes the land-ice
pressure to match it), and repeats about 10 times.

This design adds a second method. A single short model step from rest
measures the depth-mean acceleration everywhere. A least-squares solve then
finds the change in SSH under the ice whose pressure gradient cancels that
acceleration. One or two passes cost a few model time steps rather than hours
of simulation, and the land-ice pressure that comes from the ice thickness is
kept.

Success means that, for the `ice_shelf_2d` tasks, the method removes most of
the acceleration in one pass, a second pass changes SSH far less than the
first, and the forward runs that follow start without a large adjustment.

## Requirements

### Requirement: SSH is consistent with a prescribed land-ice pressure

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The SSH under ice shelves shall be adjusted until the depth-mean flow from
rest has no significant acceleration, as computed by the time integrator that
the forward runs use. The land-ice pressure shall not change.

### Requirement: Adjustment is fast

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The cost of SSH adjustment shall be a small number of model time steps.

### Requirement: Adjustment does not depend on the ocean model

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The adjustment shall need only the horizontal mesh, the initial state and
standard model output, so that it can work with MPAS-Ocean and Omega alike.

### Requirement: Columns do not empty

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

SSH adjustment shall stop with an error rather than leave a water column
under the ice with no thickness.

### Requirement: The iterative method remains available

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

Tasks shall be able to keep the iterative method until they are moved to the
new one.

## Algorithm Design

### Algorithm Design: SSH is consistent with a prescribed land-ice pressure

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The model takes one step of length $\Delta t$ from rest, with the time
integrator of the forward runs. With split-explicit, the barotropic velocity
at the end of the step is the mean over subcycles spanning $2\Delta t$, which
for velocity growing linearly from rest is the same as at $\Delta t$. For each
edge
$e$, the depth-mean acceleration is

$$
a_e = \frac{1}{H_e \Delta t} \sum_k h_{e,k} u_{e,k},
$$

where $u_{e,k}$ is the normal velocity at the end of the step, $h_{e,k}$ is
the mean of the layer thicknesses of the two cells on the edge, and the sum
covers only the layers both cells have. $H_e = \sum_k h_{e,k}$.

A change in SSH, $\delta\eta$, changes the depth-mean acceleration by
$-g\,\nabla\delta\eta$. The solve finds the $\delta\eta$ on the cells under
the ice that minimizes

$$
\sum_e w_e \left( a_e - g \frac{\delta\eta_{c_2(e)} - \delta\eta_{c_1(e)}}
{d_{c,e}} \right)^2, \qquad w_e = H_e\, d_{c,e}\, d_{v,e},
$$

over every wet edge with a cell under the ice on either side, with
$\delta\eta = 0$ elsewhere. The weight makes the sum proportional to the
kinetic energy the remaining acceleration would produce. The normal
equations are a weighted graph Laplacian on the cells under the ice and are
solved directly.

The new SSH is $\eta + \delta\eta$. Layer thicknesses follow from the
vertical coordinate, and temperature and salinity are kept in each layer.

What the solve cannot remove is the part of the acceleration that is not a
gradient, mostly from the baroclinic pressure gradient. A second pass
measures what is left after the layers have moved.

### Algorithm Design: Adjustment is fast

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

$\Delta t$ is 1 s per km of resolution, so a gravity wave crosses only a
small fraction of a cell during the step and the measured acceleration is
that of the initial state.

## Implementation

### Implementation: SSH is consistent with a prescribed land-ice pressure

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

`[ssh_adjustment] method = solve` selects the new method.
`polaris.ocean.ice_shelf.ssh_solve` holds two functions:
`compute_depth_mean_acceleration()` and `solve_for_ssh_change()`. With the
solve method, `SshForward` runs a single step with
`[ssh_adjustment] time_integrator`, with output before and after it, and `SshAdjustment` calls the two functions and then
`update_layer_thickness()`. The cells that may change are those in
`mask_variable`. `iterations` sets the number of passes.

The solve method only adjusts SSH. `adjust_variable` now defaults to `ssh`,
and `ice_shelf_2d` moves to the solve method with two passes, using
split-explicit, or RK4 for the single-layer tasks, as its forward runs do.

### Implementation: Adjustment is fast

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

`[ssh_adjustment] solve_dt_per_km` sets $\Delta t$.

### Implementation: Adjustment does not depend on the ocean model

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The functions in `ssh_solve` read `cellsOnEdge`, `dcEdge` and `dvEdge` from
the mesh, `minLevelCell` and `maxLevelCell` from the initial state, and
`normalVelocity`, `layerThickness` and `daysSinceStartOfSim` from the
output. Only the model configuration of `SshForward` is model specific.

### Implementation: Columns do not empty

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

`SshAdjustment` raises an error, naming the number of columns and the
thinnest, if any column under the ice would have no thickness.

### Implementation: The iterative method remains available

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

`method = iterate` is the default and works as before.
`[ssh_adjustment] time_integrator` is now passed on to the model; it
defaults to `split_explicit_ab2`, the integrator these runs used before.

## Testing

### Testing and Validation: SSH is consistent with a prescribed land-ice pressure

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

Unit tests check that the solve flattens a bump in SSH exactly, leaves cells
outside the mask alone, and that the depth-mean acceleration weights layers
by thickness and uses only the layers shared across an edge.

The `ice_shelf_2d` tasks at 5 and 2 km with z-star and z-level coordinates
run with two passes. The second pass's measured acceleration shows how much
the first removed.

### Testing and Validation: Adjustment is fast

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The `ssh_forward` steps of `ice_shelf_2d` each run a single time step.

### Testing and Validation: Adjustment does not depend on the ocean model

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The unit tests build their inputs without a model. Omega support for
ice-shelf tasks is outside this design.

### Testing and Validation: Columns do not empty

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The error is raised if `ice_shelf_2d` is set up with water columns too thin
for the SSH change.

### Testing and Validation: The iterative method remains available

Date last modified: 2026/11/23

Contributors:

- Xylar Asay-Davis
- Claude

The ISOMIP+ tasks under development use the iterative method and can be
checked once they are rebased onto this work.
