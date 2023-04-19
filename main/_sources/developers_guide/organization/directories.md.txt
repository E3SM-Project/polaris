:::{figure} images/org_in_package.png
:align: right
:figwidth: 50 %
:width: 311 px

Figure 1: The organization of components (green), test groups (blue), test
cases (orange) and steps (red) in the `polaris` package.
:::

(dev-directories)=

# Directory structure

In the `polaris` package within a local clone of the polaris repository,
components, test groups, test cases and steps are laid out like shown in Fig 1.

Each component has its directory with the `polaris` package directory. Among
other contents of the component's directory is a `tests` directory that
contains all of the test groups.  Each test group contains directories for
the test cases and typically also python modules that define the shared steps.
Any steps that are specific to a test case would have a module within that
test case's directory.

More details on each of these organizational concepts -- {ref}`dev-components`,
{ref}`dev-test-groups`, {ref}`dev-test-cases`, and {ref}`dev-steps` -- are
provided below.

The organization of the work directory similar but not quite the same as in the
`polaris` package, as shown in Fig. 2.

:::{figure} images/org_in_work_dir.png
:align: right
:figwidth: 50 %
:width: 283 px

Figure 2: The organization of components (green), test groups (blue), test
cases (orange) and steps (red) in an example work directory.
:::

At the top level are directories for the components.  There is no `tests`
subdirectory in this case -- the test groups are directly within the MPAS
core's directory.  The organization of test cases within a test group can
include many additional subdirectories that help sort different versions of
the test cases.  In the examples shown above, each test case is in a
subdirectory indicating the resolution of the mesh used in the test case.
Finally, steps are in subdirectories of each test case.  In some cases,
additional subdirectories are used to sort steps within a test case (e.g. if
the same step will be run at different mesh resolutions in a convergence test).