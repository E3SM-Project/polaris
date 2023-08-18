# Shared steps

date: 2023/08/18

Contributors: Carolyn Begeman, Xylar Asay-Davis

## Summary

The capability designed here is the ability to share steps across test cases.
In this design document, "shared steps" refers to any step which may be used by
multiple test cases that are available in polaris.

The main motivation behind this capability is the computational expense of
running steps that could shared across test cases multiple times. In order to
reflect the fact that steps are shared to the user, we present a new design for
the working directory structure. The design is successful insofar as it
guarantees that shared steps are run once per slurm job and that the role of
shared steps is clear to users.

## Requirements

### Requirement: Shared steps are set up once (optional).

Ideally, steps used by multiple test cases should be run once per invocation of
`polaris setup` or `polaris suite`. This requirement may be dropped since step
set up is not generally resource intensive.

### Requirement: Shared steps are run once.

Shared steps should be per run once per invocation of `polaris serial` or
`polaris parallel`.

### Requirement: Shared steps are run before steps that depend on their output.

### Requirement: Object properties of shared steps are intuitive.

Shared steps are not daughters of test cases.

### Requirement: Working directory structure is intuitive.

The working directory structure should not have shared step directories as
subdirectories of test cases.

### Requirement: Working directory step paths are easily discoverable by users.

The verbose option to `polaris list` lists the relative paths at which steps
would be set up for each test case.

### Requirement: The output of shared steps may be used by multiple test cases.

A step may only be shared across multiple test cases if its output would be
identical for each test case.



## Implementation

### Implementation: Shared steps are run before steps that depend on their output.

Requirement is already satisfied as part of task parallelism design, which
makes use of file dependencies.

### Implementation: Output of shared steps may be used by multiple test cases.

Test case steps that use the output of shared steps will make use of symbolic
links as before.

## Testing

### Testing and Validation: 
