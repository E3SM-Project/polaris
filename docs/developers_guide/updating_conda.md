(dev-updating-conda)=

# Updating Deployment Dependencies

Polaris now deploys environments through `./deploy.py` and `mache.deploy`.
This means dependency updates are handled through deployment templates and
configuration, not through the old standalone conda setup workflow.

## Where to Update Dependencies

Most dependency updates should be made in deployment templates under `deploy/`:

- `deploy/pixi.toml.j2` for pixi-managed packages
- `deploy/spack.yaml.j2` for Spack package specs
- `deploy/config.yaml.j2` for deployment options and defaults
- `deploy/pins.cfg` for pinned mache/python versions used by `deploy.py`

For background on how these files are rendered and used, see:

- [mache deploy user guide](https://docs.e3sm.org/mache/main/users_guide/deploy.html)
- [mache deploy developer guide](https://docs.e3sm.org/mache/main/developers_guide/deploy.html)

## Recommended Workflow

1. Update the relevant template(s) in `deploy/`.
2. If dependency behavior changes, bump `polaris/version.py` as appropriate.
3. Re-run deployment locally to validate:

   ```bash
   ./deploy.py --recreate
   ```

4. If Spack dependencies changed, test with:

   ```bash
   ./deploy.py --deploy-spack --recreate
   ```

5. Run required suites/tests for your machine and component.

If Spack dependencies changed in a way that affects shared machine deployments,
follow the full workflow in {ref}`dev-updating-spack`.

## Notes

- Miniforge/Micromamba/Miniconda are no longer required for deployment.
- `./deploy.py` can install pixi when needed.
- For machine-specific Spack updates, coordinate with maintainers via the
  process described in {ref}`dev-updating-spack`.
