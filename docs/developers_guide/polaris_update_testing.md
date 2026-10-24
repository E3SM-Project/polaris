(dev-polaris-update-testing)=

# Testing a Polaris version update

A pull request that updates Polaris to a new version and its Spack
environments needs the MPAS-Ocean `mpaso_pr` suite and the Omega CTests and
`omega_pr` suite to pass on every supported machine, compiler and MPI
library, first with test Spack environments and then with the shared ones
(see {ref}`dev-supported-machines` and the
[running test suites](updating_spack/testing/running_test_suites.md) page).
The utility in `utils/polaris_update_testing` does this, run by a developer
or by an AI agent.  Its `README.md` describes the commands, and its
`AGENTS.md` holds the instructions agents follow.

It works like the Omega PR testing utility ({ref}`dev-omega-pr-testing`),
with the same settings in `~/.config/polaris_pr_test.cfg`.  It also
deploys the Spack environments, and each machine's report is for one kind
of Spack environment, shared or test, read from the load script.  An
optional baseline runs the current `main` with its own shared environments.
For test environments, `deploy` can use a `mache` branch that is not
released yet, with `--mache-fork` and `--mache-branch`, and the report then
says the `mache` came from a branch (see
[Testing an unreleased mache](updating_spack/testing/updating_mache.md#testing-an-unreleased-mache)).

To start, the requester asks an agent in a Polaris checkout on their
computer something like:

```
Test Polaris PR 835 with utils/polaris_update_testing, deploying the shared
Spack environments, following utils/polaris_update_testing/AGENTS.md.
```

The design is in {doc}`../design_docs/polaris_update_testing`.
