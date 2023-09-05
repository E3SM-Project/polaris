(glossary)=

# Glossary

Polaris

: The python package containing framework for listing, setting up and running
  tasks, as well as code defining the components, tasks and steps.

Compass

: The predecessor to polaris that was focused on MPAS components and did not
  support task parallelism

Component

: This term refers to the collection of tasks associated with one or more
  E3SM components, `ocean` for MPAS-Ocean and OMEGA, `seaice` for MPAS-Seaice,
  and `landice` for MALI.

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
  either run all together or one at a time.  A task in polaris should always
  be independent of other tasks.  Some common examples of tasks are bit-for-bit 
  restart tests, decomposition tests across different numbers of cores, and
  thread tests with different thread counts.  Whereas compass allowed tasks to
  depend on other tasks, this is discouraged in polaris.  Instead, shared steps
  should be used to support common functionality.

Suite

: A collection of tasks that are from the same E3SM component that can be run 
  together with a single command (`polaris run <suite>`, where `<suite>` is the
  suite's name). Sometimes, suites are used to perform regression testing to 
  make sure new MPAS-model features do not add unexpected changes to simulation
  results.  Typically, this involves providing a "baseline" run of the same
  suite to compare with.  Other types of suites are used to run
  a sequence of tasks that depend on one another (e.g. creating a mesh,
  setting up an initial condition, running the model, and processing the
  output, as in {ref}`ocean-global-ocean`).

Work directory

: The location where tasks will be set up and run.  The "base work
  directory" is the root for all E3SM components (and therefore tasks and 
  steps), and is the path passed with the `-w` or `-b` flags to 
  {ref}`dev-polaris-setup` and {ref}`dev-polaris-suite`.  The work directory 
  for a task or step its location within base work directory (the base work 
  directory plus its relative path)

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
