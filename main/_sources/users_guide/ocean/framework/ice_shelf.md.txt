(ocean-ice-shelf)=

# Ice shelf

The framework defines an `IceShelfTask` class that provides methods common
to tasks that feature ice shelf cavities. At present, the only method included
sets up ssh adjustment steps, described in ocean-ssh-adjustment.

(ocean-ssh-adjustment)=

## SSH adjustment steps

For tasks that feature ice shelf cavities, a series of forward simulations is
run in order to iteratively bring the SSH in equilibrium with the land ice
pressure. These steps are typically shared between all tasksthat also share
initial conditions and namelist options that influence the dynamics. Only the
output from the final SSH adjustment step is used as the initial state for the
forward step(s) of the task.

### config options

The following config options are used by SSH adjustment steps. The defaults are
shown here, but may be changed in a task's local config file.

```cfg
# Options related to ssh adjustment steps
[ssh_adjustment]

# Number of ssh adjustment iterations
iterations = 10

# Output interval for the ssh adjustment phase in hours
output_interval = 1.0

# Run duration of each ssh adjustment phase in hours
run_duration = 1.0

# Variable in init.nc that determines where to adjust SSH
mask_variable = adjustSSHMask

# Whether to adjust land ice pressure or SSH
adjust_variable = landIcePressure

# Time integration scheme
time_integrator = split_explicit

# Time step in seconds as a function of resolution
rk4_dt_per_km = 6

# Time step in seconds as a function of resolution
split_dt_per_km = 6

# Time step in seconds as a function of resolution
btr_dt_per_km = 1
```
