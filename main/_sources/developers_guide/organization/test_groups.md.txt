(dev-test-groups)=

# Test Groups

Test groups are the next level of test-case organization below
{ref}`dev-components`.  Typically, the test cases within a test group are
in some way conceptually linked, serving a similar purpose or being variants on
one another. Often, they have a common topography and initial condition,
perhaps with different mesh resolutions, parameters, or both.  It is common for
a test group to include "framework" modules that are shared between its test
cases and steps (but not with other test groups).  Each component will
typically include a mix of "idealized" test groups (e.g.
{ref}`dev-ocean-baroclinic-channel` or {ref}`dev-landice-dome`) and "realistic"
domains (e.g. {ref}`dev-landice-greenland` and {ref}`dev-ocean-global-ocean`).

Each test group is a python package within the core's `tests` package.
While it is not required, a test group will typically include a config file,
named `<test_group>.cfg`, with a set of default config options that are
the starting point for all its test cases.  As an example, here is the config
file for the `dome` test group in the `landice` core:

```cfg
# config options for dome test cases
[dome]

# sizes (in cells) for the 2000m uniform mesh
nx = 30
ny = 34

# resolution (in m) for the 2000m uniform mesh
dc = 2000.0

# number of levels in the mesh
levels = 10

# the dome type ('halfar' or 'cism')
dome_type = halfar

# Whether to center the dome in the center of the cell that is closest to the
# center of the domain
put_origin_on_a_cell = True

# whether to add a small shelf to the test
shelf = False

# whether to add hydrology to the initial condition
hydro = False

# config options related to visualization for dome test cases
[dome_viz]

# which time index to visualize
time_slice = 0

# whether to save image files
save_images = True

# whether to hide figures (typically when save_images = True)
hide_figs = True
```

Some test group options will provide defaults for config options that are
shared across the core (as is the case for the `[vertical_grid]` config
section in the ocean core).  But most config options for a test group will
typically go into a section with the same name as the test group, as in the
example above.  Config options that are specific to a particular step might
go into a section with another name, like the `[dome_viz]` section above.

The `__init__.py` file for the test group must define a class for the
test group that descends from {py:class}`polaris.TestGroup`. The constructor
of that class (`__init__()`) first calls the base class' constructor with the
parent {py:class}`polaris.Component` object and the name of the test group.
Then, it constructs objects for each test case in the group and adds them to
itself by calling {py:meth}`polaris.TestGroup.add_test_case()`.  Each test case
gets passed the `self` object as its test group, allowing the test case to
determine both which component and which test group it belongs to. As an
example, the {py:class}`polaris.landice.tests.dome.Dome` class looks like this:

```python
from polaris import TestGroup
from polaris.landice.tests.dome.smoke_test import SmokeTest
from polaris.landice.tests.dome.decomposition_test import DecompositionTest
from polaris.landice.tests.dome.restart_test import RestartTest


class Dome(TestGroup):
    """
    A test group for dome test cases
    """
    def __init__(self, component):
        """
        component : polaris.landice.Landice
            the component that this test group belongs to
        """
        super().__init__(component=component, name='dome')

        for mesh_type in ['2000m', 'variable_resolution']:
            self.add_test_case(
                SmokeTest(test_group=self, mesh_type=mesh_type))
            self.add_test_case(
                DecompositionTest(test_group=self, mesh_type=mesh_type))
            self.add_test_case(
                RestartTest(test_group=self, mesh_type=mesh_type))
```

As in this example, it may be useful for a test group to make several
versions of a test case by passing different parameters.  In the example, we
create versions of `SmokeTest`, `DecompositionTest` and `RestartTest`
with each of two mesh types (`2000m` and `variable_resolution`).  We will
explore this further when we talk about {ref}`dev-test-cases` and
{ref}`dev-steps` below.

It is also common for a test group to define takes care of setting any
additional config options that apply across all test cases but are too
complicated to simply add to the `<test_group.cfg>` file.

An example of a shared `configure()` function is
{py:func}`polaris.ocean.tests.baroclinic_channel.configure()`:

```python
def configure(resolution, config):
    """
    Modify the configuration options for one of the baroclinic test cases

    Parameters
    ----------
    resolution : str
        The resolution of the test case

    config : configparser.ConfigParser
        Configuration options for this test case
    """
    res_params = {'10km': {'nx': 16,
                           'ny': 50,
                           'dc': 10e3},
                  '4km': {'nx': 40,
                          'ny': 126,
                          'dc': 4e3},
                  '1km': {'nx': 160,
                          'ny': 500,
                          'dc': 1e3}}

    if resolution not in res_params:
        raise ValueError('Unsupported resolution {}. Supported values are: '
                         '{}'.format(resolution, list(res_params)))
    res_params = res_params[resolution]
    for param in res_params:
        config.set('baroclinic_channel', param, '{}'.format(res_params[param]))
```

In the `baroclinic_channel` test group, 3 resolutions are supported:
`1km`, `4km` and `10km`.  Here, we use a dictionary to define parameters
(the size of the mesh) associated with each resolution and then to set config
options with those parameters.  This approach is appropriate if we want a user
to be able to modify these config options before running the test case (in this
case, if they would like to run on a mesh of a different size or resolution).
If these parameters should be held fixed, they should not be added to the
`config` object but rather as attributes to the test case's and/or step's
class, as we will discuss below.

As with components and the main `polaris` package, test groups can also have
a shared "framework" of packages, modules, config files, namelists, and streams
files that is shared among test cases and steps.
