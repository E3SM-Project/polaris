(dev-suites)=

# Suites

As described in the {ref}`suites` section of the User's Guide, polaris
tasks can be organized into suites.  Each core has separate 
regression suites, and a core can have multiple independent regression suites.  
A developer  defines a suite by creating a `.txt` file within the 
`polaris/<component>/suites` directory.  The format of the `.txt` file is a 
list of the work directories to  the tasks desired to be part of the suite.  A 
line starting with `#` will be  treated as a comment line.

The philosophy and requirements for the suites are as follows:

## Pull-Request (PR) suite

The PR suite is intended to be run in the context of its namesake, a pull
request to the model component. The PR suite should be able to be run in under
an hour on 256 cores (two 128-core nodes), and the core count could be doubled
for quicker testing.

In order to achieve this performance, each test in the suite should preferably
take under 20 minutes on 32 cores. However, a test may exceed these recommended
limits if it offers significant benefit for catching bugs or performance issues
or providing code coverage.

Examples of tasks that may be included in this suite:

* Short tests to compare the solution and timers with a baseline (often called
performance tests lasting 3-5 time steps)
* Variants on the above with different combinations of config options
* Tests of all common config option combinations
* Tests that verify identical behavior:
  * across different numbers of cores
  * across different numbers of threads
  * with a longer model run and 2 (or more) shorter runs of the same total
duration with a model restart

## Nightly suite

The nightly suite is intended to be run nightly as a more exhaustive test
that no recent merges have resulted in a change in solution for any possible
combination of config options. It should require no more than 256 cores and
take no more than 120 minutes of run time on 256 cores.

Examples of tasks that may be included in this suite:

* More expensive convergence tests
* Tests that require a longer run to reach steady state.
* Tests in conditions not normally encountered in global E3SM runs (e.g.,
wetting and drying)
* Tests of all possible config option combinations
