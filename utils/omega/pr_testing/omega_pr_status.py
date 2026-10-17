"""
Which rows of an Omega PR have Testing comments from the utility, and
whether they are for the PR's current head
"""

from typing import Optional

import pr_test_github as github
import pr_test_status as status
from omega_pr_manifest import MARKER_PREFIX, TEMPLATE_ROWS, UPSTREAM, Manifest
from pr_test_config import PrTestConfig


def run_status(
    pull_request: int,
    manifest: Optional[Manifest] = None,
    config: Optional[PrTestConfig] = None,
) -> str:
    """
    Summarize the Testing comments on an Omega PR

    Parameters
    ----------
    pull_request : int
        The number of the Omega PR

    manifest : omega_pr_manifest.Manifest, optional
        The manifest whose rows to list, the Omega PR template's by default.
        With a manifest, the rows a tester on this machine runs are named
        as well, or off the machines, the rows to test from each one.

    config : pr_test_config.PrTestConfig, optional
        The settings, whose ``[machines]`` entries are named with each
        machine's rows off the machines

    Returns
    -------
    text : str
        One line per row
    """
    head = github.get_pull_request(UPSTREAM, pull_request)['headRefOid']
    entries = status.get_row_entries(UPSTREAM, pull_request, MARKER_PREFIX)
    # lint is only posted when it did not come from CI, so it is listed only
    # if it was
    rows = manifest.rows if manifest is not None else TEMPLATE_ROWS
    text = status.format_status([row.name for row in rows], entries, head)
    if manifest is not None:
        machine_rows = status.format_machine_rows(manifest.rows, config)
        text = f'{text}\n\n{machine_rows}'
    return text
