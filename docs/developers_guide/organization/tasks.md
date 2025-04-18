(dev-tasks)=

# Tasks

In many ways, tasks are polaris's fundamental building blocks, since a
user can't set up an individual step of task (though they can run the
steps one at a time).

A task can be a module but is usually a python package so it can
incorporate modules for its steps and/or config files, namelists, streams, and
YAML files.  The task must include a class that descends from
{py:class}`polaris.Task`.  In addition to a constructor (`__init__()`),
the class will sometimes override the `configure()` method of the base class,
as described below.

(dev-task-class)=

## Task attributes

The base class {py:class}`polaris.Task` has a large number of attributes
that are useful at different stages (init, configuration and run) of the task.

Some attributes are available after calling the base class' constructor
`super().__init__()`.  These include:

`self.name`

: the name of the task

`self.component`

: The component the task belongs to

`self.subdir`

: the subdirectory for the task within the component's work directory

`self.path`

: the path within the base work directory of the task, made up of
  the name of the component and the task's `subdir`

`self.config`

: Configuration options for this task, possibly shared with other tasks
  and steps

`self.config_filename`

: The filename or symlink within the task where `config` is written to during
  setup and read from during run

Other attributes become useful only after steps have been added to the task:

`self.steps`

: A dictionary of steps in the task with step names as keys

`self.step_symlinks`

: A dictionary of relative paths within the step for symlinks to shared steps
  with step names as keys

`self.steps_to_run`

: A list of the steps to run when {py:func}`polaris.run.serial.run_tasks()`
  gets called.  This list includes all steps by default but can be replaced
  with a list of only those steps that should run by default if some steps
  are optional and should be run manually by the user.

Another set of attributes is not useful until `configure()` is called by the
polaris framework:

`self.work_dir`

: The task's work directory, defined during setup as the combination
  of `base_work_dir` and `path`

`self.base_work_dir`

: The base work directory

These can be used to make further alterations to the config options or to add
symlinks files in the task's work directory.

Finally, several attributes are available only when the
{py:func}`polaris.run.serial.run_tasks()` function gets called by the
framework:

`self.logger`

: A logger for output from the task.  This gets accessed by other
  methods and functions that use the logger to write their output to the log
  file.

`self.stdout_logger`

: A logger for output from the task that goes to stdout regardless of whether
  `logger` is a log file or stdout

`self.log_filename`

: At run time, the name of a log file where output/errors from the task are
  being logged, or ``None`` if output is to stdout/stderr

`self.new_step_log_file`

: Used by the framework to know whether to create a new log file for each step
  or log output to a common log file for the whole task

You can add other attributes to the child class that keeps track of information
that the task or its steps will need.  As an example,
{py:class}`polaris.landice.tasks.dome.smoke_test.SmokeTest` keeps track of the
mesh type and the velocity solver an attributes:

```python
from polaris import Task


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
will belong to, and the subdirectory within the component.  (The default is
the name of the task, which is typically not what you want.) Then, it should
create an object for each step (or make use of existing objects for shared
steps) and add them to itself using call {py:func}`polaris.Task.add_step()`.

It is important that `__init__()` doesn't perform any time-consuming
calculations, download files, or otherwise use significant resources because
objects get constructed (and all constructors get called) quite often for every
single task and step in polaris: when tasks are listed, set up,
or cleaned up, and also when suites are set up or cleaned up.

However, it is fine to call the following methods on a step during init because
these methods only keep track of a "recipe" for downloading files or
constructing namelist and streams files, they don't actually do the work
associated with these steps until the point where the step is being set up in

- {py:meth}`mpas_tools.config.MpasConfigParser.add_from_package()`
- {py:meth}`polaris.Step.add_input_file()`
- {py:meth}`polaris.Step.add_output_file()`
- {py:meth}`polaris.ModelStep.add_model_config_options()`
- {py:meth}`polaris.ModelStep.add_yaml_file()`
- {py:meth}`polaris.ModelStep.add_namelist_file()`
- {py:meth}`polaris.ModelStep.add_streams_file()`

We will demonstrate with a fairly complex example,
{py:class}`polaris.tasks.ocean.cosine_bell.CosineBell`,
to demonstrate how to make full use of {ref}`dev-code-sharing` in a task:

```python
from typing import Dict

from polaris import Step, Task
from polaris.mesh.add_step import add_uniform_spherical_base_mesh_step
from polaris.tasks.ocean.cosine_bell.analysis import Analysis
from polaris.tasks.ocean.cosine_bell.forward import Forward
from polaris.tasks.ocean.cosine_bell.init import Init
from polaris.tasks.ocean.cosine_bell.viz import Viz, VizMap


class CosineBell(Task):
    def __init__(self, component, config, icosahedral, include_viz):
        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        subdir = f'spherical/{prefix}/cosine_bell'
        name = f'{prefix}_cosine_bell'
        if include_viz:
            subdir = f'{subdir}/with_viz'
            name = f'{name}_with_viz'
            link = 'cosine_bell.cfg'
        else:
            # config options live in the task already so no need for a symlink
            link = None
        super().__init__(component=component, name=name, subdir=subdir)
        self.resolutions = list()
        self.icosahedral = icosahedral
        self.include_viz = include_viz

        self.set_shared_config(config, link=link)

        self._setup_steps()

    def _setup_steps(self):
        """ setup steps given resolutions """
        icosahedral = self.icosahedral
        config = self.config
        config_filename = self.config_filename

        if icosahedral:
            prefix = 'icos'
        else:
            prefix = 'qu'

        resolutions = config.getlist('spherical_convergence',
                                     f'{prefix}_resolutions', dtype=float)

        if self.resolutions == resolutions:
            return

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        self.resolutions = resolutions

        component = self.component

        analysis_dependencies: Dict[str, Dict[str, Step]] = (
            dict(mesh=dict(), init=dict(), forward=dict()))
        for resolution in resolutions:
            base_mesh_step, mesh_name = add_uniform_spherical_base_mesh_step(
                resolution, icosahedral)
            self.add_step(base_mesh_step, symlink=f'base_mesh/{mesh_name}')
            analysis_dependencies['mesh'][resolution] = base_mesh_step

            cos_bell_dir = f'spherical/{prefix}/cosine_bell'

            name = f'{prefix}_init_{mesh_name}'
            subdir = f'{cos_bell_dir}/init/{mesh_name}'
            if self.include_viz:
                symlink = f'init/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                init_step = component.steps[subdir]
            else:
                init_step = Init(component=component, name=name, subdir=subdir,
                                 base_mesh=base_mesh_step)
                init_step.set_shared_config(config, link=config_filename)
            self.add_step(init_step, symlink=symlink)
            analysis_dependencies['init'][resolution] = init_step

            name = f'{prefix}_forward_{mesh_name}'
            subdir = f'{cos_bell_dir}/forward/{mesh_name}'
            if self.include_viz:
                symlink = f'forward/{mesh_name}'
            else:
                symlink = None
            if subdir in component.steps:
                forward_step = component.steps[subdir]
            else:
                forward_step = Forward(component=component, name=name,
                                       subdir=subdir, resolution=resolution,
                                       base_mesh=base_mesh_step,
                                       init=init_step)
                forward_step.set_shared_config(config, link=config_filename)
            self.add_step(forward_step, symlink=symlink)
            analysis_dependencies['forward'][resolution] = forward_step

            if self.include_viz:
                with_viz_dir = f'spherical/{prefix}/cosine_bell/with_viz'

                name = f'{prefix}_map_{mesh_name}'
                subdir = f'{with_viz_dir}/map/{mesh_name}'
                viz_map = VizMap(component=component, name=name,
                                 subdir=subdir, base_mesh=base_mesh_step,
                                 mesh_name=mesh_name)
                viz_map.set_shared_config(config, link=config_filename)
                self.add_step(viz_map)

                name = f'{prefix}_viz_{mesh_name}'
                subdir = f'{with_viz_dir}/viz/{mesh_name}'
                step = Viz(component=component, name=name,
                           subdir=subdir, base_mesh=base_mesh_step,
                           init=init_step, forward=forward_step,
                           viz_map=viz_map, mesh_name=mesh_name)
                step.set_shared_config(config, link=config_filename)
                self.add_step(step)

        subdir = f'spherical/{prefix}/cosine_bell/analysis'
        if self.include_viz:
            symlink = 'analysis'
        else:
            symlink = None
        if subdir in component.steps:
            step = component.steps[subdir]
        else:
            step = Analysis(component=component, resolutions=resolutions,
                            icosahedral=icosahedral, subdir=subdir,
                            dependencies=analysis_dependencies)
            step.set_shared_config(config, link=config_filename)
        self.add_step(step, symlink=symlink)
```

By default, the task will go into a subdirectory within the component with the
same name as the task (`cosine_bell` in this case).  However, this is rarely
desirable and polaris is flexible about the subdirectory structure and the
names of the subdirectories.  This flexibility was an important requirement in
polaris' design.  Each task and step must end up in a unique directory, so it
is nearly always important that the name and subdirectory of each task or
step depends in some way on the arguments passed the constructor.  In the
example above, whether the mesh is icosahedral or quasi-uniform is an argument
(`icosahedral`) to the constructor, which is then saved as an attribute
(`self.icosahedral`) and also used to define a unique subdirectory:
`global_convergence/icos/cosine_bell` or `global_convergence/qu/cosine_bell`.

The task imports a function --
{py:func}`polaris.mesh.add_step.add_uniform_spherical_base_mesh_step()` --
and classes --
{py:class}`polaris.mesh.spherical.IcosahedralMeshStep`,
{py:class}`polaris.mesh.spherical.QuasiUniformSphericalMeshStep`,
{py:class}`polaris.tasks.ocean.cosine_bell.init.Init`,
{py:class}`polaris.tasks.ocean.cosine_bell.forward.Forward`,
{py:class}`polaris.tasks.ocean.cosine_bell.analysis.Analysis`,
{py:class}`polaris.tasks.ocean.cosine_bell.viz.VizMap`, and
{py:class}`polaris.tasks.ocean.cosine_bell.viz.Viz`
-- for creating objects for each step.  The step objects are added to itself
and the {py:class}`polaris.tasks.ocean.Ocean` component with calls to
{py:func}`polaris.Task.add_step()`.  After this, the {py:class}`dict` of
steps will be available in `self.steps`, and a list of steps to run by default
will be in `self.steps_to_run`.  This example reads resolutions from a config
option and uses them to make `base_mesh`, `init`, `forward`, `viz_map` and
`viz` steps for each resolution, and then a final `analysis` step to compare
all resolutions.

This example takes advantage of shared steps.  The `base_mesh` step resides
outside of the `cosine_bell` work directory so it could be used by any task
that needs a quasi-uniform (`qu`) or subdivided icosahedral (`icos`) mesh of
the given resolution.  A path within the task for a symlink is provided using
the `symlink` argument to make it easier for users and developers to find the
shared step.  Here's what the work directory structure will look like for the
`ocean/spherical/icos/cosine_bell` task:

 * ocean
   * spherical
     * icos
       * base_mesh
         * 60km
         * 120km
         * 240km
         * 480km
       * cosine_bell
         * base_mesh
           * **60km**
           * **120km**
           * **240km**
           * **480km**
         * init
           * 60km
           * 120km
           * 240km
           * 480km
         * forward
           * 60km
           * 120km
           * 240km
           * 480km
         * analysis

The directories in bold are symlinks.

Similarly, the `init` and `forward` steps for each resolution are shared
between the `cosine_bell` and the `cosine_bell/with_viz` tasks.  Since the
steps reside in `cosine_bell`, we don't create symlinks to the shared steps for
that version of the task, but we do for `cosine_bell/with_viz`, since the
shared steps are outside its work directory.  Here is what the
`ocean/spherical/icos/cosine_bell/with_viz` task looks like, where symlinks to
the shared steps (which always reside lower in the tree, closer to the
component directory) are again in bold:

 * ocean
   * spherical
     * icos
       * base_mesh
         * 60km
         * 120km
         * 240km
         * 480km
       * cosine_bell
         * init
           * 60km
           * 120km
           * 240km
           * 480km
         * forward
           * 60km
           * 120km
           * 240km
           * 480km
         * analysis
         * with_viz
           * base_mesh
             * **60km**
             * **120km**
             * **240km**
             * **480km**
           * init
             * **60km**
             * **120km**
             * **240km**
             * **480km**
           * forward
             * **60km**
             * **120km**
             * **240km**
             * **480km**
           * map
             * 60km
             * 120km
             * 240km
             * 480km
           * viz
             * 60km
             * 120km
             * 240km
             * 480km
           * **analysis**

(dev-task-configure)=

## configure()

The {py:meth}`polaris.Task.configure()` method is called before a task gets
set up in its work directory.  As part of setup, a user can pass their own
config options to `polaris setup` that override those from polaris packages.

The main usage of `configure()` in Polaris tasks is to re-add steps to the
task that depend on config options that a user may have changed. In the cosine
bell example above, the `configure()` method simply calls the `_setup_steps()`
method again so that steps are recreated if the requested resolutions have
change:

```python
from polaris import Task


class CosineBell(Task):
  def configure(self):
        """
        Set config options for the test case
        """
        super().configure()

        # set up the steps again in case a user has provided new resolutions
        self._setup_steps()
```

The `configure()` method is not the right place for adding steps for the first
time.  Steps should be added during init if possible and, if their names and
locations rely on config options, they should be removed and re-added in
`configure()`, as in the example above. Typically, this is because there is
a step for each of a list of resolutions (or another parameter) from a config
option.  If possible, alter the steps only in their own
{py:meth}`polaris.Step.setup()` or {py:meth}`polaris.Step.runtime_setup()`
methods, not in `configure()`.

You can also add config options from package files in `configure()`:

```python
from polaris import Task

class InertialGravityWave(Task):
    def configure(self):
        """
        Add the config file common to inertial gravity wave tests
        """
        self.config.add_from_package(
            'polaris.tasks.ocean.inertial_gravity_wave',
            'inertial_gravity_wave.cfg')
```

However, this is more typically done in the constructor if config options are
only being used by this task and external to the task if config options are
shared across multiple tasks and/or shared steps. If many tasks need the same
config options, you should use a shared `config` outside of the task, and add
it to the task using {py:meth}`polaris.Task.set_shared_config()`.

A `configure()` method can also be used to perform other operations at the
task level when a task is being set up. An example of this would be
creating a symlink to a README file that is shared across the whole task:

```python
from polaris.io import imp_res, symlink


def configure(self):
    """
    Modify the configuration options for this task
    """
    package = 'polaris.ocean.tests.global_ocean.files_for_e3sm'
    target = imp_res.files(package).joinpath('README')
    symlink(str(target), f'{self.work_dir}/README')
```
