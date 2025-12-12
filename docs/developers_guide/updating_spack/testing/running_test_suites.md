# Running Required Test Suites

After deploying a new or updated Spack environment, you must validate it by
running the required test suite(s) for each supported machine, compiler, and
MPI variant. This ensures that core E3SM components build and run correctly in
the new environment.

---

## MPAS-Ocean: Running the `pr` Suite

For each machine, compiler, and MPI combination (for example, on Chrysalis
with Intel and OpenMPI):

1. **Start a Clean Environment**

   Open a fresh terminal or run `bash` to ensure a clean shell environment.

2. **Source the Load Script**

   ```bash
   source load_polaris_dev_0.3.0-alpha.1_chrysalis_intel_openmpi.sh
   ```

   *(Replace `chrysalis`, `intel`, and `openmpi` with your machine, compiler,
   and MPI as appropriate. See {ref}`dev-mpas-supported-machines`.)*

3. **Set Up (and Auto-Build) the Suite**

   Let Polaris make a clean build of MPAS-Ocean for you with `--clean_build`
   and `--model mpas-ocean`:

   ```bash
   polaris suite -c ocean -t pr --clean_build --model mpas-ocean\
       -w /path/to/polaris_scratch/mpaso_pr_intel_openmpi
   ```

   Notes:
   - By default, Polaris builds into the `build` subdirectory of the suite
     work directory supplied with `-w` and generates a build
     script in this directory (see {ref}`dev-build`).
   - Using the`--branch` flag is not recommended so that the Omega submodule
     in your Polaris tree is used, and required submodules are checked out
     automatically.
   - You can pass extra make flags via `--cmake_flags` (e.g.,
     `--cmake_flags "-j 8"`).

4. **Run the Suite**

   ```bash
   cd /path/to/polaris_scratch/mpaso_pr_intel_openmpi
   sbatch job_script_pr.sh
   ```

5. **Check Results**

   Wait for the job to complete. If all tests pass, check the box for this
   configuration in your PR. If not, file an issue (in the Polaris repo), note
   the problem, and link to the issue next to the (unchecked) checkbox in the
   PR description.

---

## Omega: Running CTests and `omega_pr` Suite

For each machine, compiler, and MPI combination (for example, on Chrysalis
with Intel and OpenMPI):

1. **Start a Clean Environment**

   Open a fresh terminal or run `bash` to ensure a clean shell environment.

2. **Source the Load Script**

   ```bash
   source load_polaris_dev_0.3.0-alpha.1_chrysalis_intel_openmpi.sh
   ```

   *(Replace as appropriate for your configuration.)*

3. **Run Omega CTests**

   ```bash
   ./utils/omega/ctest/omega_ctest.py -c -s -o e3sm_submodules/Omega
   ```

4. **Check CTest Results**

   Wait for the tests to complete. If all tests pass, check the box for this
   configuration in your PR. If not, file an issue (in the Polaris or Omega
   repo), note the problem, and link to the issue next to the (unchecked)
   checkbox in the PR description.

5. **Set Up (and Auto-Build) the Suite**

    Omega will have already been built by the CTest utility in
    `build_omega/build_<machine>_<compiler>` under your Polaris branch (see
    {ref}`dev-build`).  To reuse that build when setting up the `omega_pr`
    suite, point `--component_path` at this directory, for example:

    ```bash
    polaris suite -c ocean -t omega_pr --model omega \
          -w /path/to/polaris_scratch/omega_pr_intel_openmpi \
          -p /path/to/polaris_branch/build_omega/build_<machine>_<compiler>
    ```

    If you omit `-p` and instead pass `--build`, Polaris will build Omega into
    the `build` subdirectory of the suite work directory (supplied with `-w`).

    Notes:
    - Using the`--branch` flag is not recommended so that the Omega submodule
      in your Polaris tree is used, and required submodules are checked out
      automatically.
    - You can pass extra CMake flags via `--cmake_flags`.

6. **Run the Suite**

   ```bash
   cd /path/to/polaris_scratch/omega_pr_intel_openmpi
   sbatch job_script_omega_pr.sh
   ```

7. **Check Results**

   Wait for the job to complete. If all tests pass, check the box for this
   configuration in your PR. If not, file an issue (in the Polaris repo), note
   the problem, and link to the issue next to the (unchecked) checkbox in the
   PR description.

---

## Notes

- Always use a clean environment to avoid contamination from previous runs.
- Use the correct load script for the machine, compiler, and MPI variant being
  tested.
- For each configuration, document the outcome in the PR checklist, linking
  to issues as needed.

---

**Tip:**
If you are testing on a different machine or with a different compiler/MPI,
simply substitute the appropriate names in the examples above. For a full list
of supported combinations and the correct make targets, see the tables in
{ref}`dev-mpas-supported-machines` and {ref}`dev-omega-supported-machines`.
