# Deploying the Final Shared Spack Environment

Once all dependencies have been tested and validated, and the new Polaris
version has passed testing across the relevant HPC systems, it is time to
deploy shared Spack environments. This page outlines the process of finalizing
the Polaris version update and notifying the community.

---

## ✅ PR Merge Checklist

Before merging the PR:

* [ ] Final deployments have been completed on all target HPC machines
* [ ] Test suites for each supported E3SM component have passed on all machines

---

## Step-by-Step Finalization

### 1. Tag a Release of the *Previous* Polaris Version

For provenance and to have a citation, we tag the last commit of the previous
Polaris version as the release.

If you want to, you can make a branch to update `polaris/version.py` to
the release version (e.g. `0.8.0`), make a PR and merge it into `main`.  This
is not strictly necessary as no one will use this release version in our
current workflows.

Either way, go to `Releases` on the right on the
[main page](https://github.com/E3SM-Project/polaris) of the repo and
click `Draft a new release` at the top.

Document the changes in this version (or you can use the
`Generate release notes` to generate these automatically, but then please
remove bot PRs for updating pre-commit dependencies).  Here is an
[example](https://github.com/E3SM-Project/polaris/releases/tag/0.7.0).

### 2. Deploy Shared Spack Environments on HPC Systems

Use the same process as during test deployment but you do *not* use the
`--spack` flag to specify a test deployment location.  For example:

```bash
SCRATCH=<path_to_scratch>
CONDA_BASE=~/miniforge3
mdkir -p $SCRATCH/tmp_spack
./configure_polaris_envs.py \
    --conda $CONDA_BASE \
    --update_spack \
    --tmpdir $SCRATCH/tmp_spack \
    --compiler intel intel gnu \
    --mpi openmpi impi openmpi \
    --recreate \
    --verbose
```

This creates a local activation scripts like:

* `load_polaris_dev_<version>_<machine>_<compiler>_<mpi>.sh`

### 3. Announce the Release

Optionally, share the updated version:

* 📣 **Slack** (`#omega` and `#mpas-devops`) with release highlights

Things you may want to include:

* List of supported HPC machines
* Summary of major changes, fixes, and new features

---

## 🔁 Post-Release Maintenance

On each supported machine:

* Remove test spack environments and temp directory
* Delete the `update-to-<version>` branch

---

➡ Next: [Maintaining Past Versions](maintaining_past_versions.md)
