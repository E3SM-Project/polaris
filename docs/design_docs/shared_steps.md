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

### Implementation: Shared steps are run before steps that depend on their output.

Requirement is already satisfied as part of task parallelism design, which
makes use of file dependencies.  When running in task-serial mode, the implementation
will be to make sure shared steps are added to the dictionary of steps before other steps
that rely on them.

### Implementation: Output of shared steps may be used by multiple tasks.

Task steps that use the output of shared steps will make use of symbolic
links as before.

## Testing

### Testing and Validation: 
