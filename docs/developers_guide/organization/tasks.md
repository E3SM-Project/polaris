(dev-tasks)=

# Tasks

In many ways, tasks are polaris's fundamental building blocks, since a
user can't set up an individual step of task (though they can run the
steps one at a time).

A task can be a module but is usually a python package so it can
incorporate modules for its steps and/or config files, namelists, and streams
files.  The task must include a class that descends from
{py:class}`polaris.Task`.  In addition to a constructor (`__init__()`),
the class will often override the `configure()` method of the base class, as 
described below.

(dev-task-class)=

## Task attributes

The base class {py:class}`polaris.Task` has a large number of attributes
that are useful at different stages (init, configuration and run) of the test
case.

Some attributes are available after calling the base class' constructor
`super().__init__()`.  These include:

`self.name`

: the name of the task

`self.component`

: The component the task belongs to

`self.subdir`

: the subdirectory for the task

`self.path`

: the path within the base work directory of the task, made up of
  `component`, `test_group`, and the task's `subdir`

Other attributes become useful only after steps have been added to the test
case:

`self.steps`

: A dictionary of steps in the task with step names as keys

`self.steps_to_run`

: A list of the steps to run when {py:func}`polaris.run.serial.run_tasks()`
  gets called.  This list includes all steps by default but can be replaced
  with a list of only those steps that should run by default if some steps
  are optional and should be run manually by the user.

Another set of attributes is not useful until `configure()` is called by the
polaris framework:

`self.config`

: Configuration options for this task, a combination of the defaults
  for the machine, core and configuration

`self.config_filename`

: The local name of the config file that `config` has been written to
  during setup and read from during run

`self.work_dir`

: The task's work directory, defined during setup as the combination
  of `base_work_dir` and `path`

`self.base_work_dir`

: The base work directory

These can be used to make further alterations to the config options or to add
symlinks files in the task's work directory.

Finally, one attribute is available only when the
{py:func}`polaris.run.serial.run_tasks()` function gets called by the
framework:

`self.logger`

: A logger for output from the task.  This gets accessed by other
  methods and functions that use the logger to write their output to the log
  file.

You can add other attributes to the child class that keeps track of information
that the task or its steps will need.  As an example,
{py:class}`polaris.landice.tasks.dome.smoke_test.SmokeTest` keeps track of the
mesh type and the velocity solver an attributes:

```python
class SmokeTest(Task):
    """
    The default dome task creates the mesh and initial condition, then performs
    a short forward run on 4 cores.

    Attributes
    ----------
    mesh_type : str
        The resolution or type of mesh of the task

    velo_solver : {'sia', 'FO'}
        The velocity solver to use for the task
    """

    def __init__(self, component, velo_solver, mesh_type):
        """
        Create the task

        Parameters
        ----------
        component : polaris.landice.Landice
            The land-ice component that this task belongs to

        velo_solver : {'sia', 'FO'}
            The velocity solver to use for the task

        mesh_type : str
            The resolution or type of mesh of the task
        """
        name = 'smoke_test'
        self.mesh_type = mesh_type
        self.velo_solver = velo_solver
        subdir = '{}/{}_{}'.format(mesh_type, velo_solver.lower(), name)
        super().__init__(component=component, name=name,
                         subdir=subdir)

        self.add_step(
            SetupMesh(task=self, mesh_type=mesh_type))

        step = RunModel(task=self, ntasks=4, openmp_threads=1,
                        name='run_step', velo_solver=velo_solver,
                        mesh_type=mesh_type)
        if velo_solver == 'sia':
            step.add_model_config_options(
                {'config_run_duration': "'0200-00-00_00:00:00'"})
        self.add_step(step)

        step = Visualize(task=self, mesh_type=mesh_type)
        self.add_step(step, run_by_default=False)
```

(dev-task-init)=

## constructor

The `__init__()` method must first call the base constructor
`super().__init__()`, passing the name of the task, the component it
will belong to, and the subdirectory (if different from the name of the test
case).  Then, it should create an object for each step and add them to itself
using call {py:func}`polaris.Task.add_step()`.

It is important that `__init__()` doesn't perform any time-consuming
calculations, download files, or otherwise use significant resources because
objects get constructed (and all constructors get called) quite often for every
single task and step in polaris: when tasks are listed, set up,
or cleaned up, and also when suites are set up or cleaned up.

However, it is fine to call the following methods on a step during init because
these methods only keep track of a "recipe" for downloading files or
constructing namelist and streams files, they don't actually do the work
associated with these steps until the point where the step is being set up in

- {py:meth}`polaris.Step.add_input_file()`
- {py:meth}`polaris.Step.add_output_file()`
- {py:meth}`polaris.ModelStep.add_model_config_options()`
- {py:meth}`polaris.ModelStep.add_yaml_file()`
- {py:meth}`polaris.ModelStep.add_namelist_file()`
- {py:meth}`polaris.ModelStep.add_streams_file()`

We will demonstrate with a fairly complex example,
{py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.CosineBell`,
to demonstrate how to make full use of {ref}`dev-code-sharing` in a task:

```python
from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.mesh.spherical import (
    IcosahedralMeshStep,
    QuasiUniformSphericalMeshStep,
)
from polaris.ocean.tasks.global_convergence.cosine_bell.analysis import (
    Analysis,
)
from polaris.ocean.tasks.global_convergence.cosine_bell.forward import Forward
from polaris.ocean.tasks.global_convergence.cosine_bell.init import Init
from polaris.ocean.tasks.global_convergence.cosine_bell.viz import Viz, VizMap


class CosineBell(Task):
    def __init__(self, component, icosahedral, include_viz):
        if icosahedral:
            subdir = 'global_convergence/icos/cosine_bell'
        else:
            subdir = 'global_convergence/qu/cosine_bell'
        if include_viz:
            subdir = f'{subdir}_with_viz'
        super().__init__(component=component, name='cosine_bell',
                         subdir=subdir)
        self.resolutions = list()
        self.icosahedral = icosahedral
        self.include_viz = include_viz

        # add the steps with default resolutions so they can be listed
        config = PolarisConfigParser()
        package = 'polaris.ocean.tasks.global_convergence.cosine_bell'
        config.add_from_package(package, 'cosine_bell.cfg')
        self._setup_steps(config)

    def _setup_steps(self, config):
        """ setup steps given resolutions """
        if self.icosahedral:
            default_resolutions = '60, 120, 240, 480'
        else:
            default_resolutions = '60, 90, 120, 150, 180, 210, 240'

        # set the default values that a user may change before setup
        config.set('cosine_bell', 'resolutions', default_resolutions,
                   comment='a list of resolutions (km) to test')

        # get the resolutions back, perhaps with values set in the user's
        # config file, which takes priority over what we just set above
        resolutions = config.getlist('cosine_bell', 'resolutions', dtype=int)

        if self.resolutions == resolutions:
            return

        # start fresh with no steps
        self.steps = dict()
        self.steps_to_run = list()

        self.resolutions = resolutions

        for resolution in resolutions:
            if self.icosahedral:
                mesh_name = f'Icos{resolution}'
            else:
                mesh_name = f'QU{resolution}'

            name = f'{mesh_name}_mesh'
            subdir = f'{mesh_name}/mesh'
            if self.icosahedral:
                self.add_step(IcosahedralMeshStep(
                    task=self, name=name, subdir=subdir,
                    cell_width=resolution))
            else:
                self.add_step(QuasiUniformSphericalMeshStep(
                    task=self, name=name, subdir=subdir,
                    cell_width=resolution))

            self.add_step(Init(task=self, mesh_name=mesh_name))

            self.add_step(Forward(task=self, resolution=resolution,
                                  mesh_name=mesh_name))

            if self.include_viz:
                name = f'{mesh_name}_map'
                subdir = f'{mesh_name}/map'
                viz_map = VizMap(task=self, name=name, subdir=subdir,
                                 mesh_name=mesh_name)
                self.add_step(viz_map)

                name = f'{mesh_name}_viz'
                subdir = f'{mesh_name}/viz'
                self.add_step(Viz(task=self, name=name, subdir=subdir,
                                  viz_map=viz_map, mesh_name=mesh_name))

        self.add_step(Analysis(task=self, resolutions=resolutions,
                               icosahedral=self.icosahedral))

```

By default, the task will go into a subdirectory within the component with the
same name as the task (`cosine_bell` in this case).  However, this is rarely 
desirable and polaris is flexible about the subdirectory structure and the 
names of the subdirectories.  This flexibility was an important requirement in 
polaris' design.  Each task and step must end up in a unique  directory, so it 
is nearly always important that the name and subdirectory of each test case or 
step depends in some way on the arguments passed the constructor.  In the 
example above, whether the mesh is icosahedral or quasi-uniform is an argument
(`icosahedral`) to the constructor, which is then saved as an attribute 
(`self.icosahedral`) and also used to define a unique subdirectory: 
`global_convergence/icos/cosine_bell` or `global_convergence/qu/cosine_bell`.

The task imports classes for each step --
{py:class}`polaris.mesh.spherical.IcosahedralMeshStep`,
{py:class}`polaris.mesh.spherical.QuasiUniformSphericalMeshStep`,
{py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.init.Init`,
{py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.forward.Forward`,
{py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.rpe.analysis.Analysis`,
{py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.viz.VizMap`, and
{py:class}`polaris.ocean.tasks.global_convergence.cosine_bell.viz.Viz`
-- so it can create objects for each and add them to itself with
{py:func}`polaris.Task.add_step()`.  After this, the {py:class}`dict` of
steps will be available in `self.steps`, and a list of steps to run by default
will be in `self.steps_to_run`.  This example reads resolutions form a config
option and uses them to make `mesh`, `init`, `forward`, `viz_map` and `viz`
steps for each resolution, and then a final `analysis` step to compare all
resolutions.

(dev-task-configure)=

## configure()

The {py:meth}`polaris.Task.configure()` method can be overridden by a
child class to set config options or build them up from defaults stored in
config files within the task or its shared framework. The `self.config`
attribute that is modified in this function will be written to a config file
for the task (see {ref}`config-files`).

If you override this method in a task, you should assume that the
`<task.name>.cfg` file in its package has already been added to the
config options prior to calling `configure()`.  This happens automatically
during task setup.

Since many tasks may need similar behavior in their `configure()` methods, it 
is common to have either a parent class that defines the `configure()` method,
as we discussed in {ref}`dev-categories-of-tasks`, or all tasks or a shared 
function (sometimes also called `configure()`) in the shared framework.

As an example, {py:meth}`polaris.ocean.tasks.baroclinic_channel.rpe.Rpe.configure()`
first calls the parent class' version of the method, 
{py:meth}`polaris.ocean.tasks.baroclinic_channel.BaroclinicChannelTestCase.configure()`:

```python
  def configure(self):
      """
      Modify the configuration options for this test case.
      """
      super().configure()
      self._add_steps(config=self.config)
```

The parent class `BaroclinicChannelTestCase` is shown in 
{ref}`dev-categories-of-tasks`.

A `configure()` method can also be used to perform other operations at the
task level when a task is being set up. An example of this would be
creating a symlink to a README file that is shared across the whole task,
as in {py:meth}`polaris.ocean.tasks.global_ocean.files_for_e3sm.FilesForE3SM.configure()`:

```python
from importlib.resources import path

from polaris.ocean.tasks.global_ocean.configure import configure_global_ocean
from polaris.io import symlink


def configure(self):
    """
    Modify the configuration options for this task
    """
    configure_global_ocean(task=self, mesh=self.mesh, init=self.init)
    with path('polaris.ocean.tasks.global_ocean.files_for_e3sm',
              'README') as target:
        symlink(str(target), '{}/README'.format(self.work_dir))
```

The `configure()` method is not the right place for adding or modifying steps
that belong to a task.  Steps should be added during init and altered only
in their own `setup()` or `runtime_setup()` methods.

Tasks that don't need to change config options don't need to override
`configure()` at all.
