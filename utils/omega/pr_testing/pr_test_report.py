"""
The pieces every Testing comment the utility writes has in common: a
hidden marker, the notes, the signature and posting
"""

import json
import os
import re
from typing import Any, Dict, List, Optional

import pr_test_github as github
from pr_test_config import PrTestConfig
from pr_test_manifest import Manifest

MARKER_SCHEMA = 1

MARKER_PREFIX = 'omega-pr-test'

_MARKER_PATTERN = re.compile(rf'<!--\s*{MARKER_PREFIX}\s+(\{{.*?\}})\s*-->')

#: the signature that Polaris's AGENTS.md prescribes for posts made by an
#: agent on someone's behalf
SIGNATURE = (
    "*Posted by {agent} on @{user}'s behalf. The testing, analysis and "
    'wording above are AI-authored; please check them accordingly.*'
)


def get_run_dir(config: PrTestConfig, manifest: Manifest) -> str:
    """The directory this machine's runs for a manifest go in"""
    return os.path.join(config.work_base, manifest.run_name)


def make_marker(
    manifest: Manifest, row: str, status: str, result: str, **extra: Any
) -> str:
    """
    The hidden marker that starts a Testing comment

    Parameters
    ----------
    manifest : pr_test_manifest.Manifest
        The manifest that was tested

    row : str
        ``<machine>/<compiler>``, or ``lint``

    status : {'complete', 'not-run'}
        Whether the row was run

    result : {'pass', 'fail', 'none'}
        The overall result

    **extra
        Anything else to record in the marker

    Returns
    -------
    marker : str
        An HTML comment holding the marker as JSON
    """
    contents: Dict[str, Any] = {
        'schema': MARKER_SCHEMA,
        'pr': manifest.pull_request,
        'pr_head': manifest.pr_head,
        'test': manifest.test_commit,
        'baseline': manifest.baseline_commit,
        'row': row,
        'status': status,
        'result': result,
    }
    contents.update(extra)
    return f'<!-- {MARKER_PREFIX} {json.dumps(contents)} -->'


def parse_marker(body: str) -> Optional[Dict[str, Any]]:
    """The marker in a comment's body, or ``None`` if it has none"""
    match = _MARKER_PATTERN.search(body)
    if match is None:
        return None
    try:
        contents = json.loads(match.group(1))
    except ValueError:
        return None
    if not isinstance(contents, dict):
        return None
    return contents


def assemble(
    heading: str,
    marker: str,
    sections: List[str],
    manifest: Manifest,
    notes: Optional[str] = None,
    agent: Optional[str] = None,
) -> str:
    """
    Put a Testing comment together

    Parameters
    ----------
    heading : str
        The comment's heading, without the ``##``

    marker : str
        The hidden marker

    sections : list of str
        The generated sections, in order

    manifest : pr_test_manifest.Manifest
        The manifest that was tested, whose notes are repeated

    notes : str, optional
        The agent's or tester's notes

    agent : str, optional
        The agent posting the comment, which adds the signature

    Returns
    -------
    text : str
        The comment
    """
    parts = [f'## {heading}\n{marker}']
    parts.extend(section.strip('\n') for section in sections)
    note_lines = []
    if manifest.notes:
        note_lines.append(f'From the requester: {manifest.notes.strip()}')
    if notes:
        note_lines.append(notes.strip())
    if note_lines:
        parts.append('### Notes\n\n' + '\n\n'.join(note_lines))
    if agent:
        signature = SIGNATURE.format(agent=agent, user=manifest.requester)
        parts.append(f'---\n\n{signature}')
    return '\n\n'.join(parts) + '\n'


def deliver(
    text: str, path: str, pull_request: int, post: bool
) -> Optional[str]:
    """
    Write a Testing comment to a file and post it if asked

    Parameters
    ----------
    text : str
        The comment

    path : str
        The file to write it to

    pull_request : int
        The Omega pull request to post it on

    post : bool
        Whether to post it

    Returns
    -------
    url : str, optional
        The URL of the posted comment, or ``None`` if it was not posted
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    if not post:
        return None
    return github.post_comment(pull_request, path)


def post_file(pull_request: int, path: str) -> str:
    """
    Post a Testing comment that ``report`` or ``lint`` wrote, perhaps on
    another machine, from its file

    The comment must have a marker for the pull request, so that only a
    comment the utility wrote is posted, and only on the PR it is for.

    Parameters
    ----------
    pull_request : int
        The Omega pull request to post it on

    path : str
        The comment's file

    Returns
    -------
    url : str
        The URL of the posted comment
    """
    with open(path, 'r', encoding='utf-8') as f:
        marker = parse_marker(f.read())
    if marker is None:
        raise ValueError(
            f'{path} has no {MARKER_PREFIX} marker, so it is not a comment '
            f'that report or lint wrote.'
        )
    if marker.get('pr') != pull_request:
        raise ValueError(
            f'{path} is a comment for PR {marker.get("pr")}, not '
            f'{pull_request}.'
        )
    return github.post_comment(pull_request, path)


def read_notes(filename: Optional[str]) -> Optional[str]:
    """The contents of a notes file, if one was given"""
    if filename is None:
        return None
    with open(filename, 'r', encoding='utf-8') as f:
        return f.read()
