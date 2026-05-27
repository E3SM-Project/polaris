# Z-Tilde Coordinate and Tracer Initialization

date: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

## Summary

The z-tilde (p-star) vertical coordinate used by Omega defines layer boundaries in
pseudo-height $\tilde{z} = -p / (\rho_0 g)$, where $p$ is sea pressure, $\rho_0$ is a
reference seawater density, and $g$ is gravitational acceleration. Because ocean
observations record geometric depth rather than pseudo-height, establishing the
pseudo-height of the seafloor (expressed in Omega as `BottomPressure`) requires knowing
the thermohaline structure of the water column and the equation of state (EOS). In turn,
the thermohaline structure must be sampled on the vertical grid that depends on
`BottomPressure`. This circular dependency means the vertical coordinate and the tracer
state must be determined jointly through iteration.

This design document describes:

1. A fixed-point iteration for determining `BottomPressure` (and therefore the z-tilde
   coordinate) such that the geometric seafloor depth recovered from the coordinate
   matches a target bathymetric depth within a configurable tolerance.
2. A pluggable interface for supplying conservative temperature (CT) and absolute salinity
   (SA) at each outer iteration step, supporting multiple initialization strategies
   without changes to the core algorithm.
3. The complete set of variables produced at convergence and their distribution across the
   separate output files established by the Polaris ocean framework.
4. The interaction between the proportional-ratio update and full or partial bottom cell
   snapping.

This capability is needed wherever the z-tilde coordinate must be initialized from a
known geometric seafloor depth. Its first concrete users are idealized test cases such as
`ocean/horiz_press_grad`, which already implements the algorithm but embeds it in
task-specific code, and the planned realistic initialization task described in the
companion design document [global_ocean_init.md](global_ocean_init.md). The design is
successful if the iteration logic is cleanly separated from the CT/SA initialization
strategy, and if the same base class and algorithm serve both idealized and realistic use
cases without modification.

The primary software challenge is providing a generalization pattern consistent with the
existing Polaris framework — specifically the convention of using overridable methods on
step subclasses, as exemplified by the convergence task framework — while keeping the
coupling between z-tilde coordinate construction, tracer initialization, and EOS
evaluation explicit and inspectable.

## Requirements

### Requirement: The z-tilde vertical coordinate can be initialized with a geometric seafloor depth matching target bathymetry within a configurable tolerance

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

Given a target geometric seafloor depth (equivalently, a target geometric water-column
thickness) and a means of obtaining conservative temperature and absolute salinity on the
resulting vertical grid, Polaris shall be able to initialize the z-tilde vertical
coordinate such that the geometric seafloor depth recovered from the converged coordinate
matches the target to within a configurable fractional tolerance.

The workflow shall support a configurable maximum number of iterations and shall terminate
early when the fractional change in the recovered geometric water-column thickness falls
below the tolerance. Both the convergence tolerance and the maximum iteration count shall
be configurable through the standard Polaris configuration mechanism.

### Requirement: CT and SA can be initialized on the z-tilde coordinate through a pluggable interface

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The workflow shall define a clear interface by which conservative temperature and absolute
salinity are supplied at each outer iteration step. This interface shall be general enough
to support multiple initialization strategies — including analytic profiles, piecewise
profiles defined by configuration values, and interpolation from an observational
hydrography dataset — without any change to the core iteration logic. The interface shall
be consistent in style with the generalization mechanisms already used in the Polaris
framework.

### Requirement: The initialized state includes all z-tilde coordinate variables and derived geometric quantities needed for subsequent steps

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The workflow shall produce at convergence all variables needed to configure the ocean
model, including z-tilde coordinate fields (pseudo-thickness, pseudo-height at midpoints
and interfaces, minimum and maximum valid level indices, cell mask, coordinate movement
weights), converged tracer fields, specific volume, pressure, `bottomDepth` consistent
with the converged geometric water-column thickness, and geometric height at layer
midpoints and interfaces.

These outputs shall be distributed across model-specific files according to the Polaris
ocean framework's split-file convention: vertical coordinate variables shall be written to
a separate vertical-coordinate file for Omega (where they feed the `InitialVertCoord`
stream) or kept in the initial-state file for MPAS-Ocean. The outputs shall be sufficient
for subsequent forward-model steps without re-running the iteration.

### Requirement: Full and partial bottom cells are handled correctly within the iteration

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

When full or partial bottom cell behavior is requested, the iteration shall handle the
discrete snapping of the pseudo-bottom-depth to layer boundaries in a manner that is
consistent with the converged state. The design shall specify how to detect and handle the
case where snapping prevents further convergence.

### Requirement: The capability is reusable across idealized and realistic initialization tasks

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The same iteration algorithm shall be applicable to both idealized test cases and
observationally-constrained realistic initialization tasks without duplication of the core
loop. Task-specific initialization of CT and SA shall be separable from the shared
iteration logic.

## Algorithm Design

### Algorithm Design: The z-tilde vertical coordinate can be initialized with a geometric seafloor depth matching target bathymetry within a configurable tolerance

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The core algorithm is a fixed-point iteration in pseudo-height space. Let:

- $H_\text{geo}^\star$ = target geometric water-column thickness
  (target bathymetric depth minus sea-surface height $\eta$)
- $P_\text{bot}^{(k)}$ = `BottomPressure` at iteration $k$
- $\hat{P}_\text{bot}^{(k)}$ = post-snap `BottomPressure` after applying full or partial
  bottom-cell constraints inside the coordinate-construction step
- $H_\text{geo}^{(k)}$ = geometric water-column thickness recovered at iteration $k$

The initial guess uses the reference density $\rho_0$ and gravitational acceleration $g$:

$$P_\text{bot}^{(0)} = P_\text{surf} + \rho_0\, g\, H_\text{geo}^\star$$

where $P_\text{surf}$ is the surface pressure (typically zero or a prescribed free-surface
value).

At each iteration $k$:

1. Construct the z-tilde coordinate from $P_\text{bot}^{(k)}$, obtaining `ZTildeMid`,
   `ZTildeInterface`, `PseudoThickness`, and related fields. The coordinate-construction
   step may snap `BottomPressure` to a layer boundary for full or partial bottom cells;
   denote the snapped value $\hat{P}_\text{bot}^{(k)}$.
2. Obtain CT and SA at the z-tilde layer midpoints through the CT/SA initialization
   interface (see the next algorithm design section).
3. Compute sea pressure at each layer midpoint from pseudo-height:
   $p_\text{mid} = -\rho_0 g \tilde{z}_\text{mid}$.
4. Evaluate the EOS to obtain specific volume:
   $\alpha = \text{EOS}(\text{CT},\, \text{SA},\, p_\text{mid})$.
5. Recover geometric layer thickness from pseudo-thickness and specific volume:
   $\delta z = \alpha\, \rho_0\, \delta\tilde{z}$.
6. Sum the geometric layer thicknesses upward from the seafloor to obtain the geometric
   water-column thickness $H_\text{geo}^{(k)}$.
7. Compute the proportional scaling factor:
   $s^{(k)} = H_\text{geo}^\star / H_\text{geo}^{(k)}$.
8. Check convergence: if $k > 0$ and
   $|H_\text{geo}^{(k)} - H_\text{geo}^{(k-1)}| / H_\text{geo}^{(k-1)} < \epsilon$
   (configurable tolerance), stop.
9. Check for full-cell stagnation: if
   $\hat{P}_\text{bot}^{(k)} = \hat{P}_\text{bot}^{(k-1)}$, stop early and log a warning
   (see the bottom-cell algorithm design section).
10. Update: $P_\text{bot}^{(k+1)} = \hat{P}_\text{bot}^{(k)} \cdot s^{(k)}$.

After convergence, `bottomDepth` is set to the actual recovered geometric water-column
thickness $H_\text{geo}^{(k)}$ (not the target $H_\text{geo}^\star$), so that the initial
condition is thermodynamically self-consistent and sea-surface height is exactly zero at
initialization even when bottom-cell snapping prevents an exact match to the target
bathymetry.

The iteration evaluates the EOS once per outer iteration (step 4 above). This is distinct
from the inner fixed-point iteration in
`pressure_and_spec_vol_from_state_at_geom_height` in
`polaris/ocean/vertical/ztilde.py`, which recovers pressure from geometric layer
thicknesses when pseudo-height is not known directly. In the present algorithm, pressure
is derived analytically from pseudo-height (step 3), so the inner iteration is not
invoked within the outer loop.

### Algorithm Design: CT and SA can be initialized on the z-tilde coordinate through a pluggable interface

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The CT/SA initialization interface is realized as an overridable method on a base step
class. The method receives the current z-tilde dataset — which contains `ZTildeMid`,
`ZTildeInterface`, `PseudoThickness`, `cellMask`, `minLevelCell`, `maxLevelCell`, and
associated coordinate information — and returns CT and SA as arrays with dimensions
`(Time, nCells, nVertLevels)`.

This follows the same generalization pattern used in the convergence task framework,
where concrete subclasses implement or override step methods that are invoked by shared
base-class logic.

Several concrete initialization strategies are envisioned:

1. **Piecewise pseudo-height profiles from config** (current `horiz_press_grad` approach):
   node values of CT and SA are read from the configuration at specified pseudo-height
   levels, and a monotone interpolant (e.g., PCHIP) maps them to each layer midpoint.
2. **Analytic profiles**: CT and SA are computed from a formula as a function of
   pseudo-height, geometric depth, or another column coordinate.
3. **Observational hydrography** (planned for realistic initialization): CT and SA are
   interpolated from a pre-processed hydrography product that has already been remapped
   to the MPAS horizontal mesh; at each outer iteration, vertical interpolation from the
   source depth levels to the current z-tilde midpoints is performed. This strategy is
   described in more detail in [global_ocean_init.md](global_ocean_init.md).

The interface constrains only what the method receives and returns; it does not constrain
how CT and SA are computed. The method may access `self.config`, `self.logger`, or any
other attributes of the step instance.

### Algorithm Design: The initialized state includes all z-tilde coordinate variables and derived geometric quantities needed for subsequent steps

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The Polaris ocean framework separates model inputs into three files. The horizontal mesh
file (`mesh.nc` or `culled_mesh.nc`) is not produced by the z-tilde initialization step;
it comes from an upstream mesh-construction or cull step. The z-tilde initialization step
produces the remaining two files.

**Vertical coordinate file** (`vert_coord.nc`, written by `write_vert_coord_dataset`):
For Omega this file feeds the `InitialVertCoord` stream. For MPAS-Ocean
`write_vert_coord_dataset` is a no-op and these variables remain in the initial-state
file instead. Variable names in parentheses are the Omega-native equivalents after the
framework's variable renaming.

| MPAS-Ocean variable | Omega variable | Description | Key dimensions |
|---|---|---|---|
| `minLevelCell` | `MinLayerCell` | First valid layer index (1-based) | nCells |
| `maxLevelCell` | `MaxLayerCell` | Last valid layer index (1-based) | nCells |
| `bottomDepth` | `BottomGeomDepth` | Actual geometric water-column thickness | nCells |
| `RefPseudoThickness` | `RefPseudoThickness` | Reference pseudo-thickness (no Time dim) | nCells, nVertLevels |
| `vertCoordMovementWeights` | `VertCoordMovementWeights` | Weights for coordinate movement | nVertLevels |

**Initial-state file** (`init.nc`, written by `write_initial_state_dataset`): horizontal
mesh variables are stripped before writing; for Omega, the vertical coordinate variables
above are also stripped (they are in `vert_coord.nc` instead).

| MPAS-Ocean variable | Omega variable | Description | Key dimensions |
|---|---|---|---|
| `temperature` | `Temperature` | Conservative temperature (CT) at convergence | Time, nCells, nVertLevels |
| `salinity` | `Salinity` | Absolute salinity (SA) at convergence | Time, nCells, nVertLevels |
| `normalVelocity` | `NormalVelocity` | Initial velocity (typically zero) | Time, nEdges, nVertLevels |
| `PseudoThickness` | `PseudoThickness` | Pseudo-layer thickness | Time, nCells, nVertLevels |
| `ZTildeMid` | `ZTildeMid` | Pseudo-height at layer midpoints | Time, nCells, nVertLevels |
| `ZTildeInterface` | `ZTildeInterface` | Pseudo-height at layer interfaces | Time, nCells, nVertLevelsP1 |
| `SurfacePressure` | `SurfacePressure` | Surface pressure | nCells |
| `BottomPressure` | `BottomPressure` | Effective (post-snap) seafloor pressure | nCells |
| `cellMask` | `cellMask` | Boolean mask of valid layers | nCells, nVertLevels |
| `pressure` | `PressureMid` | Sea pressure at layer midpoints | Time, nCells, nVertLevels |
| `zMid` / `GeomZMid` | `GeomZMid` | Geometric height at layer midpoints | Time, nCells, nVertLevels |
| `zInterface` / `GeomZInterface` | `GeomZInterface` | Geometric height at layer interfaces | Time, nCells, nVertLevelsP1 |

Additional task-specific diagnostic variables (e.g., `SpecVol`, `Density`, Montgomery
potential fields) may be included in `init.nc` by concrete subclasses.

### Algorithm Design: Full and partial bottom cells are handled correctly within the iteration

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The z-tilde coordinate-construction step (`init_z_tilde_vertical_coord` in
`polaris/ocean/vertical/ztilde.py`) already handles full and partial bottom cells by
snapping `BottomPressure` to a discrete layer boundary before returning. Within the outer
iteration, the proportional-ratio update (step 10 of the algorithm) is applied to the
post-snap value $\hat{P}_\text{bot}^{(k)}$, not the raw value $P_\text{bot}^{(k)}$. This
ensures that each successive iterate moves relative to the effective snapped position and
prevents the iteration from swinging between two snapping levels.

For full-cell configurations, `BottomPressure` is forced to the bottom of a reference
layer regardless of the incoming value. Once the iteration converges on the nearest full
cell, $\hat{P}_\text{bot}^{(k)}$ no longer changes between iterations even though the
scaling factor $s^{(k)}$ may differ from 1. The algorithm detects stagnation by comparing
$\hat{P}_\text{bot}^{(k)}$ to $\hat{P}_\text{bot}^{(k-1)}$ and stops early, logging a
warning that reports the residual mismatch between the recovered and target geometric
water-column thicknesses. The residual is bounded by the reference pseudo-layer spacing at
the seafloor.

For partial-cell configurations, `BottomPressure` is allowed to vary continuously between
the partial-cell minimum threshold and the full-cell boundary. Convergence within this
window is generally achievable, and the stagnation check triggers only if the partial-cell
constraints force a discrete jump.

### Algorithm Design: The capability is reusable across idealized and realistic initialization tasks

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The iteration algorithm is encapsulated in a base step class (see the implementation
section) that provides the outer fixed-point loop, output dataset assembly, convergence
checking, full-cell stagnation detection, and iteration logging. Concrete subclasses
supply only the CT/SA initialization method, making it straightforward to add new
initialization strategies without touching the core algorithm.

The `horiz_press_grad.Init` step is the first concrete implementation. The planned
realistic initialization step will be the second. No changes to the base class are
anticipated when adding new CT/SA initialization strategies.

## Implementation

### Implementation: The z-tilde vertical coordinate can be initialized with a geometric seafloor depth matching target bathymetry within a configurable tolerance

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The outer fixed-point loop currently embedded as a private sequence in
`polaris/tasks/ocean/horiz_press_grad/init.py` shall be extracted into a reusable
`run_z_tilde_init` method on a new `ZTildeInitStep` base class in
`polaris/ocean/vertical/ztilde_init.py`. The `horiz_press_grad.Init` class shall then be
refactored to inherit from `ZTildeInitStep` and implement the `init_tracers` abstract
method, with all other iteration logic removed from that class.

The convergence threshold and maximum iteration count shall be read from the
`vertical_grid` configuration section. The `pseudothickness_iter_count` option already
exists in that section. The fractional-change threshold (`water_col_adjust_frac_change_threshold`) is currently in the `horiz_press_grad`
section and should be moved to `vertical_grid` so that it is available to all users of the
base class without requiring task-specific configuration.

### Implementation: CT and SA can be initialized on the z-tilde coordinate through a pluggable interface

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The CT/SA initialization interface shall be declared using Python's `abc.abstractmethod`
decorator on the `ZTildeInitStep` base class, which shall itself inherit from
`OceanIOStep`. The required method signature is:

```python
@abstractmethod
def init_tracers(
    self, ds: xr.Dataset
) -> tuple[xr.DataArray, xr.DataArray]:
    """
    Initialize CT and SA at z-tilde layer midpoints for the current iteration.

    Parameters
    ----------
    ds : xarray.Dataset
        Current z-tilde dataset, including ZTildeMid, ZTildeInterface,
        PseudoThickness, cellMask, minLevelCell, and maxLevelCell.

    Returns
    -------
    conservative_temperature : xarray.DataArray
        CT with dimensions (Time, nCells, nVertLevels).
    absolute_salinity : xarray.DataArray
        SA with dimensions (Time, nCells, nVertLevels).
    """
```

The existing `horiz_press_grad.Init._interpolate_t_s` private method becomes the concrete
`init_tracers` implementation in the refactored `horiz_press_grad.Init` subclass, with no
change to its logic.

### Implementation: The initialized state includes all z-tilde coordinate variables and derived geometric quantities needed for subsequent steps

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The base class `run_z_tilde_init` method shall assemble the output dataset from the
quantities accumulated during the outer loop and return it. The concrete subclass `run`
method shall then write the split output files using the framework helpers:

```python
self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
self.write_initial_state_dataset(ds, 'init.nc', config)
```

`write_vert_coord_dataset` is a no-op for MPAS-Ocean; `write_initial_state_dataset`
strips horizontal mesh variables and (for Omega) also strips vertical coordinate variables
before writing. The concrete subclass should register `vert_coord.nc` as an output file
only for Omega (e.g., using the `setup` override pattern already used by other tasks) or
unconditionally if the step is Omega-only.

Any model-specific or task-specific fields not part of the z-tilde base output (e.g.,
`normalVelocity`, pressure-gradient diagnostics) shall be added to `ds` by the concrete
subclass before calling the write helpers. The horizontal mesh file is written separately
by the upstream mesh step and is not produced by `ZTildeInitStep`.

### Implementation: Full and partial bottom cells are handled correctly within the iteration

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The stagnation-detection logic already present in `horiz_press_grad/init.py` (comparing
the post-snap `BottomPressure` between consecutive iterations) shall be preserved
verbatim when moved into the base class. The warning message shall report the iteration
number, the stagnant `BottomPressure` value, and the residual geometric water-column
mismatch, to aid debugging on meshes where full-cell behaviour is unexpected.

### Implementation: The capability is reusable across idealized and realistic initialization tasks

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The immediate implementation priority is to refactor `horiz_press_grad.Init` onto
`ZTildeInitStep` and verify that all existing `horiz_press_grad` regression tests pass
without modification. This confirms the interface is correct before additional subclasses
are written. The refactored `horiz_press_grad.Init` already uses the three-file split
(`culled_mesh.nc`, `vert_coord.nc`, `init.nc`) introduced by the `split-mesh-and-init`
changes; the base class must therefore be consistent with this pattern from the start.

The planned realistic initialization step (`ocean/realistic/init`) will then subclass
`ZTildeInitStep` and implement `init_tracers` to read from the WOA hydrography product
described in [global_ocean_init.md](global_ocean_init.md). In that context, CT/SA
initialization at each outer iteration involves sampling a pre-computed hydrography
product that has been remapped to the MPAS horizontal mesh, then interpolating vertically
from the source depth levels to the current z-tilde layer midpoints. The mesh file for
realistic initialization comes from an upstream `e3sm/init` cull step rather than being
constructed by the init step itself, so only `vert_coord.nc` and `init.nc` are produced
by `ZTildeInitStep` in that context.

## Testing

### Testing and Validation: The z-tilde vertical coordinate can be initialized with a geometric seafloor depth matching target bathymetry within a configurable tolerance

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The existing `horiz_press_grad` regression tests provide the primary validation: after
refactoring onto the base class, all three task variants (`salinity_gradient`,
`temperature_gradient`, `ztilde_gradient`) shall produce the same outputs as before.
These tests cover convergence against known analytic profiles and therefore implicitly
validate that the geometric seafloor depth matches the target within the configured
tolerance.

Unit tests should additionally cover a single-column case with a constant-density profile
(where $s^{(k)} = 1$ at the first iteration and the loop terminates immediately) and a
case with a density gradient (where multiple iterations are required). Each test should
check that the final `bottomDepth` differs from the target by less than the convergence
tolerance.

### Testing and Validation: CT and SA can be initialized on the z-tilde coordinate through a pluggable interface

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

A test should confirm that attempting to instantiate `ZTildeInitStep` directly, without
implementing `init_tracers`, raises `TypeError`. A separate test should confirm that a
minimal concrete subclass with a constant `init_tracers` implementation completes the
outer loop without error and produces an output dataset containing all required variables.

### Testing and Validation: The initialized state includes all z-tilde coordinate variables and derived geometric quantities needed for subsequent steps

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

Regression tests for `horiz_press_grad` shall verify that the output dataset produced by
the refactored base class contains all variables listed in the algorithm design section,
with correct dimensions and non-NaN values in valid cells. A consistency check shall
verify that `GeomZMid` and `GeomZInterface` are internally consistent with
`PseudoThickness` and `SpecVol` to within floating-point precision.

### Testing and Validation: Full and partial bottom cells are handled correctly within the iteration

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

The `horiz_press_grad` task includes configurations with `partial_cell_type = full` and
`partial_cell_type = partial`. Regression tests for these configurations shall verify
that: the full-cell stagnation logic stops the outer loop when `BottomPressure` is pinned
to a reference level; and that the final `bottomDepth` is within one pseudo-layer
thickness of the target for partial-cell configurations. A unit test shall directly inject
a stagnant `BottomPressure` to confirm that the warning is issued and the loop terminates
after the first stagnation is detected.

### Testing and Validation: The capability is reusable across idealized and realistic initialization tasks

Date last modified: 2026/05/27

Contributors: Xylar Asay-Davis, Claude

Once the realistic initialization task (`ocean/realistic/init`) is implemented, its
regression tests shall exercise the shared base class with WOA-derived CT/SA on at least
one small or moderate-resolution global mesh. These tests shall confirm that the outer
loop converges and that the output dataset is complete, without any modification to the
base class.
