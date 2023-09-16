# Shared steps

date: 2023/08/18

Contributors: Carolyn Begeman, Xylar Asay-Davis

## Summary

The capability designed here is the ability to share steps across tasks.
In this design document, "shared steps" refers to any step which may be used by
multiple tasks that are available in polaris.

The main motivation behind this capability is the computational expense of
running steps that could shared across tasks multiple times. In order to
reflect the fact that steps are shared to the user, we present a new design for
the working directory structure. The design is successful insofar as it
guarantees that shared steps are run once per slurm job and that the role of
shared steps is clear to users.

## Requirements

### Requirement: Shared steps are run once.

Shared steps should be run once per invocation of `polaris serial` or
`polaris run`.

### Requirement: Shared steps are run before steps that depend on their output.

### Requirement: Shared steps are not daughters of a task

A shared step's class attributes do not include any task-related information
such as a task it belongs to.

### Requirement: Working directory structure is intuitive.

Shared step directories should be located at the highest level in the working 
directory structure where all tasks that use that step are run at or below that
level.

### Requirement: Working directory step paths are easily discoverable by users.

There should be a way to list the paths within the work directory of all steps
in each task.  There should also be a way for a user to find the steps
in a task from the task's work directory.

### Requirement: The output of shared steps may be used by multiple tasks.

A step may only be shared across multiple tasks if its output would be
identical for each task.

### Requirement: tasks do not rely on outputs from steps in other tasks

All tasks are self-contained and rely only on either shared steps or steps they
contain.



## Implementation

### Implementation: Shared steps are set up once.

As before, setup of either a list of tasks or a suite proceeds by iterating
through the tasks and then through the steps in each task. An attribute 
`setup_complete` has been added to `Step` and is initialized to `False`.
In the `setup_task()` function, setup is skipped for any steps where 
`step.setup_complete == True`, and this attribute is set to `True` when a step
has been completed.

### Implementation: Shared steps are run before steps that depend on their output.

Requirement is already satisfied as part of task parallelism design, which
makes use of file dependencies.  When running in task-serial mode, the 
implementation will be to make sure shared steps are added to the dictionary of
steps before other steps that rely on them.

### Implementation: Shared steps are not daughters of a task

The `task` attribute and constructor argument of the `Step` class has been
replaced by the `component` attribute.  The step's `subdir` attribute is now
relative to the component's work directory, rather than a parent task's work
directory.

### Implementation: Working directory structure is intuitive.

The only shared steps that reside inside of a task's work directory are in
situations where another task also lies within the task's work directory.
The only such tasks at the moment are the `cosine_bell/with_viz` tasks, which
reside inside the `cosine_bell` tasks.  The `cosine_bell/with_viz` tasks share
all of the steps of the `cosine_bell` (base-mesh, init and forward for each
resolution, and a single analysis step) and also add remapping and
visualization steps that are not shared with any other tasks:

`cosine_bell`:
 * `ocean`
   * `spherical`
     * `qu`
       * `base_mesh`
         * `60km`
         * `90km`
         * `120km`
         * `150km`
         * `180km`
         * `210km`
         * `240km`
       * `cosine_bell`
         * `init`
           * `60km`
           * `90km`
           * `120km`
           * `150km`
           * `180km`
           * `210km`
           * `240km`
         * `forward`
           * `60km`
           * `90km`
           * `120km`
           * `150km`
           * `180km`
           * `210km`
           * `240km`
         * `analysis`

`cosine_bell/with_viz`:
 * `ocean`
   * `spherical`
     * `qu`
       * `base_mesh`
         * `60km`
         * `90km`
         * `120km`
         * `150km`
         * `180km`
         * `210km`
         * `240km`
       * `cosine_bell`
         * `init`
           * `60km`
           * `90km`
           * `120km`
           * `150km`
           * `180km`
           * `210km`
           * `240km`
         * `forward`
           * `60km`
           * `90km`
           * `120km`
           * `150km`
           * `180km`
           * `210km`
           * `240km`
         * `analysis`
         * `with_viz`
           * `map`
             * `60km`
             * `90km`
             * `120km`
             * `150km`
             * `180km`
             * `210km`
             * `240km`
           * `viz`
             * `60km`
             * `90km`
             * `120km`
             * `150km`
             * `180km`
             * `210km`
             * `240km`


### Implementation: Working directory step paths are easily discoverable by users.

This is implemented in two ways.

First, `polaris list --verbose` now lists the work-directory relative path of 
steps, rather than their path relative to the task's work directory:

```
$ polaris list --verbose

...

  10: path:          ocean/spherical/qu/cosine_bell/with_viz
      name:          cosine_bell
      component:     ocean
      subdir:        spherical/qu/cosine_bell/with_viz
      steps:
       - qu_base_mesh_60km:  ocean/spherical/qu/base_mesh/60km
       - qu_init_60km:       ocean/spherical/qu/cosine_bell/init/60km
       - qu_forward_60km:    ocean/spherical/qu/cosine_bell/forward/60km
       - qu_map_60km:        ocean/spherical/qu/cosine_bell/with_viz/map/60km
       - qu_viz_60km:        ocean/spherical/qu/cosine_bell/with_viz/viz/60km
       - qu_base_mesh_90km:  ocean/spherical/qu/base_mesh/90km
       - qu_init_90km:       ocean/spherical/qu/cosine_bell/init/90km
       - qu_forward_90km:    ocean/spherical/qu/cosine_bell/forward/90km
       - qu_map_90km:        ocean/spherical/qu/cosine_bell/with_viz/map/90km
       - qu_viz_90km:        ocean/spherical/qu/cosine_bell/with_viz/viz/90km
       - qu_base_mesh_120km: ocean/spherical/qu/base_mesh/120km
       - qu_init_120km:      ocean/spherical/qu/cosine_bell/init/120km
       - qu_forward_120km:   ocean/spherical/qu/cosine_bell/forward/120km
       - qu_map_120km:       ocean/spherical/qu/cosine_bell/with_viz/map/120km
       - qu_viz_120km:       ocean/spherical/qu/cosine_bell/with_viz/viz/120km
       - qu_base_mesh_150km: ocean/spherical/qu/base_mesh/150km
       - qu_init_150km:      ocean/spherical/qu/cosine_bell/init/150km
       - qu_forward_150km:   ocean/spherical/qu/cosine_bell/forward/150km
       - qu_map_150km:       ocean/spherical/qu/cosine_bell/with_viz/map/150km
       - qu_viz_150km:       ocean/spherical/qu/cosine_bell/with_viz/viz/150km
       - qu_base_mesh_180km: ocean/spherical/qu/base_mesh/180km
       - qu_init_180km:      ocean/spherical/qu/cosine_bell/init/180km
       - qu_forward_180km:   ocean/spherical/qu/cosine_bell/forward/180km
       - qu_map_180km:       ocean/spherical/qu/cosine_bell/with_viz/map/180km
       - qu_viz_180km:       ocean/spherical/qu/cosine_bell/with_viz/viz/180km
       - qu_base_mesh_210km: ocean/spherical/qu/base_mesh/210km
       - qu_init_210km:      ocean/spherical/qu/cosine_bell/init/210km
       - qu_forward_210km:   ocean/spherical/qu/cosine_bell/forward/210km
       - qu_map_210km:       ocean/spherical/qu/cosine_bell/with_viz/map/210km
       - qu_viz_210km:       ocean/spherical/qu/cosine_bell/with_viz/viz/210km
       - qu_base_mesh_240km: ocean/spherical/qu/base_mesh/240km
       - qu_init_240km:      ocean/spherical/qu/cosine_bell/init/240km
       - qu_forward_240km:   ocean/spherical/qu/cosine_bell/forward/240km
       - qu_map_240km:       ocean/spherical/qu/cosine_bell/with_viz/map/240km
       - qu_viz_240km:       ocean/spherical/qu/cosine_bell/with_viz/viz/240km
       - analysis:           ocean/spherical/qu/cosine_bell/analysis
```

Second, we add symlinks within the task to the shared step.  In what follows,
each resolution in the `base_mesh`, `init` and `forward` subdirectories are
symlinks to the shared steps that reside elsewhere.  `analysis` is also a
symlink.

`cosine_bell/with_viz`:
 * `ocean`
   * `spherical`
     * `qu`
       * `cosine_bell`
         * `with_viz`
           * `base_mesh`
             * `60km`
             * `90km`
             * `120km`
             * `150km`
             * `180km`
             * `210km`
             * `240km`
           * `init`
             * `60km`
             * `90km`
             * `120km`
             * `150km`
             * `180km`
             * `210km`
             * `240km`
           * `forward`
             * `60km`
             * `90km`
             * `120km`
             * `150km`
             * `180km`
             * `210km`
             * `240km`
           * `map`
             * `60km`
             * `90km`
             * `120km`
             * `150km`
             * `180km`
             * `210km`
             * `240km`
           * `viz`
             * `60km`
             * `90km`
             * `120km`
             * `150km`
             * `180km`
             * `210km`
             * `240km`
           * `analysis`

Thus, a structure similar to what we had before shared steps is maintained
locally, which should make debugging easier.

### Implementation: The output of shared steps may be used by multiple tasks.

Task steps that use the output of shared steps will make use of symbolic
links as before.

### Implementation: tasks do not rely on outputs from steps in other tasks

There were not any polaris tasks that relied on outputs from other tasks even
before the implementation of shared steps.  There are tasks in Compass, though,
such as global ocean `mesh`, `init` and `dynamic_adjustment`, that do allow 
outputs from one task to be inputs of another.  As these are ported to Polaris,
we will make sure they use shared steps instead.

## Testing

### Testing And Validation: Shared steps are run once.

Output from running a series of tasks or a suite indicates when shared steps
are skipped because they already ran (`already completed`):

```
ocean/spherical/icos/cosine_bell
  * step: icos_base_mesh_60km
          execution:        SUCCESS
          runtime:          0:01:00
  * step: icos_init_60km
          execution:        SUCCESS
          runtime:          0:00:00
  * step: icos_forward_60km
          execution:        SUCCESS
          runtime:          0:00:38
  ...
  * step: analysis
          execution:        SUCCESS
          runtime:          0:00:02
  task execution:   SUCCESS
  task runtime:     0:02:59

ocean/spherical/icos/cosine_bell/with_viz
  * step: icos_base_mesh_60km
          already completed
  * step: icos_init_60km
          already completed
  * step: icos_forward_60km
          already completed
  * step: icos_map_60km
          execution:        SUCCESS
          runtime:          0:00:20
  * step: icos_viz_60km
          execution:        SUCCESS
          runtime:          0:00:06
  ...
  * step: analysis
          already completed
  task execution:   SUCCESS
  task runtime:     0:03:23
```

### Testing And Validation: Shared steps are run before steps that depend on their output.

As before, steps are added to tasks in the order they are to be run, ensuring
that shared steps run before steps that require their output when running in 
task serial (`polaris serial`).  Task parallelism already has mechanisms to
prevent steps from running before their dependencies are available, and this
is not expected to be affected by shared steps.  However, no testing with
task parallelism will be performed at this time.

### Testing And Validation: Shared steps are not daughters of a task

Steps run successfully even after we have removed the `task` attribute from
them, indicating that they no longer rely on information about a task they
formerly belonged to.

### Testing And Validation: Working directory structure is intuitive.

The intuitive work structure will need to be maintained by developers as new
tasks and steps are added, as this is not enforced by the framework.  The
proposed implementation ensures that shared steps either reside close to the
root of the directory structure from the tasks that use them or that they
live inside of the tasks, which we have deemed an intuitive structure.

### Testing And Validation: Working directory step paths are easily discoverable by users.

Between `polaris list --verbose` and the local symlinks to shared steps within
each task, we think the shared steps will be discoverable by users and
developers.

### Testing And Validation: The output of shared steps may be used by multiple tasks.

We have implemented shared steps for base meshes, initial conditions and
forward runs, and shown that multiple tasks can make use of their output.

### Testing And Validation: tasks do not rely on outputs from steps in other tasks

This is not enforced, it will simply need to be maintained as the preferred
convention for future development.  Currently, all tasks can be run
independently and do not rely on any other tasks.
