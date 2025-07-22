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
   and MPI as appropriate. See the table in
   {ref}`dev-mpas-supported-machines`.)*

3. **Create a Worktree for E3SM**

   ```bash
   cd e3sm_submodules/E3SM-Project
   git worktree add ../e3sm_chrysalis_intel_openmpi
   cd ../e3sm_chrysalis_intel_openmpi/components/mpas-ocean
   git submodule update --init --recursive .
   ```

4. **Build MPAS-Ocean**

   ```bash
   make ifort
   ```
   *(Use the correct make target for your machine and compiler. See the table
   in {ref}`dev-mpas-supported-machines`.)*

5. **Set Up and Run the Test Suite**

   ```bash
   polaris suite -c ocean -t pr -p . -w /path/to/polaris_scratch/pr_intel_openmpi
   cd /path/to/polaris_scratch/pr_intel_openmpi
   sbatch job_script_pr.sh
   ```

6. **Check Results**

   Wait for the job to complete. If all tests pass, check the box for this
   configuration in your PR. If not, file an issue (in the Polaris repo), note
   the problem, and link to the issue next to the (unchecked) checkbox in the
   PR description.

---

## Omega: Running CTests

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

4. **Check Results**

   Wait for the tests to complete. If all tests pass, check the box for this
   configuration in your PR. If not, file an issue (in the Polaris or Omega
   repo), note the problem, and link to the issue next to the (unchecked)
   checkbox in the PR description.

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
