(dev-tutorial-mali-pr-on-perlmutter)=

# Developer Tutorial: Running the `mali_pr` Suite on Perlmutter

This tutorial takes you from no Polaris at all to a finished run of the
{ref}`landice-suite-mali-pr` on Perlmutter.  Along the way, you clone
Polaris, deploy its environment, let Polaris build MALI, and submit the suite
as a batch job.  You can use Perlmutter's CPU nodes (pm-cpu) or its GPU nodes
(pm-gpu); the steps are the same apart from a few names, which are given for
both.

You need:

- a NERSC account in the `e3sm` project (or another project you can charge
  jobs to; see {ref}`tutorial-mali-pr-submit`)
- an SSH key on GitHub that you can use from Perlmutter, since Polaris and
  its submodules are cloned with SSH
- the `bash` shell (see {ref}`dev-shell`)

## Cloning Polaris

Log in to Perlmutter and clone Polaris:

```bash
ssh <username>@perlmutter.nersc.gov
git clone git@github.com:E3SM-Project/polaris.git
cd polaris
git submodule update --init jigsaw-python e3sm_submodules/MALI-Dev
```

Polaris keeps the model source code in submodules under `e3sm_submodules`.
You only need two of them here: `jigsaw-python`, which the deployment builds,
and `MALI-Dev`, the source code for MALI.

## Deploying the Polaris environment

Polaris runs in a [pixi](https://pixi.sh) environment that `./deploy.py`
creates in your clone.  MALI also needs compiled libraries, including Albany
and Trilinos for its first-order velocity solver.  These are in shared Spack
environments on Perlmutter, and `--with-albany` points Polaris to the ones
that have Albany.

For pm-cpu:

```bash
./deploy.py --machine pm-cpu --compiler gnu --with-albany
```

For pm-gpu:

```bash
./deploy.py --machine pm-gpu --compiler gnugpu --with-albany
```

The first deployment takes a while, since it installs pixi and builds the
environment.  Do not add `--deploy-spack`: that rebuilds the Spack
environments rather than using the shared ones, which takes hours.

When it is done, you have a load script in the root of your clone.  Source it
whenever you start a new shell to work with Polaris:

```bash
# pm-cpu
source load_polaris_pm-cpu_gnu_mpich.sh

# pm-gpu
source load_polaris_pm-gpu_gnugpu_mpich.sh
```

{ref}`dev-conda-env` says more about deployment and its options.

## Setting up the suite

Choose a work directory on Perlmutter's scratch file system, where the suite
will be built and run, and set up the suite there:

```bash
# pm-cpu
polaris suite -c landice -t mali_pr -m pm-cpu \
    -w $SCRATCH/polaris_work/mali_pr_pm-cpu

# pm-gpu
polaris suite -c landice -t mali_pr -m pm-gpu \
    -w $SCRATCH/polaris_work/mali_pr_pm-gpu
```

Polaris builds MALI from the `MALI-Dev` submodule before it sets up the
tasks, so this step takes several minutes.  The build goes in
`landice_build` in the work directory, and its log in
`landice_build/build_mali.log`.  When setup finishes, it lists the four tasks
in the suite:

```none
Setting up tasks:
  landice/dome/2km/sia/decomp
  landice/dome/2km/sia/restart
  landice/dome/2km/fo/decomp
  landice/dome/2km/fo/restart
```

Running `polaris suite` again in the same work directory reuses the build.
Add `--build` to rebuild MALI after you change its source code.

(tutorial-mali-pr-submit)=

## Submitting the job

Setup writes a job script, `job_script.mali_pr.sh`, to the work directory.
Submit it:

```bash
cd $SCRATCH/polaris_work/mali_pr_pm-cpu   # or mali_pr_pm-gpu
sbatch job_script.mali_pr.sh
```

The job script charges the `e3sm` project.  To charge another project,
put its name in a config file, for example `my_account.cfg`:

```cfg
[parallel]
account = <project>
```

then add `-f my_account.cfg` to the `polaris suite` command above and
set up the suite again.

The suite runs in a few minutes once the job starts.  You can check on the
job with `squeue --me`.

## Checking the results

The job's output is in `polaris_mali_pr.o<jobid>` in the work directory.  It
ends with a summary of the tasks:

```none
Task Runtimes:
0:00:07 PASS landice/dome/2km/sia/decomp
0:00:02 PASS landice/dome/2km/sia/restart
0:00:12 PASS landice/dome/2km/fo/decomp
0:00:07 PASS landice/dome/2km/fo/restart
Total runtime: 0:00:28
PASS: All passed successfully!
```

Each task's log is in `case_outputs`, and the task's own work directory, such
as `landice/dome/2km/fo/decomp`, has its steps' output.  The job also writes
`mali_pr_output_for_pr.md`, a summary of the run to paste into a pull
request.

## Next steps

- To test a MALI branch of your own, check it out in
  `e3sm_submodules/MALI-Dev`, or point `--branch` at another E3SM checkout,
  and set up the suite with `--build` (see {ref}`dev-landice-build`).
- To compare your results with an earlier run, set up the suite with
  `-b <earlier work directory>` (see {ref}`suites`).
- The {ref}`dev-quick-start` covers the deployment and build options this
  tutorial skipped.
