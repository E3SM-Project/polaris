"""
Which rows of a Polaris version update have Testing comments from the
utility, with each kind of Spack environment, and whether they are for the
PR's current head
"""

from typing import Optional

import pr_test_github as github
import pr_test_status as status
from polaris_update_manifest import MARKER_PREFIX, UPSTREAM, Manifest
from polaris_update_report import SPACK_KINDS
from pr_test_config import PrTestConfig


def run_status(
    pull_request: int,
    manifest: Optional[Manifest] = None,
    config: Optional[PrTestConfig] = None,
) -> str:
    """
    Summarize the Testing comments on a Polaris version update

    Parameters
    ----------
    pull_request : int
        The number of the Polaris PR

    manifest : polaris_update_manifest.Manifest, optional
        The manifest whose rows to list.  With a manifest, the rows a
        tester on this machine runs are named as well, or off the machines,
        the rows to test from each one.

    config : pr_test_config.PrTestConfig, optional
        The settings, whose ``[machines]`` entries are named with each
        machine's rows off the machines

    Returns
    -------
    text : str
        One line per row and kind of Spack environment
    """
    head = github.get_pull_request(UPSTREAM, pull_request)['headRefOid']
    entries = status.get_row_entries(UPSTREAM, pull_request, MARKER_PREFIX)
    for entry in entries:
        entry['row'] = f'{entry.get("row")}/{entry.get("spack")}'
    # list the kinds of environment that have been reported on, or both if
    # none has
    kinds = [
        kind
        for kind in SPACK_KINDS
        if any(entry['row'].endswith(f'/{kind}') for entry in entries)
    ] or SPACK_KINDS
    rows = []
    if manifest is not None:
        rows = [
            f'{row.name}/{kind}' for kind in kinds for row in manifest.rows
        ]
    if not rows and not entries:
        return (
            f'There are no Testing comments from the utility on PR '
            f'{pull_request}.'
        )
    text = status.format_status(rows, entries, head)
    if manifest is not None:
        machine_rows = status.format_machine_rows(manifest.rows, config)
        text = f'{text}\n\n{machine_rows}'
    return text
