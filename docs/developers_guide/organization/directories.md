:::{figure} images/org_in_package.png
:align: right
:figwidth: 50 %
:width: 311 px

Figure 1: An out-of-date diagram of the organization of components (green), 
categories of tasks (blue), tasks (orange) and steps (red) in the `polaris`
package.
:::

(dev-directories)=

# Directory structure

In the `polaris` package within a local clone of the polaris repository,
components, tasks and steps are laid out like shown in Fig 1.

Each component has its directory with the `polaris` package directory. Among
other contents of the component's directory is a `tasks` directory that
contains all of the tasks, typically sorted into categories.  Each subdirectory
has directories or modules for the tasks and typically also python modules that 
define the step classes shared between tasks. Any step classes that are 
specific to a task would have a module within that task's subdirectory.

More details on each of these organizational concepts -- {ref}`dev-components`,
{ref}`dev-categories-of-tasks`, {ref}`dev-tasks`, and {ref}`dev-steps` -- are
provided below.

The organization of the work directory similar but not quite the same as in the
`polaris` package, as shown in Fig. 2.

:::{figure} images/org_in_work_dir.png
:align: right
:figwidth: 50 %
:width: 283 px

Figure 2: An out-of-date diagram of the organization of components (green), 
categories of tasks (blue), tasks (orange) and steps (red) in an example work
directory.
:::

At the top level are directories for the components.  There is no `tasks`
subdirectory in this case -- the subdirectories for the tasks are directly 
within the components' directory.  The organization of tasks within component
can include many additional subdirectories that help sort different categories
of tasks and versions of each task.  In the examples shown above, each task is 
in a subdirectory indicating the category of task and then the resolution of 
the mesh used in the task. Steps that are shared between tasks are also in
subdirectories of the component.  Often, shared steps are outside of any task
work directory, perhaps at the same level as the tasks that share them.
Sometimes, it is appropriate for shared steps to be inside of a task (e.g. if
all steps of one task are also steps of another task).  Steps that are not
shared between tasks should reside in subdirectories of that task. In some 
cases, additional subdirectories are used to sort steps within a task 
(e.g. if the same step will be run at different mesh resolutions in a 
convergence test).
