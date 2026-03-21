# Overview of Deployment and Testing

This section documents the full testing and deployment process for Polaris,
including how to:

* Update the E3SM Spack fork to support new versions
* Maintain and release new versions of `mache` for system-specific Spack
  configurations
* Perform test and final shared deployments of Polaris on supported HPC
  platforms
* Identify and resolve deployment issues

---

## Phased Deployment Strategy

Testing typically begins with a **partial deployment** of the new Polaris
version on a few key HPC systems. Once core functionality and package
compatibility are verified, a **full deployment** to all supported machines is
performed.

The process may require some iteration if major changes to dependencies
or the deployment infrastructure are required during troubleshooting.

---

## Key Components of the Deployment Process

The following steps and infrastructure are used when testing and deploying a
new release:

### 🛠️ [Updating the E3SM Spack Fork](updating_spack_fork.md)

* Add new versions of performance-critical tools (e.g., ESMF, MOAB)
* Create `spack_for_mache_<version>` branches for use in `mache`

### 🧩 [Updating `mache`](updating_mache.md)

* Keep system-specific Spack environment templates in sync with E3SM module
  stacks
* Create RC and final releases of `mache`
* Use `utils/update_cime_machine_config.py` to streamline updates

### 🚀 [Deploying Spack Environments on HPCs](deploying_spack.md)

* Use the `configure_polaris_envs.py` script and template infrastructure
* Build environments and activation scripts tailored to each system

### ✅ [Running Required Test Suites](running_test_suites.md)

* Describes how to validate new environments by running required test suites
  for each supported machine, compiler, and MPI variant
* Provides step-by-step instructions for MPAS-Ocean (`pr` suite) and Omega
  (CTest) validation
* Explains how to document results and handle failures in the PR checklist

### 🧪 [Troubleshooting Deployment Issues](troubleshooting.md)

* Resolve Spack build failures and MPI/compiler mismatches
* Address problems with activation, modules, or symbolic links
* Common pitfalls in configuration

---

## Audience

This section is primarily intended for Polaris maintainers and release
engineers. Familiarity with Spack, Conda, and HPC system environments is
assumed.

➡ Start with: [Updating the E3SM Spack Fork](updating_spack_fork.md)
