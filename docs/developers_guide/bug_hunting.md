(dev-bug-hunting)=

# Hunting for bugs

The utility in `utils/bug_hunt` finds bugs in Omega and Polaris, checks them
against the issues and pull requests that already track them, ranks them,
and asks a developer for a few decisions at a time.  It is run by an AI
agent at a developer's request; nothing runs on a schedule.  Its `README.md`
describes the commands, and its `AGENTS.md` holds the instructions agents
follow.

A hunt can read the nightly results on
[CDash](https://my.cdash.org/index.php?project=omega): the CTests and the
`omega_nightly` suite from the cron jobs in `cron-scripts`, and the coupled
`e3sm_omega_developer` tests.  It can also read Polaris and CIME runs on
disk, run tests that do not run regularly, and review Omega code merged
since the last review.  Only `omega_pr` and `omega_nightly` run regularly
with Omega, so the `omega_hunt` and `omega_hunt_long` suites hold tasks that
exercise what those two do not, including tasks that are known to fail.

Each finding is kept in a ledger, a git repository with a YAML file for each
finding.  A failure seen on several machines or nights is one finding.  The
agent links each finding to any issue that tracks it, gives it an owner
(Omega, Polaris, the rest of E3SM or the machine environment) and a priority,
and writes a digest of at most five decisions.  The developer answers each
with one word: `file` it as an issue, `batch` it with similar small bugs in
a clean-up issue, `log` it in the ledger, `dismiss` it, or `dig` further.
Nothing is posted to GitHub without the developer's permission.  A machine
that stops reporting for a reason that is not a bug, such as an allocation
out of compute hours, can be put on hold with `bug_hunt.py hold`, and the
harvest takes it off hold when it reports again.  Omega bugs that matter
only for features or options outside E3SM v4, listed with
`bug_hunt.py outside-v4`, rank one level lower.

To start, the developer clones the ledger repository, names it in a
`[bug_hunt]` section of `~/.config/polaris_pr_test.cfg`, and asks an agent
in a Polaris checkout something like:

```
Hunt Omega bugs following utils/bug_hunt/AGENTS.md: harvest since the
last hunt, then triage.
```

Agents doing other work use the same utility to set aside bugs that do not
block their task, with `bug_hunt.py park`, as the Polaris `AGENTS.md` says.
A bug that blocks the task is fixed as part of it.
