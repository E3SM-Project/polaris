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

`deploy.py` and `deploy/cli_spec.json` belong to `mache`.  Don't edit them
by hand.  To move to a new `mache`, regenerate them and update the pin, as
described in
[Updating Polaris to a new mache](updating_spack/testing/updating_mache.md#updating-polaris-to-a-new-mache).

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

(dev-dependency-branch)=

## Testing a Dependency from a Branch

To test a branch of one of polaris' python dependencies, such as
`geometric_features`, `mpas_tools` or `mosaic`, before it is released, deploy
polaris as usual and then install the branch into the polaris environment:

```bash
source load_polaris_<machine>_<compiler>_<mpi>.sh
git clone -b <branch> git@github.com:<org>/<repo>.git <path>
python -m pip install --no-deps --no-build-isolation -e <path>
```

For `mpas_tools`, install `<path>/conda_package` instead.  Only the python
package comes from the branch; the compiled tools that come with `mpas_tools`
stay those of the release.

Since the install is editable, pulling new commits to the branch is enough to
pick them up.  Rerunning `./deploy.py` puts the release back, so repeat the
`pip install` after each deployment.

`geometric_features` needs one more step.  The load script points
`GEOMETRIC_DATA_DIR` at the data that came with the release, so features that
the branch adds or changes are missing (they fail to download with a 404
error).  After each time you source the load script, run:

```bash
export GEOMETRIC_DATA_DIR=<path>/geometric_data
```

Job scripts source the load script themselves, so add the same line to a job
script just after its `source load_polaris_env.sh`.

## Notes

- Miniforge/Micromamba/Miniconda are no longer required for deployment.
- `./deploy.py` can install pixi when needed.
- For machine-specific Spack updates, coordinate with maintainers via the
  process described in {ref}`dev-updating-spack`.
