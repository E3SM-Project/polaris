(dev-config)=

# Config files

The primary documentation for the config parser is in
[MPAS-Tools config parser](http://mpas-dev.github.io/MPAS-Tools/stable/config.html).
Here, we include some specific details relevant to using the
{py:class}`mpas_tools.config.MpasConfigParser` in polaris.

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

The {py:meth}`mpas_tools.config.MpasConfigParser.add_from_package()` method can
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
implements {py:meth}`mpas_tools.config.MpasConfigParser.getlist()`, which
can be used to parse a config value separated by spaces and/or commas into
a list of strings, floats, integers, booleans, etc. Another useful method
is {py:meth}`mpas_tools.config.MpasConfigParser.getexpression()`, which can
be used to get python dictionaries, lists and tuples as well as a small set
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

## Comments in config files

One of the main advantages of {py:class}`mpas_tools.config.MpasConfigParser`
over {py:class}`configparser.ConfigParser` is that it keeps track of comments
that are associated with config sections and options.

See [comments in config files](http://mpas-dev.github.io/MPAS-Tools/stable/config.html#config_comments)
in MPAS-Tools for more details.
