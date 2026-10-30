(dev-omega-pr-testing)=

# Testing an Omega pull request

The Omega pull request template asks for the CTests, the Polaris
`omega_pr` suite and coupled CIME tests to pass on each supported machine
and compiler, and for the
results to be recorded in `Testing` comments.  The utility in
`utils/omega/pr_testing` does this, run by a developer or by an AI agent.
Its `README.md` describes the commands, and its `AGENTS.md` holds the
instructions agents follow.

In outline, an *initiator* pins what to test in a branch on the requester's
fork and reports on linting and the documentation build.  A *tester* builds
and runs the baseline and the PR on each machine, then posts one comment
for the machine's rows: a line for each row, and the files Polaris, the
CTests and CIME wrote, with the commits of Polaris and both Omega builds and any new
compiler warnings.  By default, one agent
on the requester's own computer is both, running each machine's commands
over ssh through the connections the requester opens by logging in.
Frontier does not allow such connections, so an agent on Frontier tests its
rows.

The baseline is the Omega commit Polaris pins in `e3sm_submodules/Omega`,
unless the requester chooses another, `develop` included, with a reason
that rests on evidence rather than a guess.  If the PR needs
Polaris changes that the baseline Omega cannot run, the PR is tested with a
Polaris test merge and the baseline runs from a second Polaris checkout
without those changes.  An existing baseline
run is reused when its provenance matches (see
{py:func}`polaris.baselines.find_baseline`), which relies on the record of
the source that Polaris's build scripts write (see {ref}`dev-provenance`).
A baseline with failed tasks is still reused, since running it again would
not fix them.  The report says how many tasks failed in the baseline and
does not count a task as a baseline difference or a failure just because
the baseline has no output to compare it with.

To start, the requester copies `utils/pr_testing/example.cfg` to
`~/.config/polaris_pr_test.cfg` on their computer and on each machine, fills
it in, logs in to each machine, and asks an agent in a Polaris checkout on
their computer something like:

```
Test Omega PR 553 with utils/omega/pr_testing, following
utils/omega/pr_testing/AGENTS.md.
```

`init` prints the prompt to give an agent on Frontier, which works out its
own rows.

The modules it shares with other PR testing utilities are in
`utils/pr_testing`.
