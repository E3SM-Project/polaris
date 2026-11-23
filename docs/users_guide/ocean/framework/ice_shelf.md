(ocean-ice-shelf)=

# Ice shelf

The framework defines an `IceShelfTask` class that provides methods common
to tasks that feature ice shelf cavities.  It sets up ssh adjustment steps,
described in {ref}`ocean-ssh-adjustment`.

Ice-shelf tasks need the land-ice options in MPAS-Ocean from
[E3SM-Project/E3SM#8047](https://github.com/E3SM-Project/E3SM/pull/8047),
which are on the FAnSSIE branch but not yet in E3SM-Project.  Setting up an
ice-shelf task with an MPAS-Ocean build that lacks them fails with an error
that says to build MPAS-Ocean from the `e3sm_submodules/FAnSSIE` submodule
(see {ref}`dev-ocean-fanssie`).

(ocean-ssh-adjustment)=

## SSH adjustment steps

For tasks that feature ice shelf cavities, pairs of `ssh_forward` and
`ssh_adjust` steps bring the SSH into equilibrium with the land-ice pressure.
These steps are typically shared between all tasks that also share initial
conditions and namelist options that influence the dynamics. Only the output
from the final `ssh_adjust` step is used as the initial state for the forward
step(s) of the task.

There are two methods, chosen with `method`:

- `solve`: each `ssh_forward` step runs a single short step from rest, with
  `time_integrator`, which should be the one the task's forward runs use.  The
  `ssh_adjust` step computes the depth-mean acceleration on each edge, then
  solves for the change in SSH, under the ice only, whose pressure gradient
  cancels it. The solve is a least-squares fit weighted by the water-column
  thickness and the area each edge represents.  One pass removes most of the
  imbalance; a second measures what is left and removes most of that.
- `iterate`: each `ssh_forward` step runs the model for `run_duration` hours.
  The `ssh_adjust` step takes the SSH at the end of the run, or, with
  `adjust_variable = landIcePressure`, changes the land-ice pressure to match
  it.  It typically takes about 10 iterations.

The `solve` method adjusts only SSH.  We recommend it for new tasks, since it
is much faster than `iterate` and keeps the land-ice pressure that comes from
the ice thickness.

### config options

The following config options are used by SSH adjustment steps. The defaults are
shown here, but may be changed in a task's local config file.
`time_integrator` sets MPAS-Ocean's `config_time_integrator` and selects
which of the time steps per km applies.

```cfg
# Options related to ssh adjustment steps
[ssh_adjustment]

# How to make SSH consistent with the land-ice pressure: "iterate" runs the
# model for run_duration and takes its SSH at the end (or changes the
# land-ice pressure to match it); "solve" runs a single short step from rest
# and solves for the SSH change that cancels the depth-mean acceleration
method = iterate

# Number of ssh adjustment iterations
iterations = 10

# Output interval for the ssh adjustment phase in hours
output_interval = 1.0

# Run duration of each ssh adjustment phase in hours
run_duration = 1.0

# Variable in init.nc that determines where to adjust SSH
mask_variable = adjustSSHMask

# Whether to adjust land ice pressure or SSH
adjust_variable = ssh

# Time integration scheme: split_explicit_ab2, split_explicit or RK4
time_integrator = split_explicit_ab2

# Time step in seconds as a function of resolution
rk4_dt_per_km = 1.5

# Time step in seconds as a function of resolution
split_dt_per_km = 30

# Time step in seconds as a function of resolution
btr_dt_per_km = 1.5

# Time step in seconds as a function of resolution of the single step from
# rest that the "solve" method measures
solve_dt_per_km = 1.0
```

With `method = solve`, `output_interval`, `run_duration`, `rk4_dt_per_km`
and `split_dt_per_km` are not used.  The `ssh_adjust` step stops with an
error if the change in SSH would leave a water column under the ice with no
thickness; the water column under the ice must then be made thicker.
