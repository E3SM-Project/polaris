(dev-test-cases)=

# Test cases

In many ways, test cases are polaris's fundamental building blocks, since a
user can't set up an individual step of test case (though they can run the
steps one at a time).

A test case can be a module but is usually a python package so it can
incorporate modules for its steps and/or config files, namelists, and streams
files.  The test case must include a class that descends from
{py:class}`polaris.TestCase`.  In addition to a constructor (`__init__()`),
the class will often override the `configure()` and `validate()` methods of
the base class, as described below.

The `run()` method in {py:class}`polaris.TestCase` is deprecated; behaviors
at runtime can instead be handled by individual steps by overriding the
{py:meth}`polaris.Step.constrain_resources()` and
{py:meth}`polaris.Step.runtime_setup()` methods.  Details about these methods
are described further in {ref}`dev-steps`.

(dev-test-case-class)=

## TestCase attributes

The base class {py:class}`polaris.TestCase` has a large number of attributes
that are useful at different stages (init, configuration and run) of the test
case.

Some attributes are available after calling the base class' constructor
`super().__init__()`.  These include:

`self.name`

: the name of the test case

`self.test_group`

: The test group the test case belongs to

`self.component`

: The component the test group belongs to

`self.subdir`

: the subdirectory for the test case

`self.path`

: the path within the base work directory of the test case, made up of
  `component`, `test_group`, and the test case's `subdir`

Other attributes become useful only after steps have been added to the test
case:

`self.steps`

: A dictionary of steps in the test case with step names as keys

`self.steps_to_run`

: A list of the steps to run when {py:func}`polaris.run.serial.run_tests()`
  gets called.  This list includes all steps by default but can be replaced
  with a list of only those tests that should run by default if some steps
  are optional and should be run manually by the user.

Another set of attributes is not useful until `configure()` is called by the
polaris framework:

`self.config`

: Configuration options for this test case, a combination of the defaults
  for the machine, core and configuration

`self.config_filename`

: The local name of the config file that `config` has been written to
  during setup and read from during run

`self.work_dir`

: The test case's work directory, defined during setup as the combination
  of `base_work_dir` and `path`

`self.base_work_dir`

: The base work directory

These can be used to make further alterations to the config options or to add
symlinks files in the test case's work directory.

Finally, one attribute is available only when the
{py:func}`polaris.run.serial.run_tests()` function gets called by the
framework:

`self.logger`

: A logger for output from the test case.  This gets accessed by other
  methods and functions that use the logger to write their output to the log
  file.

You can add other attributes to the child class that keeps track of information
that the test case or its steps will need.  As an example,
{py:class}`polaris.landice.tests.dome.smoke_test.SmokeTest` keeps track of the
mesh type and the velocity solver an attributes:

```python
class SmokeTest(TestCase):
    """
    The default test case for the dome test group simply creates the mesh and
    initial condition, then performs a short forward run on 4 cores.

    Attributes
    ----------
    mesh_type : str
        The resolution or type of mesh of the test case

    velo_solver : {'sia', 'FO'}
        The velocity solver to use for the test case
    """

    def __init__(self, test_group, velo_solver, mesh_type):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.landice.tests.dome.Dome
            The test group that this test case belongs to

        velo_solver : {'sia', 'FO'}
            The velocity solver to use for the test case

        mesh_type : str
            The resolution or type of mesh of the test case
        """
        name = 'smoke_test'
        self.mesh_type = mesh_type
        self.velo_solver = velo_solver
        subdir = '{}/{}_{}'.format(mesh_type, velo_solver.lower(), name)
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)

        self.add_step(
            SetupMesh(test_case=self, mesh_type=mesh_type))

        step = RunModel(test_case=self, ntasks=4, openmp_threads=1,
                        name='run_step', velo_solver=velo_solver,
                        mesh_type=mesh_type)
        if velo_solver == 'sia':
            step.add_model_config_options(
                {'config_run_duration': "'0200-00-00_00:00:00'"})
        self.add_step(step)

        step = Visualize(test_case=self, mesh_type=mesh_type)
        self.add_step(step, run_by_default=False)
```

(dev-test-case-init)=

## constructor

The `__init__()` method must first call the base constructor
`super().__init__()`, passing the name of the test case, the test group it
will belong to, and the subdirectory (if different from the name of the test
case).  Then, it should create an object for each step and add them to itself
using call {py:func}`polaris.TestCase.add_step()`.

It is important that `__init__()` doesn't perform any time-consuming
calculations, download files, or otherwise use significant resources because
objects get constructed (and all constructors get called) quite often for every
single test case and step in polaris: when test cases are listed, set up,
or cleaned up, and also when test suites are set up or cleaned up.

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

As an example, here is the constructor from
{py:class}`polaris.ocean.tests.baroclinic_channel.rpe_test.RpeTest`:

```python
from polaris.testcase import TestCase
from polaris.ocean.tests.baroclinic_channel.initial_state import InitialState
from polaris.ocean.tests.baroclinic_channel.forward import Forward
from polaris.ocean.tests.baroclinic_channel.rpe_test.analysis import Analysis

class RpeTest(TestCase):
    """
    The reference potential energy (RPE) test case for the baroclinic channel
    test group performs a 20-day integration of the model forward in time at
    5 different values of the viscosity at the given resolution.

    Attributes
    ----------
    resolution : str
        The resolution of the test case
    """

    def __init__(self, test_group, resolution):
        """
        Create the test case

        Parameters
        ----------
        test_group : polaris.ocean.tests.baroclinic_channel.BaroclinicChannel
            The test group that this test case belongs to

        resolution : str
            The resolution of the test case
        """
        name = 'rpe_test'
        subdir = f'{resolution}/{name}'
        super().__init__(test_group=test_group, name=name,
                         subdir=subdir)

        nus = [1, 5, 10, 20, 200]

        res_params = {'1km': {'ntasks': 144, 'min_tasks': 36},
                      '4km': {'ntasks': 36, 'min_tasks': 8},
                      '10km': {'ntasks': 8, 'min_tasks': 4}}

        if resolution not in res_params:
            raise ValueError(
                f'Unsupported resolution {resolution}. Supported values are: '
                f'{list(res_params)}')

        params = res_params[resolution]

        self.resolution = resolution

        self.add_step(
            InitialState(test_case=self, resolution=resolution))

        for index, nu in enumerate(nus):
            name = 'rpe_test_{}_nu_{}'.format(index + 1, nu)
            step = Forward(
                test_case=self, name=name, subdir=name,
                ntasks=params['ntasks'], min_tasks=params['min_tasks'],
                resolution=resolution, nu=float(nu))

            step.add_namelist_file(
                'polaris.ocean.tests.baroclinic_channel.rpe_test',
                'namelist.forward')
            step.add_streams_file(
                'polaris.ocean.tests.baroclinic_channel.rpe_test',
                'streams.forward')
            self.add_step(step)

        self.add_step(
            Analysis(test_case=self, resolution=resolution, nus=nus))
```

We have deliberately chosen a fairly complex example to demonstrate how to make
full use of {ref}`dev-code-sharing` in a test case.

The test case imports the classes for its steps --
{py:class}`polaris.ocean.tests.baroclinic_channel.initial_state.InitialState`,
{py:class}`polaris.ocean.tests.baroclinic_channel.forward.Forward`, and
{py:class}`polaris.ocean.tests.baroclinic_channel.rpe_test.analysis.Analysis`
-- so it can create objects for each and add them to itself with
{py:func}`polaris.TestCase.add_step()`.  After this, the {py:class}`dict` of
steps will be available in `self.steps`.

By default, the test case will go into a subdirectory with the same name as the
test case (`rpe_test` in this case).  However, polaris is flexible
about the subdirectory structure and the names of the subdirectories.  This
flexibility was an important requirement in polaris' design.  Each test case 
and step must end up in a unique  directory, so it may be important that the 
name and subdirectory of each test  case or step depends in some way on the 
arguments passed the constructor.  In  the example above, the resolution is an 
argument to the constructor, which is  then saved as an attribute 
(`self.resolution`) and also used to define a unique subdirectory each 
resolution: `1km/rpe_test`, `4km/rpe_test` and `10km/rpe_test`.

The same `Forward` step is included in the test case 5 times with a different
viscosity parameter `nu` for each.  The value of
`nu` is passed to the step's constructor, along with
the unique `name`, `subdir`, and several other parameters:
`resolution`, `ntasks`, and `min_tasks`. In this example, the steps are
given rather clumsy names -- `rpe_test_1_nu_1`, `rpe_test_2_nu_5`, etc. --
but these could be any unique names.

(dev-test-case-configure)=

## configure()

The {py:meth}`polaris.TestCase.configure()` method can be overridden by a
child class to set config options or build them up from defaults stored in
config files within the test case or its test group. The `self.config`
attribute that is modified in this function will be written to a config file
for the test case (see {ref}`config-files`).

If you override this method in a test case, you should assume that the
`<test_case.name>.cfg` file in its package has already been added to the
config options prior to calling `configure()`.  This happens automatically
during test-case setup.

Since many test groups need similar behavior in the `configure()` method for
each test case, it is common to have a shared function (sometimes also called
`configure()`) in the test group, as we discussed in {ref}`dev-test-groups`.

{py:meth}`polaris.ocean.tests.baroclinic_channel.rpe_test.RpeTest.configure()`
simply calls the shared function in its test group,
{py:func}`polaris.ocean.tests.baroclinic_channel.configure()`:

```python
from polaris.ocean.tests import baroclinic_channel


def configure(self):
    """
    Modify the configuration options for this test case.
    """
    baroclinic_channel.configure(self.resolution, self.config)
```

{py:func}`polaris.ocean.tests.baroclinic_channel.configure()` was already
shown in {ref}`dev-test-groups` above.  It sets parameters for the number of
cells in the mesh in the x and y directions and the resolution of those cells.

The `configure()` method can also be used to perform other operations at the
test-case level when a test case is being set up. An example of this would be
creating a symlink to a README file that is shared across the whole test case,
as in {py:meth}`polaris.ocean.tests.global_ocean.files_for_e3sm.FilesForE3SM.configure()`:

```python
from importlib.resources import path

from polaris.ocean.tests.global_ocean.configure import configure_global_ocean
from polaris.io import symlink


def configure(self):
    """
    Modify the configuration options for this test case
    """
    configure_global_ocean(test_case=self, mesh=self.mesh, init=self.init)
    with path('polaris.ocean.tests.global_ocean.files_for_e3sm',
              'README') as target:
        symlink(str(target), '{}/README'.format(self.work_dir))
```

The `configure()` method is not the right place for adding or modifying steps
that belong to a test case.  Steps should be added during init and altered only
in their own `setup()` or `runtime_setup()` methods.

Test cases that don't need to change config options don't need to override
`configure()` at all.

(dev-test-case-validate)=

## validate()

The base class's {py:meth}`polaris.TestCase.validate()` can be overridden to
perform {ref}`dev-validation` of variables in output files from a step and/or
timers from the E3SM component.

In  {py:meth}`polaris.ocean.tests.global_ocean.init.Init.validate()`, we see
examples of validation of variables from output files:

```python
def validate(self):
    """
    Test cases can override this method to perform validation of variables
    and timers
    """
    steps = self.steps_to_run

    variables = ['temperature', 'salinity', 'layerThickness']
    compare_variables(test_case=self, variables=variables,
                      filename1='initial_state/initial_state.nc')

    if self.with_bgc:
        variables = [
            'temperature', 'salinity', 'layerThickness', 'PO4', 'NO3',
            'SiO3', 'NH4', 'Fe', 'O2', 'DIC', 'DIC_ALT_CO2', 'ALK',
            'DOC', 'DON', 'DOFe', 'DOP', 'DOPr', 'DONr', 'zooC',
            'spChl', 'spC', 'spFe', 'spCaCO3', 'diatChl', 'diatC',
            'diatFe', 'diatSi', 'diazChl', 'diazC', 'diazFe',
            'phaeoChl', 'phaeoC', 'phaeoFe', 'DMS', 'DMSP', 'PROT',
            'POLY', 'LIP']
        compare_variables(test_case=self, variables=variables,
                          filename1='initial_state/initial_state.nc')

    if self.mesh.with_ice_shelf_cavities:
        variables = ['ssh', 'landIcePressure']
        compare_variables(test_case=self, variables=variables,
                          filename1='ssh_adjustment/adjusted_init.nc')
```

If you leave the default keyword argument `skip_if_step_not_run=True`,
comparison will be skipped (logging a message) if one or more of the steps
involved in the comparison was not run.
