(dev-updating-conda)=

# Updating Conda Dependencies

## 🏷️ Polaris Versioning Scheme

Polaris is primarily a developer-focused project and is in a perpetual "alpha"
stage. Versions in the `main` branch always end with `-alpha.<N>`.
Occasionally, releases are tagged without the `-alpha.<N>` for documentation
and provenance.

The `alpha` version is incremented each time Polaris' Conda dependencies
change. This signals to developers and deployment infrastructure that
environments created with an older alpha version may not be compatible with
the new code.

## 🔄 Workflow for Dependency Changes

When Conda dependencies are updated (added or version-bumped), the `alpha`
version must also be incremented. This ensures developers know when their
Conda environments are out of date and need to be recreated or updated.

Each time a developer sources a Polaris load script (see {ref}`dev-conda-env`),
the script checks that the Polaris version (including `alpha`) matches the one
used to create the Conda environment. If not, an error message prompts the
developer to update or recreate the environment.

Unless Spack dependencies are also changed (in which case you need to follow
the workflow in {ref}`dev-updating-spack`), there is no need to deploy shared
Spack environments—just update Conda dependencies, bump the `alpha` version,
make a pull request, and merge.

---

## ⬆️ Bump the `alpha` version

Unless you are updating share Spack environments, you need to start by
updating the Polaris version to the next `alpha` number in `polaris/version.py`
and committing the change.  For example, change:
``` python
__version__ = '0.8.0-alpha.9'
```
to
``` python
__version__ = '0.8.0-alpha.10'
```
and commit this with a message like, "Update Polaris to v0.8.0-alpha.10".

---

## ✍️ Updating dependencies

There are two places you might need to make the changes to the dependencies,
depending on the package(s) involved.

### `conda-dev-spec.template`

The [Jinja template](https://jinja.palletsprojects.com/en/stable/) that defines
Polaris' Conda environments is
[`deploy/conda-dev-spec.template`](https://github.com/E3SM-Project/polaris/blob/main/deploy/conda-dev-spec.template).
This file is the easiest place to add new Conda dependencies.  It is the right
place to add dependencies that you do not plan to pin to a specific version
and which will not also be installed in a shared Spack environment.

Add your new dependency in the appropriate location:
- `# Base` - runtime Polaris dependencies not associated with development
- `# Static typing` - dependencies for Python type checking
- `# Linting and testing` - tools for linthing the code and running simple
  unit tests
- `# Development` - other development requirements like MPI, CMake and
  compilers, typically only used on unsupported machines such as laptops
- `# CF-compliance` - tools that are handy for checking
  [CF compliance](https://cfconventions.org/).
- `# Documentation` - tools for building the documentation
- `# Visualization` - tools for quick visualization, not directly required
  by any Polaris tasks or steps

### `default.cfg`

Several Conda packages have fixed versions defined in `deploy/default.cfg`.
Currently, these are:

```cfg
python = 3.13

# versions of conda packages
geometric_features = 1.6.1
mache = 1.31.0
conda_moab = 5.5.1
mpas_tools = 1.2.0
otps = 2021.10
parallelio = 2.6.6
```

We choose to define these "pinned" versions in the config file so that
developers can override them with their own config file (which might be
convenient for testing) and so that we can easily reference these versions in
multiple places during the deployment workflow if needed.

**Note:** We treat the MOAB package as a special case with different versions
from conda-forge (`conda_moab`) and Spack (`spack_moab`).  This is because
MOAB has infrequent releases and we currently need features and bug fixes for
many Polaris workflows that are only available from the `master` branch.
Since the `master` version is not available on conda-forge, we fall back on
the latest release for use on login nodes and unsupported machines.

Some versions defined in `default.cfg` apply to both Conda and Spack package:

```cfg
# versions of conda or spack packages (depending on machine type)
esmf = 8.8.1
metis = 5.1.0
netcdf_c = 4.9.2
netcdf_fortran = 4.6.2
pnetcdf = 1.14.0
```
If those get updated, you will probably need to deploy new shared Spack
environments, meaning you will need to follow the full
[Spack Deployment Workflow](updating_spack/workflow.md).
