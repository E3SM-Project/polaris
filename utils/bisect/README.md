# Using the bisect utility

The `utils/bisect` directory contains a small wrapper around `git bisect` that
automates building and running one or more Polaris test cases across a range
of E3SM commits. It is intended to answer questions of the form:

> *"What is the first E3SM commit where this Polaris test (or suite) begins
> to fail or change its answers?"*

The workflow has two pieces:

- `bisect.py`: a driver that initializes `git bisect` and calls
   `git bisect run .../bisect_step.py`.
- `bisect_step.py`: a single "step" of the bisection that builds E3SM and runs
   the requested Polaris test(s) at a given commit and reports **success** or
   **failure** back to `git bisect`.

Both scripts are configured through an INI-style config file, typically called
`bisect.cfg`, based on `utils/bisect/example.cfg`.

## Quick start

1. Copy the example config to the root of the Polaris branch where you want to
    launch the bisect (this is also where you will run `bisect.py`):

    ```bash
    cp utils/bisect/example.cfg bisect.cfg
    ```

2. Edit `bisect.cfg` (see [Configuration options](#configuration-options)) to
    set:

    - `good` and `bad` commit hashes or tags in the E3SM repo.
    - Paths for `e3sm_path`, `work_base`, and `load_script`.
    - The `setup_command` and `run_command` for your Polaris test(s).

3. On a compute node (interactive or batch), from the root of the Polaris
    branch containing `bisect.cfg`, run:

    ```bash
    ./utils/bisect/bisect.py -f bisect.cfg
    ```

    The script will print the `git bisect` commands it is running and then
    iterate over commits until the first "bad" commit is found.

4. When `git bisect` finishes, it will print the first bad commit and reset
    the E3SM repository back to its original state.

## Configuration options

The config file is a standard `configparser` INI file with a single
`[bisect]` section. The `example.cfg` file documents each option, but the most
important ones are summarized here:

- `good`: hash or tag for a **passing** E3SM commit.
- `bad`: hash or tag for a **failing** E3SM commit.
- `first_parent` (bool): if `True`, `git bisect` follows only the first parent
   of merge commits, which is often what you want when bisecting along a main
   development branch.
- `e3sm_path`: path to the E3SM checkout that will be bisected.
   - This can point to `e3sm_submodules/E3SM-Project`, `e3sm_submodules/Omega`,
      or another clone.
   - The build process will initialize the submodules if required.
- `work_base`: base directory for all builds and runs. For each commit hash
   `<hash>` the bisect step creates:
   - `build_hash_<hash>`: build directory used when configuring and building
      E3SM for that commit.
   - `e3sm_hash_<hash>`: work/run directory where Polaris is executed and where
      logs and outputs for that commit live.
- `load_script`: shell script used to activate the Polaris environment and set
   any required environment variables (compilers, MPI, etc.). This is sourced
   at the beginning of each step.
- `setup_command`: command to set up the desired Polaris tasks or suites.
   `bisect_step.py` automatically appends the appropriate `-p`, `--branch`, and
   `-w` options, so they should **not** appear in the config file.
   `--clean_build` is also appended so neither `--build` nor `--clean_build`
   should appear in `setup_command`.
- `run_command`: command used to run the Polaris tasks inside the work
    directory.  The command is typically `polaris serial` but it could be
    useful to add a timeout, e.g. `timeout 5m polaris serial` if the "bad" runs
    are hanging.

## Directory layout and outputs

For each commit tested, `bisect_step.py` does roughly the following:

1. Determine the current short commit hash using `git rev-parse --short HEAD`.
2. Define directories under `work_base`:

    - Build directory: `build_hash_<hash>`
    - Work/run directory: `e3sm_hash_<hash>`

3. Source the load script, reset the E3SM tree to a clean state, configure and
    build, then run Polaris in the work directory.

As a result, after a bisect session you will typically see a tree like:

```text
<work_base>/
   build_hash_44814ae/
   build_hash_7b87d1f/
   ...
   e3sm_hash_44814ae/
      case_outputs/
      custom.pickle
      job_script.custom.sh
      load_polaris_env.sh
      ...
      polaris_custom.o45750050

      ... (other test outputs)
   e3sm_hash_7b87d1f/
      ...
```

The exact filenames within each `e3sm_hash_<hash>` directory depend on the
Polaris test case(s), but you can always:

- Inspect build logs under `build_hash_<hash>` (e.g., `CMake` or `make`
   outputs if you direct them there from the setup command).
- Inspect run logs and Polaris outputs under `e3sm_hash_<hash>` (e.g.
   `polaris_<suite>.o<jobid>` and the task logs in `case_outputs`).

## Typical console output

When you run `bisect.py`, you will see a summary of the commands being
executed, for example:

```text
------------------------------------------------------------------------
Bisect Initialization
------------------------------------------------------------------------

Running:
   cd /path/to/E3SM-Project
   git bisect start --first-parent
   git bisect good 44814ae
   git bisect bad 7b87d1f
   git bisect run /path/to/polaris/utils/bisect/bisect_step.py -f /path/to/polaris/bisect.cfg
```

For each commit, `git bisect run` calls `bisect_step.py`, which prints a
"Bisect Step" banner and the full command sequence it is about to run, for
example:

```text
------------------------------------------------------------------------
Bisect Step
------------------------------------------------------------------------

Running:
   source /path/to/load_polaris_bisect_*.sh
   cd /path/to/E3SM-Project
   rm -rf *
   git reset --hard HEAD
   polaris setup -n 39 -b /path/to/baseline -p /path/to/work_base/build_hash_44814ae --clean_build --branch /path/to/E3SM-Project -w /path/to/work_base/e3sm_hash_44814ae
   cd /path/to/work_base/e3sm_hash_44814ae
   polaris serial
```

If the build and run succeed (exit code 0), the commit is treated as
**good**. A non-zero exit code (e.g., build failure, test failure, timeout)
marks the commit as **bad** for the purposes of `git bisect`.

When the bisection completes, `git bisect` prints a summary such as:

```text
<hash> is the first bad commit
```

It then resets the E3SM repository so it is no longer in a `bisect` state.

## Notes and best practices

- Since the code is built and run on a compute node, any baseline you use for
   comparison (e.g., for non-bit-for-bit checks) should also be built on a
   compute node. Otherwise, you may see differences purely due to where the
   code was compiled.
- The bisect process can be expensive (many builds and runs). Consider using
   a dedicated scratch directory for `work_base` with enough quota and
   performance.
- You can test your configuration for a single commit by running
   `bisect_step.py` directly (outside of `git bisect`) on a known good or bad
   commit to make sure the environment and commands are correct before
   launching a full bisect.
