# Shared code for the PR testing utilities

These modules are shared by the utilities that test pull requests on the
supported machines, such as [the Omega PR testing
utility](../omega/pr_testing/README.md).  They are not run directly.  Each
utility's script puts this directory on `sys.path`.

- `example.cfg`: the settings, which go in `~/.config/polaris_pr_test.cfg`
- `pr_test_config.py`: reads the settings
- `pr_test_git.py` and `pr_test_github.py`: git and GitHub helpers
- `pr_test_rows.py`: the machine, compiler and MPI combinations to test
- `pr_test_setup.py`: Polaris checkouts, Omega worktrees, baselines, suites,
  CTests and job submission
- `pr_test_report.py`: markers, the table of a machine's rows and posting
- `pr_test_status.py`: which rows have results on a PR
- `pr_test_warnings.py`: the build log parser

Their tests are in `tests/pr_testing`.
