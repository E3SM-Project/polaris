# How Conda and Spack Work Together in Polaris

Polaris uses a hybrid approach that combines Conda and Spack to build
and deploy a comprehensive software environment for analysis and diagnostics.
This page explains the motivation for this strategy, how the components
interact, and the shared infrastructure that supports Polaris and related
projects (e.g. [E3SM-Unified](https://docs.e3sm.org/e3sm-unified/main/releasing/release-workflow.html)).

---

## Why Combine Conda and Spack?

Each tool solves a different part of the problem:

### ✅ Conda

* Excellent for managing Python packages and their dependencies
* Supports rapid installation and reproducibility
* Compatible with conda-forge and custom channels
* User-friendly interface, especially for scientists and developers

### ✅ Spack

* Designed for building performance-sensitive HPC software
* Allows fine-grained control over compilers, MPI implementations, and system
  libraries
* Better suited for tools written in Fortran/C/C++ with MPI dependencies

### ❗ The Challenge

Neither system alone is sufficient:

* Conda cannot reliably build or run MPI-based binaries across multiple nodes
  on HPC systems.
* Spack lacks strong support for modern Python environments and is generally
  harder to use for scientists accustomed to Conda-based workflows.

---

## Architecture: How They Work Together

Polaris environments:

1. Use **Conda** to install the core Python tools and lightweight dependencies
2. Rely on **Spack** to build performance-critical tools outside Conda as
   well as libraries required for build E3SM components to be tested in Polaris
3. Are bundled into a single workflow that ensures compatibility across both

System-specific setup scripts ensure both components are activated correctly.

For MPI-based tools:

* The tools are built with Spack using system compilers and MPI
* Users automatically access these builds when running on compute nodes

---

## Shared Infrastructure

Polaris, E3SM-Unified, and Compass all rely on the same key components:

* [`mache`](https://github.com/E3SM-Project/mache): A configuration library
  for detecting machine-specific settings (modules, compilers, paths)
* [E3SM's Spack fork](https://github.com/E3SM-Project/spack): Centralized
  control over package versions and build settings
* Conda: Used consistently to install `mache`, lightweight tools, and Python
  dependencies

This shared foundation ensures reproducibility and consistency across
workflows, testbeds, and developer tools in the E3SM ecosystem.  `mache` also
helps to ensure that libraries used by E3SM components come from the
same system module in Polaris as they do in E3SM.  In cases where libraries
are built with Spack, `mache` ensures that the compilers and MPI libraries
used to build them are the same as will be used to build the components
themselves.

---

## Summary

The hybrid Conda + Spack model in Polaris balances ease of use with HPC
performance. While more complex to maintain, it provides flexibility,
compatibility, and performance across diverse systems. Shared infrastructure
(like `mache` and E3SM's Spack fork) reduces duplication across projects and
streamlines the release process.

---

## Future Alternatives

As complexity grows, other strategies may be worth evaluating:

### Option: **E4S (Extreme-scale Scientific Software Stack)**

* Spack-based stack of curated HPC tools
* E4S environments aim to replace the need for manual Spack+Conda integration
* May offer better long-term sustainability, but lacks Python focus today

🔗 [Explore E4S](https://e4s.io)

### Other Approaches (less suitable currently):

* Pure Spack builds (harder for Python workflows)
* Pure Conda builds (harder for HPC performance tools and likely can't provide
  libraries needed to build E3SM components)
* Containers (portability gains, but complex for HPC integration)

---

## Summary

The hybrid Conda + Spack model in Polaris balances ease of use with HPC
performance. While more complex to maintain, it provides flexibility,
compatibility, and performance across diverse systems. Shared infrastructure
(like `mache` and E3SM's Spack fork) reduces duplication across projects and
streamlines the release process.
