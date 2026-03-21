# Updating `mache` for Polaris

`mache` is the configuration library used by Polaris (and related
projects like E3SM-Unified and Compass) to determine machine-specific settings,
including module environments and Spack configurations.

During each Polaris release, it is often necessary to:

* Add support for new machines
* Update Spack environment templates for existing systems
* Create release candidates and final versions of `mache`

This page outlines the steps for maintaining and updating `mache` during the
release process.

---

## Repo Location

🔗 [https://github.com/E3SM-Project/mache](https://github.com/E3SM-Project/mache)

---

## When to Update `mache`

You should update `mache` when:

* A supported machine has changed modules or compilers
* New machines are being targeted for deployment
* Spack YAML templates fall out of sync with system configurations
* You need to test new combinations of compiler + MPI + module environments

Each change should be tested by deploying a release candidate of Polaris.

---

## Key Tasks

### 1. Update config options

Each HPC machine supported by Polaris has a
[config file in `mache`](https://github.com/E3SM-Project/mache/tree/main/mache/machines).

These config options control the default deployment behavior, including the
Unix `group` that the environment will belong to, the
`compiler` and `mpi` library used to build Spack packages by
default, the `base_path` under which the conda and spack environments as well
as the activation scripts will be installed, and whether that machine will
use E3SM's version of `hdf5`, `netcdf-c`, `netcdf-fortran`, `parallel-netcdf`,
etc. or install them from Spack.

### 2. Edit Spack Templates

Spack environment templates live in:

```
mache/spack/templates/<machine>_<compiler>_<mpi>.yaml
```

Edit these files to reflect updated system modules or new toolchains.
If adding a new machine, copy an existing `yaml` file to use as a template.

Use the utility script to assist:
🔗 [utils/update_cime_machine_config.py README](https://github.com/E3SM-Project/mache/blob/main/utils/README.md)

---

### 3. Create a Release Candidate

Use the typical GitHub flow:

```bash
git checkout -b update-to-1.32.0
# Make changes
# Push branch and open PR
```

Once the PR is reviewed and merged:

* Tag a release candidate (e.g., `1.32.0rc1`)
* Publish it to conda-forge under `mache_dev` (by merging a PR that targets
  the `dev` branch)

This RC will be referenced in the Polaris build process.

---

### 4. Finalize the Release

Once testing across all platforms is complete:

* Create a final version tag (e.g., `1.32.0`)
* Always use [semantic versioning](https://semver.org/)
* Submit a PR to `mache-feedstock` to update the recipe (this time targeting
  the `main` branch)
* Merge once CI passes

Afterward, update any references to the RC version in the Polaris repo to
point to the final release.

---

## Best Practices

* Be liberal in what system tools (`tar`, `CMake`, etc.) are defined as
  `buildable: false` in Spack environments.
* Regularly sync templates with actual E3SM production configurations
* Validate changes via test deployments of Polaris before tagging final versions.
* New mache releases will need to be made as needed by any of the
  **downstream** repos — currently Polaris, E3SM-Unified, and Compass.

---

➡ Next: [Deploying Spack Environment](deploying_spack.md)
