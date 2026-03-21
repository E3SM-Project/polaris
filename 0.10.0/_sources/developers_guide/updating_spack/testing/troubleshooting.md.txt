# Troubleshooting Deployment

Even with well-maintained tools, deployment of Polaris on HPC systems
often encounters system-specific or environment-specific problems. This page
outlines common categories of issues and how to diagnose and resolve them.

This is an evolving list.  Please make PRs to add descriptions of issues
you have encountered and solutions you have found.

---

## 1. 🛠️ Spack Build Failures

### Common Causes

* Missing or incompatible system modules (`cmake`, `perl`, `bison`, etc.)
* Outdated Spack package definitions in the `spack_for_mache_<version>`
  branch on the E3SM fork
* Spack build cache pollution
* Environment not set correctly for Spack to detect compilers/libraries

### Solutions

* If Spack is attempting to build common system tools (`cmake`, `tar`, etc.),
  add their system versions to the Spack templates in `mache` with
  `buildable: false` instead to save time and prevent build problems.
* Check with `spack find`, `spack config get compilers`, and
  `spack config get modules`
* Load required modules manually before re-running
* Rebuild: `spack uninstall -y <package>` or delete the full deployment
  directory
* Double-check you are using the correct `spack_for_mache_<version>` branch

---

## 2. 🔢 Activation Script or Module Issues

### Symptoms

* Scripts not found or symlinks broken
* Compute node not detected

### Fixes

* Inspect Jinja2 templates for logic errors (especially for new systems)
* Re-run deployment with `--recreate`
* Validate compute node detection logic (`$SLURM_JOB_ID`, `$COBALT_JOBID`,
  etc.)
* For new schedulers (e.g., PBS), extend template logic accordingly

---

## 3. 🚫 Conda Environment Problems

### Symptoms

* Conda fails to resolve dependencies
* Environments install but are missing key packages

### Fixes

* Run with `--recreate` to force a rebuild
* Inspect logs carefully for root cause messages
* Use troubleshooting scripts to bisect failing specs
* Check for channel mismatches or conflicting dev-label dependencies

---

## 4. 💾 Filesystem and Permission Issues

### Symptoms

* Scripts not executable by collaborators
* Environment directories not group-readable

### Fixes

* Run: `chmod -R g+rx` and `chgrp -R <group>` as needed
* Confirm deployment messages show permission updates succeeded
* Use `ls -l` to inspect group ownership and mode bits
* You may need to coordinate with administrators or previous maintainers to
  set permissions

---

## 5. 🧰 `mache` Configuration Problems

### Symptoms

* Unknown machine error during deployment
* Spack fails to load environment due to incorrect module list

### Fixes

* Ensure the correct `mache` version or branch is being installed
* Ensure that the machine has been added to `mache` both under
  [machine config files](https://github.com/E3SM-Project/mache/tree/main/mache/machines)
  and in the logic for
  [machine discovery](https://github.com/E3SM-Project/mache/blob/main/mache/discover.py)
* Validate updates to `config_machines.xml` and spack YAML templates

---

## 6. 🪖 Spack Caching and Environment Contamination

### Symptoms

* Builds complete but produce incorrect or stale binaries
* Environment behaves inconsistently between deploys

### Fixes

* Clear Spack caches manually if needed
* Always deploy from a clean `$TMPDIR` and fresh clone if unsure
* Delete the entire directory:

  ```bash
  rm -rf <spack_env_dir>
  ```

---

## 7. ⚠️ Common Fix: Full Clean + Re-run

When in doubt, remove and rebuild everything:

```bash
rm -rf <spack_env_dir>
./configure_polaris_envs.py --conda ~/miniforge3 --recreate
```

This often resolves cases where previous state is interfering with a clean
build.

---

## 📎 Related Tools & Tips

* Use `screen`, `tmux`, or `nohup` for long deployments
* Always log output: `... 2>&1 | tee deploy.log`
* Validate final symlinks and paths manually after deployment
* Document which system + compiler + MPI variants have been tested

---

Back to: [Deploying Spack Environments on HPCs](deploying_spack.md)
