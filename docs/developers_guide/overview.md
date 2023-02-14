(dev-overview)=

# Overview

Polaris is a [python package](https://docs.python.org/3/tutorial/modules.html#packages).
All of the code in the package can be accessed in one of two ways.  The first
is the command-line interface with commands like {ref}`dev-polaris-list` and
{ref}`dev-polaris-setup`.  The second way is through import commands like:

```python
from polaris.io import symlink


symlink('../initial_condition/initial_condition.nc', 'init.nc')
```

Before we dig into the details of how to develop new test cases and other
infrastructure for polaris, we first give a little bit of background on
the design philosophy behind the package.

(dev-style)=

## Code Style

All code is required to adhere fairly strictly to the
[PEP8 style guide](https://www.python.org/dev/peps/pep-0008/).  A bot will
flag any PEP8 violations as part of each pull request to
<https://github.com/E3SM-Project/polaris>.  Please consider using an editor that
automatically flags PEP8 violations during code development, such as
[pycharm](https://www.jetbrains.com/pycharm/) or
[spyder](https://www.spyder-ide.org/), or a linter, such as
[flake8](https://flake8.pycqa.org/en/latest/) or
[pep8](https://pep8.readthedocs.io/).  We discourage you from automatically
reformatting your code (e.g. with [autopep8](https://github.com/hhatto/autopep8))
because this can often produce undesirable and confusing results.

The [flake8](https://flake8.pycqa.org/en/latest/) utility for linting python
files to the PEP8 standard is included in the POLARIS conda environment. To use
flake8, just run `flake8` from any directory and it will return lint results
for all files recursively through all subdirectories.  You can also run it for a
single file or using wildcards (e.g., `flake8 *.py`).  There also is a
[vim plugin](https://github.com/nvie/vim-flake8) that runs the flake8 linter
from within vim.  If you are not using an IDE that lints automatically, it is
recommended you run flake8 from the command line or the vim plugin before
committing your code changes.

(dev-packages)=

## Packages and Modules

Why a python package?  That sounds complicated.

Some of the main advantages of polaris being a package instead of a group
of scripts are that:

1. it is a lot easier to share code between test cases;
2. there is no need to create symlinks to individual scripts or use
   [subprocess](https://docs.python.org/3/library/subprocess.html) calls to
   run one python script from within another;
3. functions within polaris modules and subpackages have relatively simple
   interfaces that are easier to document and understand than the arguments
   passed into a script; and
4. releases of the polaris package would make it easy for developers of
   other python packages and scripts to use our code (though there are not yet
   any "downstream" packages that use polaris).

This documentation won't try to provide a whole tutorial on python packages,
modules and classes but we know most developers won't be too clued in on these
concepts so here's a short intro.

### Packages

A python package is a directory that has a file called `__init__.py`.  That
file can be empty or it can have code in it.  If it has functions or classes
inside of it, they act like they're directly in the package.  As an example,
the polaris file
[polaris/ocean/\_\_init\_\_.py](https://github.com/E3SM-Project/polaris/tree/main/polaris/ocean/__init__.py)
has a class {py:class}`polaris.ocean.Ocean()` that looks like this (with the
[docstrings](https://www.python.org/dev/peps/pep-0257/) stripped out):

```python
class Ocean(Component):
    def __init__(self):
        super().__init__(name='ocean')

        self.add_test_group(GlobalConvergence(component=self))

    def configure(self, config):
        section = config['ocean']
        model = section.get('model')
        configs = {'mpas-ocean': 'mpas_ocean.cfg',
                   'omega': 'omega.cfg'}
        if model not in configs:
            raise ValueError(f'Unknown ocean model {model} in config options')

        config.add_from_package('polaris.ocean', configs[model])
```

This class contains all of the ocean test groups, which contain all the ocean
test cases and their steps.  The details aren't important.  The point is that
the class can be imported like so:

```python
from polaris.ocean import Ocean


ocean = Ocean()
```

So you don't ever refer to `__init__.py`, it's like a hidden shortcut so the
its contents can be referenced with just the subdirectory (package) name.

A package can contain other packages and modules (we'll discuss these in just
a second).  For example, the `ocean` package mentioned above is inside the
`polaris` package.  The sequence of dots in the import is how you find your
way from the root (`polaris` for this package) into subpackages and modules.
It's similar to the `/` characters in a unix directory.

### Modules

Modules are just python files that aren't scripts.  Since you can often treat
scripts like modules, even that distinction isn't that exact.  But for the
purposes of the `polaris` package, every single file ending in `.py` in the
`polaris` package is a module (except maybe the `__init__.py`, not sure
about those...).

As an example, the `polaris` package contains a module `list.py`.
There's a function {py:func}`polaris.list.list_machines` in that module:

```python
def list_machines():
    machine_configs = sorted(contents('polaris.machines'))
    print('Machines:')
    for config in machine_configs:
        if config.endswith('.cfg'):
            print(f'   {os.path.splitext(config)[0]}')
```

It lists the supported machines.  You would import this function just like in
the package example above:

```python
from polaris.list import list_machines


list_machines()
```

So a module named `foo.py` and a package in a directory named `foo` with
an `__init__.py` file look exactly the same when you import them.

So why choose one over the other?

The main reason to go with a package over a module is if you need to include
other files (such as other modules and packages, but also other things like
{ref}`config-files`, namelists and streams files).  It's
always pretty easy to make a module into a package (by making a directory with
the name of the package, moving the module in, an renaming it `__init__.py`)
or visa versa (by renaming `__init__.py` to the module name, moving it up
a directory, and deleting the subdirectory).

### Classes

In the process of developing
[MPAS-Analysis](https://github.com/MPAS-Dev/MPAS-Analysis/), we found that
many of our developers were not very comfortable with
[classes](https://docs.python.org/3/tutorial/classes.html), methods,
[inheritance](https://docs.python.org/3/tutorial/classes.html#inheritance)
and other concepts related to
[object-oriented programming](https://en.wikipedia.org/wiki/Object-oriented_programming).
In MPAS-Analysis, tasks are implemented as classes to make it easier to use
python's [multiprocessing](https://docs.python.org/3/library/multiprocessing.html)
capability.  In practice, this led to code that was complex enough that only
a handful of developers felt comfortable contributing directly to the code.

Based on this experience, we were hesitant to use classes in compass, the
predecessor to polaris and tried an implementation without them.  This led to a
clumsy set of functions and 
[python dictionaries](https://docs.python.org/3/tutorial/datastructures.html#dictionaries)
that was equally complex but harder to understand and document than classes.

The outcome of this experience is that we have used classes to define
components, test groups, test cases and steps.  Each component will "descend"
from the {py:class}`polaris.Component` base class; each test groups descends
from {py:class}`polaris.TestGroup`; each test case descends from
{py:class}`polaris.TestCase`; and each steps descends from
{py:class}`polaris.Step`.  These base classes contain functionality that can
be shared with the "child" classes that descend from them and also define
a few "methods" (functions that belong to a class) that the child class is
meant to "override" (replace with their own version of the function, or augment
by replacing the function and then calling the base class's version of the
same function).

We have some tutorials on how to add new components, test groups, test
cases and steps, and more will be developed in the near future.  These will 
explain the main features of  classes that developers need to know about.  
We also hope that the tests currently in the package can provide a starting 
point for new development.

(dev-code-sharing)=

## Code sharing

The `polaris` package is dense and will have a learning curve.  We hope
the python package approach is worth it because the skills learned to work with
it will be broadly applicable to understanding and developing other python
packages. In developing polaris we endeavor to increase  code  readability and
code sharing in a number of ways.

### ...in the polaris framework

The polaris framework (modules and packages not in the component packages)
has a lot of code that is shared across existing test cases and could be very
useful for future ones.

The framework has been broken into modules that make it clear what 
functionality each contains, e.g. `polaris.namelists` and
`polaris.streams` are for manipulating namelist and
streams files, respectively; `polaris.io` has functionality for
downloading files from the
[LCRC server](https://web.lcrc.anl.gov/public/e3sm/polaris/)
and creating symlinks; `polaris.validation` can be used to ensure that
variables are bit-for-bit identical between steps or when compared with a
baseline, and to compare timers with a baseline; and the
`polaris.parallel` module contains a function  
{py:func}`polaris.parallel.get_available_cores_and_nodes()` that can find out
the number of total cores and nodes available for running steps.

### ...within a component

A component in polaris could, theoretically, build out functionality as
complex as in the E3SM components themselves.  This has already been
accomplished for several of the idealized test cases included in polaris. As an
example, the shared functionality in the {ref}`dev-ocean` is described in
{ref}`dev-ocean-framework`.

### ...within a test group

So far, the most common type of shared code within test group are modules
defining steps that are used in multiple test cases.  For example, the
{ref}`dev-ocean-baroclinic-channel` configuration uses shared modules to define
the `initial_state` and `forward` steps of each test case.  Configurations
also often include namelist and streams files with replacements to use across
test cases.

In addition to shared steps, the {ref}`dev-ocean-global-ocean` configuration
includes some additional shared framework described in
{ref}`dev-ocean-global-ocean-framework`.

The shared code in `global_ocean` has made it easy to define dozens different
test cases using the QU240 or QUwISC240 meshes.  This is possible because
the same conceptual test (e.g. restart) can be defined:

> - with or without ice-shelf cavities
> - with the RK4 or split-explicit time integrators

In theory, we could provide additional variants of these test cases with 
different  initial conditions and other capabilities such as support for 
biogeochemistry.

### ...within a test case

The main way code is currently reused with a test case is when the same module
for a step gets used multiple times within a test case.  For example,
the {ref}`dev-ocean-baroclinic-channel-rpe-test` test case uses the same
forward run with 5 different values of the viscosity.
