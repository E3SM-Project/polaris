(glossary)=

# Glossary

Polaris

: The python package containing framework for listing, setting up and running
  tasks, as well as code defining the components, test groups, tasks and 
  steps.

Compass

: The predecessor to polaris that used XML files and python scripts to define
  components, test groups, tasks and steps.

Component

: This term refers to the collection of tasks associated with one or more
  E3SM components, `ocean` for MPAS-Ocean and OMEGA, and `landice` for MALI.

Step

: A step is the smallest units of work in polaris that you can run on
  its own.  Each task is made up of a sequence of steps.  Currently,
  these steps run in sequence, but there are plans to allow them to run in
  parallel with one another (task parallelism) in the near future.  Steps are
  commonly used to create meshes and initial conditions (together or 
  separately), run an E3SM component in standalone mode, and to perform
  visualization or analysis of the results.

Task

: A task is the smallest unit of work that polaris will let a user
  set up on its own.  It is a sequence of one or more steps that a user can
  either run all together or one at a time.  A task is often independent
  of other tasks.  For example, many test groups in polaris include
  tasks for checking bit-for-bit restart and decomposition across
  different numbers of cores and threads.  Sometimes, it is convenient to
  have tasks that depend on other tasks.  The most common example
  of this in polaris are tasks that create meshes and/or initial
  conditions that are used in several subsequent tasks.

Test group

: A test group is a collection of tasks with a common concept or
  purpose.  Each polaris component defines several test groups.  Examples in
  the {ref}`landice` are {ref}`landice-dome` and {ref}`landice-greenland`, 
  while  examples from {ref}`ocean` include {ref}`ocean-baroclinic-channel` and
  {ref}`ocean-global-ocean`.

Suite

: A collection of tasks that are from the same E3SM component (but not
  necessarily the same test group) that can be run together with a single
  command (`polaris run <suite>`, where `<suite>` is the suite's name).
  Sometimes, suites are used to perform regression testing to make sure
  new MPAS-model features do not add unexpected changes to simulation
  results.  Typically, this involves providing a "baseline" run of the same
  suite to compare with.  Other types of suites are used to run
  a sequence of tasks that depend on one another (e.g. creating a mesh,
  setting up an initial condition, running the model, and processing the
  output, as in {ref}`ocean-global-ocean`).

Work directory

: The location where tasks will be set up and run.  The "base work
  directory" is the root for all E3SM components (and therefore test groups, 
  tasks and steps), and is the path passed with the `-w` or `-b` flags
  to {ref}`dev-polaris-setup` and {ref}`dev-polaris-suite`.  The work
  directory for a task or step its location within base work directory
  (the base work directory plus its relative path)

Package

: A python package is a directory that has a file called `__init__.py`.
  That file can be empty or it can have code in it.  If there is code in
  `__init__.py`, it gets imported as if it were directly in the package
  (you never include `__init__` in an `import` statement).

Module

: Python modules are python files that can be imported by other python files
  (so they're not just scripts).  Nearly every single file ending in `.py`
  in the polaris package is a module.  The `__init__.py` files are a
  special case, that may define a module with the name of the package
  (directory) that `__init__.py` is in.
