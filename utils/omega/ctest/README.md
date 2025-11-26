# Omega CTest utility

This utility helps Omega developers build the model and run
CTests for a given compiler.

The utility will check out submodules that Omega needs and build Omega with
the requested compilers (see below). On a compute node, the utility will also
run CTests directly.  On a login node, it will create a job script for running
CTests and can optionally submit the job script.

## Instructions

1. You must have followed the instructions for configuring
   Polaris on a [supported machine](https://e3sm-project.github.io/polaris/main/developers_guide/quick_start.html#supported-machines),
   specifying the compiler for which you wish to test Omega.  The result
   should be an activation script like:
   ```
   load_dev_polaris_0.3.0-alpha.1_chrysalis_intel_openmpi.sh
   ```
   You must be on a machine that supports both E3SM (present in Omega's
   [config_machines.xml](https://github.com/E3SM-Project/Omega/blob/develop/cime_config/machines/config_machines.xml))
   and Polaris (see [supported machines](https://e3sm-project.github.io/polaris/main/developers_guide/machines/index.html#supported-machines)).

2. Source the polaris load script for the desired compiler, e.g.:
   ```
   source load_dev_polaris_0.3.0-alpha.1_chrysalis_intel_openmpi.sh
   ```

3. Initialize the submodule if you are using it (as opposed to a different
   Omega development branch) and you have not already done so:
   ```
   git submodule update --init e3sm_submodules/Omega
   ```

4. Run the utility:
   ```
   ./utils/omega/ctest/omega_ctest.py
   ```
   The utility will check out submodules and build Omega with the compilers
   associated with the Polaris load script (e.g. `intel` in the example above).

   The code is built in a subdirectory `build_omega/build_<machine>_<compiler>`
   within the current directory (e.g. the base of the Polaris branch so not
   typically within the Omega branch).

   **Flags**:

   ```
   usage: omega_ctest.py [-h] [-o OMEGA_BRANCH] [-c] [-s] [-d]
                      [--cmake_flags CMAKE_FLAGS]
   ```

   * `-o <path_to_omega_branch>`: point to a branch of Omega
     (`e3sm_submodules/Omega` by default)

   * `-c`: indicates that the build subdirectory should be removed first to
     allow a clean build

   * `-s`: if running the utility on a login node, submit the job script that
     the utility generates (does nothing on a compute node)

   * `--account`: specify the account to supply in the job script (necessary
     on some machines, such as Chicoma)

   * `-d`: build Omega in debug mode

   * `--cmake_flags="<flags>"`: Extra flags to pass to the `cmake` command

5. If you are on a login node and didn't use the `-s` flag, you will need
   to submit the batch job to run CTests yourself (perhaps after editing the
   job script), e.g.:
   ```
   sbatch build_omega/job_build_and_ctest_omega_chrysalis_intel.sh
   ```

If all goes well, you will see something like:
```
$ cat omega_ctest_chrysalis_intel.o464153
Test project /gpfs/fs1/home/ac.xylar/e3sm_work/polaris/improve-omega-ctest-output/build_omega/build_chrysalis_intel
      Start  1: DATA_TYPES_TEST
 1/33 Test  #1: DATA_TYPES_TEST ....................   Passed    0.44 sec
      Start  2: MACHINE_ENV_TEST
 2/33 Test  #2: MACHINE_ENV_TEST ...................   Passed    0.88 sec
      Start  3: BROADCAST_TEST
 3/33 Test  #3: BROADCAST_TEST .....................   Passed    0.89 sec
      Start  4: LOGGING_TEST
...
32/33 Test #32: GSWC_CALL_TEST .....................   Passed    0.06 sec
      Start 33: EOS_TEST
33/33 Test #33: EOS_TEST ...........................   Passed    1.20 sec

100% tests passed, 0 tests failed out of 33


Label Time Summary:
OPENMP     =  63.42 sec*proc (32 tests)
Omega-0    =  63.42 sec*proc (32 tests)

Total Test time (real) =  63.51 sec

(Copy the following to a comment in your Omega PR)

CTest unit tests:
- Machine: chrysalis
- Compiler: intel
- Build type: Release
- Result: All tests passed
- Log: /path/to/ctests.log

```
