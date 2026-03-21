# Deploying Spack Environments on HPCs

Once you have updated Spack dependencies and bumped the Polaris version, you
must deploy and test the new environments on supported HPC systems. This
ensures compatibility with system modules and successful builds of E3SM
components.

This page outlines the deployment workflow, key files, command-line flags, and
best practices for deploying and validating Spack environments in Polaris.

---

## Deployment Workflow

Deployment is managed via `./deploy.py` (backed by `mache.deploy`) and associated
infrastructure. The process is typically:

1. **Update configuration files**:
   - Set the target version in `polaris/version.py`
    - Update package pins in `deploy/pins.cfg`
    - Update Spack specs in `deploy/spack.yaml.j2` if package specs changed
   - Update machine configs in `polaris/machines/` as needed

2. **Test the build** on one or more HPC machines:

   ```bash
   SCRATCH=<path_to_scratch>
   mkdir -p $SCRATCH/tmp_spack
   ./deploy.py --deploy-spack --spack-path $SCRATCH/test_spack \
       --compiler intel intel gnu --mpi openmpi impi openmpi --recreate
   ```

    *Adjust `--compiler` and `--mpi` as needed for your machine and test matrix.*

   *You may want to use `screen` or `tmux` and pipe output to a log file:*
   ```bash
    ./deploy.py ... 2>&1 | tee deploy.log
   ```

3. **Check output** and validate:
   - Spack built the expected packages
    - Pixi environment was created and activated
   - Activation scripts were generated and symlinked correctly
   - Permissions have been updated successfully

4. **Test E3SM component builds and workflows** using the new environment

5. **Deploy more broadly** once core systems pass testing

---

## Key Deployment Components

- **`deploy.py`**: Main entry point for deploying Polaris environments.
  Handles pixi deployment and optional Spack deployment through `mache.deploy`.
- **`deploy/pins.cfg`**: Pin versions for pixi and Spack packages.
- **`deploy/config.yaml.j2`**: Deployment behavior and machine/runtime
  settings consumed by `mache.deploy`.
- **`deploy/spack.yaml.j2`**: Jinja2 template for Spack specs.
- **`deploy/hooks.py`**: Polaris-specific deployment hooks used by
  `mache.deploy`.
- **Mache deploy docs**: authoritative behavior and option details:
  <https://docs.e3sm.org/mache/main/users_guide/deploy.html>

---

## Common Command-Line Flags

- `--deploy-spack`: Build or rebuild Spack environments.
- `--spack-path <path>`: Path to Spack checkout used for deployment/testing.
- `--compiler <compiler(s)>`: Specify compiler(s) to build for.
- `--mpi <mpi(s)>`: Specify MPI library/libraries.
- `--recreate`: Recreate environments even if they exist.
- `--mache-fork` and `--mache-branch`: Use a specific fork/branch of `mache`
  (for co-development/testing).

See `./deploy.py --help` for the full list.

If needed, set Spack temporary build location with `spack.tmpdir` in
`deploy/config.yaml.j2`.

---

## Notes and Best Practices

- Use a unique Spack install location for testing (`--spack-path`).
- Use a scratch or group directory for Spack's temporary build files.
- Set `spack.tmpdir` in `deploy/config.yaml.j2` if you need to control
  temporary build location.
- Only deploy shared Spack environments after thorough testing.
- Check `albany_supported.txt` and `petsc_supported.txt` for supported
  machine/compiler/MPI combos.
- For troubleshooting, see [Troubleshooting Deployment](troubleshooting.md).

---

➡ Next: [Troubleshooting Deployment](troubleshooting.md)
