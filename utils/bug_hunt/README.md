# Bug hunting for Omega and Polaris

`bug_hunt.py` finds bugs in Omega and Polaris, checks them against the
issues and pull requests that already track them, ranks them, and asks a
developer for a few decisions at a time.  Findings wait in a ledger, a git
repository with a YAML file for each.  Agents follow
[`AGENTS.md`](AGENTS.md).

## Setting up

Clone the ledger repository, and say where it is in a `[bug_hunt]` section
of `~/.config/polaris_pr_test.cfg`, the file the PR testing utilities use:

```ini
[bug_hunt]
# a clone of the ledger repository
ledger = /path/to/omega-polaris-bug-hunt-ledger
# the most decisions a digest asks for, besides P1 findings
decisions = 5
# Polaris and CIME work directories to harvest with --local
harvest_roots = /path/to/runs
```

`omega_repo` in the `[polaris_pr_test]` section, a clone of
E3SM-Project/Omega, is used to list the merges between the last night a test
passed and the first night it failed.

## Commands

| Command | What it does |
|---|---|
| `harvest` | reads CDash (and with `--local`, runs on disk) into the ledger |
| `park` | records a bug found while doing something else, or in a review |
| `hold` | puts rows on hold, so a harvest does not report them as stopped |
| `outside-v4` | lists or edits the features and options outside E3SM v4, which rank lower |
| `match` | lists issues and pull requests that may already track findings |
| `update` | records the agent's decisions about a finding |
| `review` | lists the Omega and Polaris merges since the last review, or records one |
| `digest` | writes the decisions for the developer |
| `file` | files a finding as an issue or in a clean-up batch |
| `handoff` | prints the prompt for a session that fixes a finding |
| `status` | summarizes the ledger |

Nothing is posted to GitHub without `file --post`.  `cdash.yaml` lists the
CDash builds that are harvested, and `campaigns.yaml` the tests a hunt can
run that do not run regularly, including the `omega_hunt` and
`omega_hunt_long` suites.

The tests are in `tests/bug_hunt`.
