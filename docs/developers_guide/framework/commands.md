(dev-command-mods)=

# Modules for polaris commands

(dev-list)=

## list module

The {py:func}`polaris.list.list_cases()`, {py:func}`polaris.list.list_machines()`
and {py:func}`polaris.list.list_suites()` functions are used by the
`polaris list` command to list test cases, supported machines and test
suites, respectively.  These functions are not currently used anywhere else
in polaris.

(dev-setup)=

## setup module

The {py:func}`polaris.setup.setup_cases()` and {py:func}`polaris.setup.setup_case()`
functions are used by `polaris setup` and `polaris suite` to set up a list
of test cases and a single test case, respectively, in a work directory.
Subdirectories will be created for each test case and its steps; input,
namelist and streams files will be downloaded, symlinked and/or generated
in the setup process. A [pickle file](https://docs.python.org/3/library/pickle.html)
called `test_case.pickle` will be written to each test case directory
containing the test-case object for later use in calls to `polaris run`.
Similarly, a file `step.pickle` containing both the step and test-case
objects will be written to each step directory, allowing the step to be run
on its own with `polaris run`.  In contrast to {ref}`config-files`, these
pickle files are not intended for users (or developers) to read or modify.
Properties of the test-case and step objects are not intended to change between
setting up and running a test suite, test case or step.

(dev-clean)=

## clean module

The {py:func}`polaris.clean.clean_cases()` function is used by
`polaris clean` and `polaris suite` to delete the constants of a test-case
subdirectory in the work directory.

(dev-suite)=

## suite module

The {py:func}`polaris.suite.setup_suite()` and {py:func}`polaris.suite.clean_suite()`
functions are used by `polaris suite` to set up or clean up a test suite in a
work directory.  Setting up a test suite includes setting up the test cases
(see {ref}`dev-setup`), writing out a {ref}`dev-provenance` file, and saving
a pickle file containing a python dictionary that defines the test suite for
later use by `polaris run`.  The "target" and "minimum" number of cores
required for running the test suite are displayed.  The "target" is determined
based on the maximum product of the `ntasks` and `cpus_per_task`
attributes of each step in the test suite.  This is the number of cores to run
on to complete the test suite as quickly as possible, with the
caveat that many cores may sit idle for some fraction of the runtime.  The
"minimum" number of cores is the maximum of the product of the `min_tasks`
and `min_cpus_per_task` attribute for all steps in the suite, indicating the
fewest cores that the test may be run with before at least some steps in the
suite will fail.

(dev-run)=

## run.serial module

The function {py:func}`polaris.run.serial.run_tests()` is used to run a
test suite or test case and {py:func}`polaris.run.serial.run_single_step()` is
used to run a single step using `polaris run`.  `run_tests()` performs
setup operations like creating a log file and figuring out the number of tasks
and CPUs per task for each step, then it calls each step's `run()` method.

Suites run from the base work directory with a pickle file starting with the
suite name, or `custom.pickle` if a suite name was not given. Test cases or
steps run from their respective subdirectories with a `testcase.pickle` or
`step.pickle` file in them. Both of these functions reads the local pickle
file to retrieve information about the test suite, test case and/or step that
was stored during setup.

If {py:func}`polaris.run.serial.run_tests()` is used for a test suite, it will
run each test case in the test suite in the order that they are given in the
text file defining the suite (`polaris/<component>/suites/<suite_name>.txt`).
Output from test cases and their steps are stored in log files in the
`case_output` subdirectory of the base work directory. If the function is
used for a single test case, it will run the steps of that test case, writing
output for each step to a log file starting with the step's name. In either
case (suite or individual test), it displays a `PASS` or `FAIL` message for
the test execution, as well as similar messages for validation involving output
within the test case or suite and validation against a baseline (depending on
the implementation of the `validate()` method in the test case and whether a
baseline was provided during setup).

{py:func}`polaris.run.run_single_step()` runs only the selected step from a
given test case, skipping any others, displaying the output in the terminal
window rather than a log file.

(dev-cache)=

## cache module

The {py:func}`polaris.cache.update_cache()` function is used by
`polaris cache` to copy step outputs to the `polaris_cache` database on
the LCRC server and to update `<component>_cached_files.json` files that
contain a mapping between these cached files and the original outputs.  This
functionality enables running steps with {ref}`dev-step-cached-output`, which
can be used to skip time-consuming initialization steps for faster development
and debugging.
