# Maintaining Past Versions

After we have moved on to new version of Polaris, older versions may still be
in use for months or years older Polaris branches. This page outlines best
practices for keeping past versions available and usable.

---

## 🎯 Goals

* Ensure long-term reproducibility
* Avoid breaking existing workflows
* Minimize overhead for maintainers
* Free up limited disk space when required

---

## 🔒 Avoid Breaking Changes

### Don’t Delete Spack Environments

Shared Polaris Spack environments are isolated by version (and machine,
compiler and MPI version). Do not delete directories like:

```bash
/lcrc/soft/climate/polaris/chrysalis/spack/dev_polaris_soft_0_8_0
/lcrc/soft/climate/polaris/chrysalis/spack/dev_polaris_0_8_0_intel_openmpi
```
These environments may be used by others with older Polaris development
branches.

**Exception**: If the environment is broken beyond repair and cannot be
recreated, it should be removed. If there is no more disk space for software,
the oldest environments must be deleted to make room for new ones. Use your
best judgment and document removals in issues on the Polaris repo.

---

## 🧹 What Can Be Removed

### Test Environments

You can safely delete Spack environments use for test deployment. These were
used only during internal testing and should be removed when they are no longer
needed to free up disk space.  They should be in the maintainers own scratch
space in any case.

You can also delete your own Polaris conda environments whenever you need to
free up space for your own use.

### Intermediate Build Artifacts

Temporary logs or caches (e.g., from failed deployments) can be removed to
save space.

---

## 🔁 Rebuilding Past Versions

If a past version breaks due to:

* OS upgrades
* Module stack changes
* File system reorganizations

...you could consider rebuilding that version. Follow these steps:

1. Checkout the appropriate commit in the Polaris repo (perhaps the release
   tag, e.g. `0.7.0`)
2. Use `configure_polaris_envs.py` as usual, since Polaris will notice the
   older version in `polaris/version.py`:

   ``` bash
   ./configure_polaris_envs.py --conda ~/miniforge3 --recreate --update_spack ...
   ```

You may run into difficulty solving for older conda environments e.g. because
of missing system modules.  At some point, it may simply not be possible to
recreate older Polaris Spack environments because of this.

---

## 💬 Communication

* Coordinate cleanup of old versions via Slack (`#mpas-devops`)
* Use GitHub issues to document version removals or rebuilds

---

Back to: [Deploying the Final Shared Spack Environment](deploying_shared_spack.md)
