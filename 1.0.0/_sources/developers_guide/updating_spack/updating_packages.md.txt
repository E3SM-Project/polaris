# Updating Spack Dependencies

Updating shared Spack dependencies in Polaris is part of the release workflow
for supported machines. Compared with pixi dependency updates, Spack updates
are heavier-weight because environments are shared and build times are often
long.

Polaris now uses `./deploy.py` backed by `mache.deploy`. For deployment
behavior and templates, treat the mache docs as the source of truth:

- [mache deploy user guide](https://docs.e3sm.org/mache/main/users_guide/deploy.html)
- [mache deploy developer guide](https://docs.e3sm.org/mache/main/developers_guide/deploy.html)

## Workflow for Spack Dependency Changes

1. **Create a version-update branch**

   Use a branch like `update-to-<version>` (for example
   `update-to-0.9.0-alpha.1`).

2. **Bump the Polaris version**

   Update `polaris/version.py` to the target version and commit that change.

3. **Update deployment inputs**

   - Update pinned versions in `deploy/pins.cfg`:
     - `[spack]` for Spack-only pins
     - `[all]` for pins shared by pixi and Spack
   - Update Spack specs in `deploy/spack.yaml.j2` as needed
   - Update deployment defaults/behavior in `deploy/config.yaml.j2` only if
     deployment logic or paths need to change

4. **Open a PR and track testing/deployment**

   Include:
   - an **Updates** section listing changed versions and rationale
   - a **Testing** checklist by machine/compiler/MPI
   - a **Deployment** checklist for final shared deployment

5. **Run test deployments before shared deployment**

   Example:

   ```bash
   ./deploy.py --deploy-spack --spack-path <test_spack_path> \
       --compiler <compiler...> --mpi <mpi...> --recreate
   ```

6. **Run required validation suites**

   Follow the testing pages under `updating_spack/testing/` before final
   deployment.

## Adding a New Spack Package

To add a new package to Polaris Spack environments:

1. Add or update the package pin in `deploy/pins.cfg` (`[spack]` or `[all]`).
2. Add the corresponding spec in `deploy/spack.yaml.j2` under `library` and/or
   `software`, whichever is appropriate.
3. If inclusion should be conditional, express that condition in Jinja2
   template logic and document it in your PR.
4. Test on supported machine/compiler/MPI combinations.

## Summary

- Update version and deployment inputs (`deploy/pins.cfg`, `deploy/spack.yaml.j2`).
- Validate with `./deploy.py` test deployments.
- Coordinate final shared Spack deployment only after testing passes.

If deployment (pixi) dependencies also changed, follow
[Updating Deployment Dependencies](../updating_conda.md).
