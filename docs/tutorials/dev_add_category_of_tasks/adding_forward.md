# Adding a `forward` Step

Now that we know that the first step seems to be working, we're ready to add
another. We will add a `forward` step for running the MPAS-Ocean model forward
in time from the initial condition created in `init`.  `forward`
will be a little more complicated than `init` as we get started.
We're going to start from the {py:class}`polaris.ocean.model.OceanModelStep`
subclass that descends from {py:class}`polaris.ModelStep`, which in turn
descends from `Step`.  `ModelStep` adds quite a bit of useful functionality
for steps that run E3SM model components (MALI, MPAS-Ocean, MPAS-seaice or
Omega) and `OceanModelStep` adds on to that with some functionality specific to
the ocean. We'll explore some aspects of the functionality that each of these
subclasses brings in here, but there may be other capabilities that we don't
cover here that will be important for your tasks so it likely will be useful to
have a look at the general {ref}`dev-model` section and potentially the
ocean-specific {ref}`dev-ocean-model` section as well.  MALI and MPAS-seaice
steps will likely descend from `ModelStep`, though there may be advantages in
defining `LandiceModelStep` and `SeaiceModelStep` classes in the future.

We start with a `Forward` class that descends from `OceanModelStep` and a
constructor with the name of the step.  This time, we also supply the target
number of MPI tasks (`ntasks`), minimum number of MPI tasks (`min_tasks`), and
number of threads (the `init` used the default of 1 task, 1 CPU per
task and 1 thread):

```bash
$ vim polaris/tasks/ocean/my_overflow/forward.py
```
```python
from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):
    """
    A step for performing forward MPAS-Ocean runs as part of overflow
    test cases.
    """

    def __init__(
        self,
        component,
        init,
        name,
        indir,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
    ):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            the name of the task

        init : polaris.tasks.ocean.my_overflow.init.Init
            the initial state step

        indir : str
            The directory the task is in, to which ``name`` will be appended

        ntasks : int, optional
            the number of tasks the step would ideally use.  If fewer tasks
            are available on the system, the step will run on all available
            tasks as long as this is not below ``min_tasks``

        min_tasks : int, optional
            the number of tasks the step requires.  If the system has fewer
            than this number of tasks, the step will fail

        openmp_threads : int, optional
            the number of OpenMP threads the step will use
        """
        if min_tasks is None:
            min_tasks = ntasks
        super().__init__(
            component=component,
            name=name,
            indir=indir,
            ntasks=ntasks,
            min_tasks=min_tasks,
            openmp_threads=openmp_threads,
            update_eos=True,
            graph_target=f'{init.path}/culled_graph.info',
        )

```

By default, the number of MPI tasks `ntasks` isn't specified yet, nor is the
minimum number of MPI tasks `min_tasks`.  If they aren't specified explicitly,
they will be computed algorithmically later on based on the number of cells in
the mesh, as well discuss below. The constructor also takes the `component` and
the shared `init` step.  The subdirectory `indir` is the location within
the component's work directory of the taks that this step belongs to, to which
`name` will be appended to get the steps subdirectory.  This is in contrast
to `init`, which lives outside of any task because it is a step shared between
tasks.

Next, we add some inputs (from `init`) and outputs that we will define later:

```bash
$ vim polaris/tasks/ocean/my_overflow/forward.py
```
```{code-block} python
:emphasize-lines: 20-32

...

class Forward(OceanModelStep):

    ...

    def __init__(
        self,
        component,
        init,
        name,
        indir,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
    ):

        ...

        self.add_input_file(
            filename='initial_state.nc',
            work_dir_target=f'{init.path}/init.nc',
        )

        self.add_output_file(
            filename='output.nc',
            validate_vars=[
                'layerThickness',
                'normalVelocity',
                'temperature',
            ],
            check_properties=[
                'mass conservation',
            ],
        )
```

By defining `validate_vars` as part of the output, we ensure that these
variables will be compared with output from a baseline Polaris run if one
is provided to ensure that the results are identical.

## Defining model config options and streams

The E3SM components supported by Polaris require both model config options
and streams definitions (namelist and streams files for MPAS components, and
yaml files for Omega, see {ref}`dev-model-yaml-namelists-and-streams`) to work
properly.  An important part of Polaris' functionality is that it takes the
default model config options and E3SM component and modifies only those options
that are specific to the task to produce the final model config files used to
run the model.

In Polaris, there are two main ways to set model config options and we will
demonstrate both in this task.  First, you can define a namelist or yaml
file with the desired values.  This is useful for model config options that are
always the same for this task and can't be changed based on config options
from the Polaris config file.

In the ocean component, we want the same tasks to work with either Omega
or MPAS-Ocean.  We have decided to define model config options using the new
yaml file format that Omega will use, whereas the seaice and landice components
of Polaris will use the namelist and streams files that MPAS components use.
This tutorial will focus on the yaml format but the concepts will not be hugely
different for namelist and streams files.

Here is the `forward.yaml` file for `my_overflow` (a simplified version of
the one from `overflow`):

```bash
$ vim polaris/tasks/ocean/my_overflowl/forward.yaml
```
```yaml
mpas-ocean:
  time_management:
    config_stop_time: none
    config_run_duration: 0000_00:12:00
  time_integration:
    config_dt: 20.0
    config_time_integrator: split_explicit_ab2
  io:
    config_write_output_on_startup: false
  hmix_del2:
    config_use_mom_del2: true
    config_mom_del2: 1000.0
  bottom_drag:
    config_implicit_bottom_drag_type: constant
    config_implicit_constant_bottom_drag_coeff: 0.01
  cvmix:
    config_cvmix_background_scheme: none
    config_use_cvmix_convection: true
  split_explicit_ts:
    config_btr_dt: 5.0
  streams:
    mesh:
      filename_template: initial_state.nc
    input:
      filename_template: initial_state.nc
    restart:
      output_interval: 0010_00:00:00
    output:
      type: output
      filename_template: output.nc
      output_interval: 0000_00:00:01
      clobber_mode: truncate
      contents:
      - tracers
      - xtime
      - normalVelocity
      - layerThickness
      - ssh
      - vertVelocityTop
      - density
      - daysSinceStartOfSim
      - relativeVorticity
```

````{note}
For comparison, here is a typical seaice namelist file:
```none
config_nSnowLayers = 5

config_use_velocity_solver = false
config_use_advection = false

config_use_ocean_mixed_layer = false
```

And a truncated streams file:
```xml
<streams>
<immutable_stream name="mesh"
                  type="none"
                  filename_template="mesh_variables.nc" />

<immutable_stream name="input"
                  type="input"
                  filename_template="grid.nc"
                  filename_interval="none"
                  input_interval="initial_only" />

<immutable_stream name="restart"
                  type="input;output"
                  filename_template="restarts/restart.$Y-$M-$D_$h.$m.$s.nc"
                  filename_interval="00_00:00:01"
                  input_interval="initial_only"
                  output_interval="00-03-00_00:00:00" />

<stream name="output"
        type="output"
        filename_template="output/output.$Y.nc"
        filename_interval="01-00-00_00:00:00"
        clobber_mode="replace_files"
        output_interval="00-00-00_01:00:00" >

	<var name="xtime"/>
	<var name="daysSinceStartOfSim"/>
	<var name="iceAreaCell"/>
	<var name="iceVolumeCell"/>
	<var name="snowVolumeCell"/>
	<var name="surfaceTemperatureCell"/>
	<var name="shortwaveDown"/>
	<var name="longwaveDown"/>

</stream>

...

</streams>
```
````

There is also a shared `output.yaml` file for ocean tasks that makes sure
we get double-precision output (the default is single precision, which saves a
lot of space but isn't great for regression testing):

```yaml
mpas-ocean:
  streams:
    output:
      type: output
      precision: double
```


In the `forward` step, we add these namelists as follows:

```{code-block} python
:emphasize-lines: 20-23

...

class Forward(OceanModelStep):

    ...

    def __init__(
        self,
        component,
        init,
        name,
        indir,
        ntasks=None,
        min_tasks=None,
        openmp_threads=1,
    ):

        ...

        # make sure output is double precision
        self.add_yaml_file('polaris.ocean.config', 'output.yaml')

        self.add_yaml_file('polaris.tasks.ocean.my_overflow', 'forward.yaml')
```

The first argument to {py:meth}`polaris.ModelStep.add_yaml_file()` is the
python package where the namelist file can be found, and the second is the
file name.  Files within the polaris package can't be referenced directly
with a file path but rather with a package like in these examples.

The model config options will start with the default set for the E3SM
component, provided along with the model executable at the end of compilation.
For MPAS-Ocean, MPAS-seaice and MALI, this will be in
`default_inputs/namelist.<component>.forward`.  For Omega, this is
`configs/Default.yml`. Each time a yaml or namelist file is added to a step,
the model config options changed in that file will override the previous
values. So the order of the files may matter if the same model config options
are changed in multiple files in Polaris.

Streams are handled a little differently.  Again, the starting point is a set
of defaults from the E3SM components, either
`default_inputs/streams.<component>.forward` or `configs/Default.yml`.  But in
this case, streams are only included in the step if they are referenced in one
of the yaml or streams files added to it.  If you want the default definition
of a stream, referring to it is enough:

```yaml
mpas-ocean:
  streams:
    restart: {}
```

If you want to change one of its attributes but not its contents, you can do
that:
```yaml
mpas-ocean:
  streams:
    input:
      filename_template: initial_state.nc
```
Other attributes will remain as they are in the defaults.  You can
change the contents (the variables or arrays) of a stream in addition to the
attributes.  In this case, the contents you provide will replace the default
contents:

```bash
$ vim polaris/tasks/ocean/my_overflow/forward.yaml
```
```yaml
mpas-ocean:
  ...
  streams:
    output:
      type: output
      filename_template: output.nc
      output_interval: 0000_00:00:01
      clobber_mode: truncate
      contents:
      - tracers
      - xtime
      - normalVelocity
      - layerThickness
      - ssh
      - vertVelocityTop
      - density
      - daysSinceStartOfSim
      - relativeVorticity
```
Finally, you can add completely new streams that don't exist in the default
model config files to a step by defining all of the relevant streams attributes
and contents.  We don't demonstrate that in this tutorial.


## Dynamically Computhing the Number of Tasks

In the `ocean` component in steps that descend from `OceanModelStep`, it is
possible to compute the number of MPI tasks dynamically based on the mesh size.
This requires an estimate for the number of cells in the mesh, based on
config options such as the domain size and resolution.  To take advantage of
this, we override the `compute_cell_count()` method to estimate the cell count:

```{code-block} python
:emphasize-lines: 1, 9-25

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.model import OceanModelStep


class Forward(OceanModelStep):

    ...

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['my_overflow']
        lx = section.getfloat('lx')
        ly = section.getfloat('ly')
        resolution = section.getfloat('resolution')
        nx, ny = compute_planar_hex_nx_ny(lx, ly, resolution)
        cell_count = nx * ny
        return cell_count
```

So far, this type of capability hasn't been implemented in other components
but may come in the future.

## Adding the `forward` step to the task

Returning to the `default` task, we are now ready to add
`initial_state` and `forward` steps to the task.  In
`polaris/tasks/ocean/my_overflow/default/__init__.py`, we add:

```{code-block} python
:emphasize-lines: 2, 14-20

from polaris import Task
from polaris.tasks.ocean.my_overflow.forward import Forward


class Default(Task):

    ...

    def __init__(self, component, indir, init):
        ...

        self.add_step(init, symlink='init')

        forward_step = Forward(
            component=component,
            init=init,
            name='forward',
            indir=self.subdir,
        )
        self.add_step(forward_step)
```

We put the `forward` step in the `default` task's subdirectory and pass along
the shared init step.

### Testing

We're ready to run some more tests just like we did in
[Testing the First Task and Step](testing_first_task.md).  Again, we'll start
with `polaris list` to make sure that works fine and the task still shows
up.  Then, we'll set up the task with `polaris setup` as before.  Next,
we will go to the task's work directory and use `polaris serial`
(on an interactive node) or submit a job script to make sure the task runs both
steps (`init` and `forward`) that we've added so far.

---

← [Back to *Adding Step Outputs*](adding_outputs.md)

→ [Continue to *Adding a Visualization Step*](adding_viz.md)
