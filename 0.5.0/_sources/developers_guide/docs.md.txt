(dev-docs)=

# Documentation

The polaris documentation is generated using the
[Sphinx](https://www.sphinx-doc.org/en/master/) package and is written in
[MyST](https://myst-parser.readthedocs.io/en/latest/syntax/syntax.html)
format.  We recommend these [basic tips](https://myst-parser.readthedocs.io/en/latest/syntax/roles-and-directives.html#roles-directives)
on using MyST in Sphinx.

Another easy way to get started is by taking a look at the existing source
code for the documentation: <https://github.com/E3SM-Project/polaris/tree/main/docs/>

Each time you add a component or task, the corresponding
documentation must be included with the pull request to add the code.  This
includes documentation for both the User's Guide and the Developer's Guide.
For examples, see:

- {ref}`ocean` in the User's Guide
- {ref}`ocean-baroclinic-channel` tasks in the User's Guide
- {ref}`dev-ocean` in the Developer's Guide
- {ref}`dev-ocean-baroclinic-channel` tasks in the Developer's Guide

Documentation for each component in the User's guide should include a label 
with the name of the component:

```markdown
(ocean)=

# Ocean
...
```

In the Developer's Guide, labels have `dev-` prepended to them:

```markdown
(dev-ocean)=

# Ocean component
...
```

Each category of tasks (e.g. baroclinic channel) should have its own page in
the `tasks` subdirectory of the component. The label for the page should have
have the component name prepended (to make sure it's unique), and each task 
(if explicitly labeled) should have the component and category of tasks 
prepended to it. Thus, in the User's guide, we have:

```markdown
(ocean-baroclinic-channel)=

# baroclinic_channel

...

(ocean-baroclinic-channel-default)=

## default

...
```

And in the Developer's guide, these become:

```markdown
(dev-ocean-baroclinic-channel)=

# baroclinic_channel

...

(dev-ocean-baroclinic-channel-default)=

## default

...
```

Documentation for a component or task in the User's Guide
should contain information that is needed for users who set up and run the test
case, including:

- Documentation for the component itself (if any)

- A page for each category of tasks with a section for each task:

  - A citation or link where the test case that is the basis for the tasks is 
    defined (if any)
  - A brief overview of the common characteristics of the tasks
  - An image showing typical output from one of the tasks
  - A list of (commented) config options that apply to all tasks
  - A (typically brief) description of each task
  - The following sections as described in the template: description, mesh,
    vertical grid, initial conditions, forcing, time step, config, and cores

- A description of any common framework within the component that the test 
  group or task pages may need to refer to.  This should only include
  framework that users may need to be aware of, e.g. because of 
  {ref}`config-files` or namelist options they may wish to edit.

- A description of each suite, including which tasks are included

A template is available for documenting groups of related tasks in the User's 
Guide: {ref}`ocean-category-of-task`

The Developer's guide for each component should contain:

- Relevant technical details about development specific to that component

- A page for each category of tasks:

  - A description of any development-specific details common to all tasks in
    this category
  - A description of shared config, namelist and streams files
  - A description of shared steps
  - A description of any other shared framework code shared between the tasks 
    in that category
  - A description of each task and its steps

- Technical details on the shared framework for the component

Finally, all functions in the tasks and their shared framework that are part of
the public API (i.e. all functions that don't start with an underscore) should 
be added to `docs/<component>/api.md`:

````markdown

### baroclinic_channel

```{eval-rst}
.. currentmodule:: polaris.ocean.tasks.baroclinic_channel

.. autosummary::
   :toctree: generated/

   add_baroclinic_channel_tasks

   forward.Forward
   forward.Forward.compute_cell_count
   forward.Forward.dynamic_model_config

   init.Init
   init.Init.setup
   init.Init.run

...
```
````

The Developer's Guide also contains details on the framework shared across
polaris, so any updates to this framework should include relevant additions
or modifications ot the documentation.

(dev-docstrings)=

## Docstrings

The Developer's Guide includes a {ref}`dev-api` that is automatically generated
from the python code and the [docstrings](https://www.python.org/dev/peps/pep-0257/)
at the beginning of each function.  Polaris uses docstrings in the
[Numpydoc](https://numpydoc.readthedocs.io/en/latest/format.html) format.
The text is in [reStructuredText](https://www.sphinx-doc.org/en/master/usage/restructuredtext/basics.html)
format.  A typical example looks like this:

```python
def compute_land_ice_pressure_and_draft(ssh, modifySSHMask, ref_density):
    """
    Compute the pressure from and overlying ice shelf and the ice-shelf draft

    Parameters
    ----------
    ssh : xarray.DataArray
        The sea surface height (the ice draft)

    modifySSHMask : xarray.DataArray
        A mask that is 1 where ``landIcePressure`` can be deviate from 0

    ref_density : float
        A reference density for seawater displaced by the ice shelf

    Returns
    -------
    landIcePressure : xarray.DataArray
        The pressure from the overlying land ice on the ocean

    landIceDraft : xarray.DataArray
        The ice draft, equal to the initial ``ssh``
    """
```

The docstring must include a brief description of the function.  Then, it
includes a `Parameters` section with entries for each argument.  The argument
are always given on their own line with the type, separated by ` : ` (note
the spaces on either side of the colon).  The type should not be in code format
(i.e. not in double back-quotes) because this interferes with Sphinx's ability
to link to the documentation for the type.  In the example above, Sphinx will
automatically find the API reference to `xarray.DataArray` within the
`xarray` documentation (which is also written using sphinx).  If an argument
is a keyword argument (i.e. given with `arg=value` in the function
declaration), the type should be followed by `, optional`, indicating that
the argument will take on a default value if it is not supplied.

On the next lines after the argument and type, indented by 4 spaces, is a brief
description of the argument.  If the argument is optional and the default value
is not obvious (e.g. `arg=None` is used as an indication that `arg` will be
replaced by something else in the function), it should also be described. If
the default value of the argument is obvious in the function declaration (e.g.
`arg=True`), no further description is necessary.

Finally, if the function returns values, these need to be described in the same
way as the parameters, with the name of the return values followed by a colon
and the type, then a description, indented by 4 spaces.

Other sections such as `Raises` and `Examples` are optional.
