(dev-config)=

# Config files

The primary documentation for the config parser is in the
[tranche documentation](https://xylar.github.io/tranche/).
Here, we include some specific details relevant to using the
{py:class}`tranche.Tranche` in polaris.

Here, we provide the {py:class}`polaris.config.PolarisConfigParser` that has
almost the same functionality but also ensures that certain relative paths are
converted automatically to absolute paths.  `PolarisConfigParser` also has
attributes for a `filepath` where the config file will be written out and a
list of `symlinks` that will point to `filepath`.  It also has a
{py:meth}`polaris.config.PolarisConfigParser.setup()` method that can be
overridden to add config options (e.g. algorithmically from other config
options) as part of setting up polaris tasks and steps.  These features are
included to accommodate sharing config options across shared steps and/or
multiple tasks.

The {py:meth}`tranche.Tranche.add_from_package()` method can
be used to add the contents of a config file within a package to the config
options. Examples of this can be found in many tasks as well as in the
`polaris.setup` module. Here is a typical example from
{py:class}`polaris.tasks.ocean.inertial_gravity_wave.InertialGravityWave`:

```python
from polaris import Task


class InertialGravityWave(Task):
    def __init__(self, component):
        name = 'inertial_gravity_wave'
        subdir = f'planar/{name}'
        super().__init__(component=component, name=name, subdir=subdir)

        ...

        self.config.add_from_package(
            'polaris.tasks.ocean.inertial_gravity_wave',
            'inertial_gravity_wave.cfg')
```

The first and second arguments are the name of a package containing the config
file and the name of the config file itself, respectively.  You can see that
the file is in the path `polaris/ocean/tasks/baroclinic_channel`
(replacing the `.` in the module name with `/`).  In this case, we know
that the config file should always exist, so we would like the code to raise
an exception (`exception=True`) if the file is not found.  This is the
default behavior.  In some cases, you would like the code to add the config
options if the config file exists and do nothing if it does not.  In this
example from {py:func}`polaris.setup.setup_task()`, there may not be a config
file for the particular machine we're on, and that's fine:

```python
from polaris.config import PolarisConfigParser


def _get_basic_config(config_file, machine, component_path, component):
    config = PolarisConfigParser()
    if machine is not None:
        config.add_from_package('mache.machines', f'{machine}.cfg',
                                exception=False)
```
If there isn't a config file for this machine, nothing will happen.

The `MpasConfigParser` class also includes methods for adding a user
config file and other config files by file name, but these are largely intended
for use by the framework rather than individual tasks.

Other methods for the `MpasConfigParser` are similar to those for
{py:class}`configparser.ConfigParser`.  In addition to `get()`,
`getinteger()`, `getfloat()` and `getboolean()` methods, this class
implements {py:meth}`tranche.Tranche.getlist()`, which
can be used to parse a config value separated by spaces and/or commas into
a list of strings, floats, integers, booleans, etc. Other useful methods
are {py:meth}`tranche.Tranche.getexpression()`, which can
be used to get python dictionaries, lists, and tuples, and
{py:meth}`tranche.Tranche.getnumpy()`, which also suppports a small set
of functions (`range()`, {py:meth}`numpy.linspace()`,
{py:meth}`numpy.arange()`, and {py:meth}`numpy.array()`)

## Shared config files

Often, it makes sense for many tasks and steps to share the same config
options.  The default behavior is for a task and its "owned" steps to share
a config file in the task's work directory called `{task.name}.cfg` and
symlinks with that same name in each step's work directory.  The default for
a shared step is to have its own `{step.name}.cfg` in its work directory.

Developers can create shared config parsers that define the location of the
shared config file and add them to tasks and steps using
{py:meth}`polaris.Task.set_shared_config()` and
{py:meth}`polaris.Step.set_shared_config()`.  The location of the shared
config file should be intuitive to users but local symlinks will also make
it easy to modify the shared config options from within any of the tasks and
steps that use them.

As an example, the baroclinic channel tasks share a single
`baroclinic_channel.cfg` config file for each resolution that resides in the
resolution's work directory:

```python
from polaris.config import PolarisConfigParser
from polaris.resolution import resolution_to_string
from polaris.tasks.ocean.baroclinic_channel.default import Default
from polaris.tasks.ocean.baroclinic_channel.init import Init
from polaris.tasks.ocean.baroclinic_channel.rpe import Rpe


def add_baroclinic_channel_tasks(component):
    for resolution in [10., 4., 1.]:
        resdir = resolution_to_string(resolution)
        resdir = f'planar/baroclinic_channel/{resdir}'

        config_filename = 'baroclinic_channel.cfg'
        config = PolarisConfigParser(filepath=f'{resdir}/{config_filename}')
        config.add_from_package('polaris.tasks.ocean.baroclinic_channel',
                                'baroclinic_channel.cfg')

        init = Init(component=component, resolution=resolution, indir=resdir)
        init.set_shared_config(config, link=config_filename)

        default = Default(component=component, resolution=resolution,
                          indir=resdir, init=init)
        default.set_shared_config(config, link=config_filename)
        component.add_task(default)

        ...

        component.add_task(Rpe(component=component, resolution=resolution,
                               indir=resdir, init=init, config=config))
```

For most tasks and steps, it is convenient to call `set_shared_config()`
after constructing the step or task and before adding it to the component.
In the example of the `Rpe` task here, we need the shared config in the
constructor so it has to be passed in.  We call `self.set_shared_config()`
in the constructor, and then use config options to determine the steps to be
added as follows:

```python
from polaris import Task
from polaris.tasks.ocean.baroclinic_channel.forward import Forward
from polaris.tasks.ocean.baroclinic_channel.rpe.analysis import Analysis


class Rpe(Task):
    def __init__(self, component, resolution, indir, init, config):
        super().__init__(component=component, name='rpe', indir=indir)
        self.resolution = resolution

        # this needs to be added before we can use the config options it
        # brings in to set up the steps
        self.set_shared_config(config, link='baroclinic_channel.cfg')
        self.add_step(init, symlink='init')
        self._add_rpe_and_analysis_steps()

    def _add_rpe_and_analysis_steps(self):
        """ Add the steps in the test case either at init or set-up """
        config = self.config
        component = self.component
        resolution = self.resolution

        nus = config.getlist('baroclinic_channel_rpe', 'viscosities',
                             dtype=float)
        for nu in nus:
            name = f'nu_{nu:g}'
            step = Forward(
                component=component, name=name, indir=self.subdir,
                ntasks=None, min_tasks=None, openmp_threads=1,
                resolution=resolution, nu=nu)

            step.add_yaml_file(
                'polaris.tasks.ocean.baroclinic_channel.rpe',
                'forward.yaml')
            self.add_step(step)

        self.add_step(
            Analysis(component=component, resolution=resolution, nus=nus,
                     indir=self.subdir))
```

(dev-component-config)=

## Where a task's or step's config options come from

Every config parser belongs to exactly one component, and gets that
component's config options and nothing else from any other component.

During setup, polaris builds a config parser for each component **in use** --
the component that owns the tasks being set up, the components that own steps
in those tasks and the components of any dependencies of those steps
({py:func}`polaris.component_graph.get_components_in_use()`).  A component's
config parser is made up of:

1. the config options for the machine and the command line
   (`polaris/default.cfg`, the machine config files, a config file passed with
   `-f` and options like `-p`)
2. the component's own config file, `polaris/<component>/<component>.cfg`
3. whatever the component's
   {py:meth}`polaris.Component.configure()` method adds, such as the ocean's
   `mpas_ocean.cfg` or `omega.cfg`

That config parser is then prepended to the config parser of each task and
shared step the component owns, so a task's or step's own config files always
take precedence over the component's.

This means that a shared step gets the config options of **its own**
component, not those of the component that owns the task that includes it.  A
shared ocean step gets the ocean's config options whether it was set up as
part of an ocean task or as part of an `e3sm/init` task, so a step behaves the
same however it was reached.  Two rules follow, and setup raises if either is
broken:

- a step from a component other than its task's must be a shared step with a
  shared config file, since a step without one would get its config options
  from the task, and so from the wrong component
- a shared config file must be used by steps from only one component, since it
  is that component's config options it will be given

The suite's config file (`polaris/suites/<component>/<suite>.cfg`) is not part
of any of this.  It applies only to the suite's job script, so that a task or
step behaves the same whether or not it was set up as part of a suite.

## Comments in config files

One of the main advantages of {py:class}`tranche.Tranche`
over {py:class}`configparser.ConfigParser` is that it keeps track of comments
that are associated with config sections and options.

Comments must begin with the `#` character. They must be placed *before* the
config section or option in question (preferably without blank lines between).
The comments can be any number of lines long.
