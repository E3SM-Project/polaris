# Getting Started

This page describes how to set up your development environment for adding a
new category of tasks to Polaris.

To begin, check out the Polaris repository and create a new branch from `main`
for developing your new category of tasks. We'll use the simpler approach
described in {ref}`dev-polaris-repo`, but feel free to use the `git worktree`
approach from {ref}`dev-polaris-repo-advanced` if you prefer.

```bash
git clone git@github.com:E3SM-Project/polaris.git add-my-overflow
cd add-my-overflow
git checkout -b add-my-overflow
```

Next, create a conda environment for developing Polaris, as described in
{ref}`dev-conda-env`. We'll assume you're working on a supported machine and
using the default compilers and MPI libraries, but consult the documentation
if you need a custom environment.

```bash
# This may take a while the first time
./configure_polaris_envs.py --conda $HOME/miniforge3 --verbose
```

If you don't already have [miniforge3](https://github.com/conda-forge/miniforge)
installed at the location specified by `--conda`, it will be installed
automatically.

```{note}
If you already have [Miniconda](https://docs.conda.io/en/latest/miniconda.html)
installed, you can use that as well. However, we recommend Miniforge3, as it
comes with important tools and configuration options set up as needed for
Polaris.
```

After setup, you should have a file named `load_dev_polaris_*.sh`, where `*`
depends on your Polaris version, machine, and compilers. For example, on
Chrysalis, you might have `load_dev_polaris_0.1.0-alpha.3_chrysalis_intel_openmpi.sh`:

```bash
source load_dev_polaris_0.1.0-alpha.3_chrysalis_intel_openmpi.sh
```

Now, get the E3SM source code (used by Polaris to build MPAS-Ocean) via the
`E3SM-Project` submodule:

```bash
cd e3sm_submodules/E3SM-Project
git submodule update --init .
cd components/mpas-ocean
git submodule update --init --recursive .
cd ../../../../
```

This will recursively get the submodules needed by MPAS-Ocean.

If your new category of tasks will require changes to E3SM itself, you may
want to create a branch in the E3SM repository as well:

```bash
cd e3sm_submodules/E3SM-Project
git fetch --all -p
git switch -c xylar/mpas-ocean/add-my-overflow origin/master
cd ../..
```

```{note}
E3SM branch names must follow certain conventions. If you are using your
own fork, start the branch name with the component (e.g., `mpas-ocean`). If
you plan to push to the E3SM repo, begin with your GitHub username (e.g.,
`xylar/mpas-ocean/add-overflow`). Use all lowercase, hyphens as
separators, and a descriptive name.
```

If your tasks require running MPAS-Ocean, the recommended workflow is to let
Polaris build automatically when you run `polaris setup` or `polaris suite`
with `--build`.

If you have a strong reason to manage the build yourself, you can still build
the executable manually:

```bash
cd e3sm_submodules/E3SM-Project/components/mpas-ocean/
make ifort
cd ../../../..
```

The `make` target may differ depending on your machine and compilers; see
{ref}`dev-supported-machines` or {ref}`dev-other-machines` for details.

Now you're ready to start developing!

---

← [Back to *Overveiw*](overview.md)

→ [Continue to *Making a New Category of Tasks*](creating_category_of_tasks.md)
