# Deploying Spack Environments on HPCs

Once you have updated Spack dependencies and bumped the Polaris version, you
must deploy and test the new environments on supported HPC systems. This
ensures compatibility with system modules and successful builds of E3SM
components.

This page outlines the deployment workflow, key files, command-line flags, and
best practices for deploying and validating Spack environments in Polaris.

---

## Deployment Workflow

Deployment is managed via the `configure_polaris_envs.py` script and associated
infrastructure. The process is typically:

1. **Update configuration files**:
   - Set the target version in `polaris/version.py`
   - Update Spack and Conda package versions in `deploy/default.cfg`
   - Update machine configs in `polaris/machines/` as needed

2. **Test the build** on one or more HPC machines:

   ```bash
   SCRATCH=<path_to_scratch>
   CONDA_BASE=~/miniforge3
   mdkir -p $SCRATCH/tmp_spack
   ./configure_polaris_envs.py \
       --conda $CONDA_BASE \
       --update_spack \
       --spack $SCRATCH/test_spack \
       --tmpdir $SCRATCH/tmp_spack \
       --compiler intel intel gnu \
       --mpi openmpi impi openmpi \
       --recreate \
       --verbose
   ```

  *Adjust `--compiler` and `--mpi` as needed for your machine and test matrix.*

   *You may want to use `screen` or `tmux` and pipe output to a log file:*
   ```bash
   ./configure_polaris_envs.py ... 2>&1 | tee deploy.log
   ```

3. **Check output** and validate:
   - Spack built the expected packages
   - Conda environment was created and activated
   - Activation scripts were generated and symlinked correctly
   - Permissions have been updated successfully

4. **Test E3SM component builds and workflows** using the new environment

5. **Deploy more broadly** once core systems pass testing

---

## Key Deployment Components

- **`configure_polaris_envs.py`**: Main entry point for deploying Polaris
  environments. Handles both Conda and Spack setup.
- **`deploy/default.cfg`**: Specifies package versions and deployment options.
- **`deploy/shared.py`**: Shared logic for deployment scripts.
- **`deploy/bootstrap.py`**: Handles environment creation and Spack builds
  after the bootstrap environment is set up.
- **Templates**: Jinja2 templates in `deploy/` and `deploy/spack/` for
  environment specs and activation scripts.

---

## Common Command-Line Flags

- `--conda <path>`: Path to your Miniforge3 installation (required).
- `--update_spack`: Build or rebuild the Spack environment.
- `--spack <path>`: Path to install Spack environments (for testing).
- `--tmpdir <path>`: Temporary directory for Spack builds (recommended).
- `--compiler <compiler(s)>`: Specify compiler(s) to build for.
- `--mpi <mpi(s)>`: Specify MPI library/libraries.
- `--with_albany`: Include Albany in the Spack environment
  (see `albany_supported.txt` for supported combos).
- `--with_petsc`: Include PETSc and Netlib LAPACK (see `petsc_supported.txt`).
- `--recreate`: Recreate environments even if they exist.
- `--mache_fork` and `--mache_branch`: Use a specific fork/branch of `mache`
  (for co-development/testing).
- `--verbose`: Print all output to the terminal.

See `./configure_polaris_envs.py --help` for the full list.

---

## Notes and Best Practices

- Use your own Miniforge3 installation (not Miniconda or a shared install).
- Use a unique Spack install location for testing (`--spack`).
- Use a scratch or group directory for Spack's temporary build files
  (`--tmpdir`).
- Only deploy shared Spack environments after thorough testing.
- Check `albany_supported.txt` and `petsc_supported.txt` for supported
  machine/compiler/MPI combos.
- For troubleshooting, see [Troubleshooting Deployment](troubleshooting.md).

---

➡ Next: [Troubleshooting Deployment](troubleshooting.md)
