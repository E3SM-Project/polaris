(dev-omega-pr-testing)=

# Testing an Omega pull request

The Omega pull request template asks for the CTests and the Polaris
`omega_pr` suite to pass on each supported machine and compiler, and for the
results to be recorded in `Testing` comments.  The utility in
`utils/omega/pr_testing` does this, run by a developer or by an AI agent.
Its `README.md` describes the commands, and its `AGENTS.md` holds the
instructions agents follow.

In outline, an *initiator* pins what to test in a branch on the requester's
fork and reports on linting and the documentation build.  A *tester* builds
and runs the baseline and the PR on each machine, then posts a comment made
from the files Polaris and the CTests wrote, with the commits of Polaris
and both Omega builds and any new compiler warnings.  By default, one agent
on the requester's own computer is both, running each machine's commands
over ssh through the connections the requester opens by logging in.
Frontier does not allow such connections, so an agent on Frontier tests its
rows.

The baseline is the Omega commit Polaris pins in `e3sm_submodules/Omega`,
unless the requester chooses another and says why.  If the PR needs
Polaris changes that the baseline Omega cannot run, the PR is tested with a
Polaris test merge and the baseline runs from a second Polaris checkout
without those changes.  An existing baseline
run is reused when its provenance matches (see
{py:func}`polaris.baselines.find_baseline`), which relies on the record of
the source that Polaris's build scripts write (see {ref}`dev-provenance`).

To start, the requester copies `utils/omega/pr_testing/example.cfg` to
`~/.config/omega_pr_test.cfg` on their computer and on each machine, fills
it in, logs in to each machine, and asks an agent in a Polaris checkout on
their computer something like:

```
Test Omega PR 553 with utils/omega/pr_testing, following
utils/omega/pr_testing/AGENTS.md.
```

`init` prints the prompt to give an agent on Frontier, which works out its
own rows.

The design is in {doc}`../design_docs/omega_pr_testing`.
