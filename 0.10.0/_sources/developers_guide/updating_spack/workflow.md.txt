# Overview of the Workflow

The Polaris workflow for updating shared Spack environments typically follows
this progression:

1. **[Updating Conda Dependencies](../updating_conda.md)**
2. **[Updating Spack Dependencies](updating_packages.md)**
3. **[Deployment and Testing](testing/overview.md)**
4. **[Adding a New Machine](adding_new_machines.md)**
5. **[Deploying the New Versione](deploying_shared_spack.md)**
6. **[Maintaining Past Versions](maintaining_past_versions.md)**

We begin with some background information, then each of these steps is detailed
in its own page. See below for a high-level summary.

---

## Backgraound: How Conda and Spack Work Together in Polaris

Why does Polaris use both Conda and Spack? What roles do they each serve?
Before you start, it's critical to understand how these two systems work
together.

🔗 [Read more](../conda_vs_spack.md)

---

## 1. Updating Conda Dependencies

Frequently, developers need to updating Conda dependencies at the same time
that they are updating shared Spack environments. In such cases, follow the
same process you would if you were just updating Conda dependencies but there
is no need to bump the `alpha` version or make a separate PR for those changes.

🔗 [Read more](../updating_conda.md)

---

## 2. Updating Spack Dependencies

Updates to shared Spack environments typcially occur when Polaris needs to
support new Spack dependencies (e.g. a new MPI-base library or tool) or when
new  versions of existing Spack dependencies are required.  Sometimes, new
shared Spack environments are required because system modules have changed
(particularly if modules currently used by Polaris are no longer available).
This step documents how to propose new Spack dependencies or changes to
existing ones.

🔗 [Read more](updating_packages.md)

---

## 4. Deploying and Testing on HPCs

Before full deployment, new versions of Polaris are installed on a subset of
HPC platforms for iterative testing and validation. This stage often requires
updating updating `mache` to support new systems or changes in machine
configurations, adding package versions to E3SM's Spack fork, and
troubleshooting deployment scripts.

Testing includes everything from basic imports to full workflow runs.

🔗 [Read more](testing/overview.md)

---

## 5. Adding a New Machine

Most of the work for adding a new machine takes place in `mache`. Here we
provide notes on adding new HPCs that are specific to Polaris.

🔗 [Read more](adding_new_machines.md)

---

## 6. Deploying the Shared Spack Environments

Once test deployments have been made and the rquired test suites are passing:

* Deploy across all supported HPC machines
* Merge the version-update PR
* Announce the release to the community

🔗 [Read more](deploying_shared_spack.md)

---

## 7. Maintaining Past Versions

Older versions of Polaris sometimes require maintenance (repairs or deletion).

🔗 [Read more](maintaining_past_versions.md)
