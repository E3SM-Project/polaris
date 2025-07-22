(dev-updating-spack)=

# Updating Shared Spack Environments

This section documents the workflow for updating Polaris' shared Spack
environments and for incrementing the Polaris version (typically the minor
version, and rarely the major version). These updates are required when shared
Spack packages change, which is a more involved process than updating Conda
dependencies.

**Note:** If you are only updating Conda dependencies and bumping the `alpha`
version, follow the instructions in {ref}`dev-updating-conda` instead.

Building Spack dependencies for each compiler and MPI library can take several
hours, so we share Spack environments between developers on supported machines.
As a result, Spack dependencies in Polaris are updated less frequently than
Conda dependencies, since the process is more involved and time-consuming. When
Spack dependencies need to be updated, new versions of these shared
environments must be built and deployed on all supported machines.

Polaris is primarily used by developers, not end users, so releases are not a
major focus of its development cycle. However, version numbers are important
for tracking changes to shared Spack environments. Changes to the major or
minor version number (and, in theory, the patch version) are reserved for
situations where shared Spack packages have changed and a new release of the
shared Spack environments is required. This process requires coordinated
testing and deployment across supported HPC systems.

Athough Polaris shares a lot of its deployment infrastructure with
[E3SM-Unified](https://docs.e3sm.org/e3sm-unified/main/releasing/index.html)
(such as the `mache` package and the E3SM Spack fork), the two packages have
quite distinct workflows for updating version numbers as well as deploying
and testing shared Spack environments. Where E3SM-Unified has rare,
coordinated releases, Polaris' shared Spack environments are updated as
needed to fix bugs or breakages or to support new features.

This guide serves as a roadmap for updating shared Spack environments and
incrementing the Polaris version when Spack dependencies change.

```{toctree}
:maxdepth: 1

workflow
updating_packages
testing/index
adding_new_machines
deploying_shared_spack
maintaining_past_versions
```