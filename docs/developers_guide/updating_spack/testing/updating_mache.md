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

Afterward, update Polaris to the final release, as described below.

---

## Updating Polaris to a new mache

Polaris pins one version of `mache` in `deploy/pins.cfg`.  Two of
Polaris' files belong to `mache` and must match that version: `deploy.py`
and `deploy/cli_spec.json`.  Never edit them by hand.  Have the new
`mache` regenerate them instead.  The steps work for a release on
conda-forge, such as `5.3.0`, or a release candidate on the `mache_dev`
label, such as `5.3.0rc1`.

1. From the root of your Polaris branch, make a bootstrap environment with
   the new `mache`:

   ```bash
   ./deploy.py --bootstrap-only --mache-version 5.3.0
   ```

2. Follow the instructions it prints:

   ```bash
   pixi shell -m deploy_tmp/bootstrap_pixi/pixi.toml
   mache deploy update --software polaris --mache-version 5.3.0
   exit
   ```

   This replaces `deploy.py` and `deploy/cli_spec.json` with the versions
   from the new `mache`.

3. Set `mache` under `[pixi]` in `deploy/pins.cfg` to the new version.
   Until the pin and `meta.mache_version` in `deploy/cli_spec.json` name
   the same version, `./deploy.py` refuses to run.

4. Update any other dependencies in `deploy/pins.cfg`, `deploy/pixi.toml.j2`
   and `deploy/spack.yaml.j2` (see {ref}`dev-updating-conda` and
   [Updating Spack Dependencies](../updating_packages.md)).

5. `mache deploy update` leaves Polaris' own deployment files alone:
   `deploy/config.yaml.j2`, `deploy/pixi.toml.j2`, `deploy/spack.yaml.j2`,
   `deploy/hooks.py`, `deploy/load.sh` and `deploy/custom_cli_spec.json`.
   Read the `mache` release notes, and make in these files any changes the
   new version asks for.

6. Review the diff, and commit the regenerated files and the new pins
   together.

---

## Testing an unreleased mache

To deploy Polaris with a `mache` branch that has not been released yet,
such as a `mache` PR that fixes a machine's Spack template, pass its fork
and branch to `./deploy.py`:

```bash
./deploy.py --deploy-spack --spack-path <test_spack_path> \
    --compiler <compiler...> --mpi <mpi...> \
    --mache-fork <org>/mache --mache-branch <branch>
```

`./deploy.py` then downloads the bootstrap script from the branch, clones
it, and installs `mache` from the clone into the Polaris environment.  It
skips the check that the pin matches `deploy/cli_spec.json`, so you can
test a branch before updating Polaris to it.  If the branch changes
`deploy.py` or `deploy/cli_spec.json`, regenerate them from the branch
first, as above but with `--mache-fork` and `--mache-branch` in place of
`--mache-version`.  Leave `--mache-version` off `mache deploy update` too,
so it uses the version of the `mache` it was installed with.

Use a `mache` branch only for test deployments.  Release `mache`, then
update Polaris to the release as above, before deploying the shared Spack
environments.  The Polaris version update testing utility takes the same
flags ({ref}`dev-polaris-update-testing`).

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
