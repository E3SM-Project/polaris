"""
Filing findings: an issue of their own, a line in a clean-up batch, and the
prompt that hands a filed finding to a session that fixes it
"""

import contextlib
import json
import os
import tempfile
from dataclasses import dataclass
from typing import Iterator, List, Optional

from bug_hunt_ledger import Finding, split_evidence
from pr_test_github import gh

#: the repository each owner's issues go to
REPOS = {
    'omega': 'E3SM-Project/Omega',
    'e3sm': 'E3SM-Project/Omega',
    'polaris': 'E3SM-Project/polaris',
}

#: the branch fixes start from, by repository
BASE_BRANCHES = {
    'E3SM-Project/Omega': 'develop',
    'E3SM-Project/polaris': 'main',
}

#: the label that clean-up batches carry, by repository
CLEANUP_LABELS = {
    'E3SM-Project/Omega': 'clean up',
    'E3SM-Project/polaris': 'clean-up',
}

PRIORITY_LABELS = {
    'P1': 'priority: high',
    'P2': 'priority: medium',
    'P3': 'priority: low',
    'P4': 'priority: low',
}

#: Omega's labels for machines and compilers, by the parts of a row
ROW_LABELS = {
    'chrysalis': 'Chrysalis',
    'pm-cpu': 'pm-cpu',
    'pm-gpu': 'pm-gpu',
    'aurora': 'Aurora',
    'frontier': 'Frontier',
    'gnu': 'GNU',
    'gnugpu': 'GNU',
    'intel': 'intel',
    'intelgpu': 'intel',
}

#: the line that comes before an issue's signature
SIGNATURE_RULE = '\n---\n'


class FileError(Exception):
    """A finding cannot be filed as asked"""


@dataclass
class Issue:
    """
    An issue to file

    Attributes
    ----------
    repo : str
        The repository, such as ``E3SM-Project/Omega``

    title : str
        The title

    body : str
        The body, as Markdown

    labels : list of str
        Labels to add, if the repository has them
    """

    repo: str
    title: str
    body: str
    labels: List[str]


def repo_for(finding: Finding, repo: Optional[str] = None) -> str:
    """
    The repository a finding's issue goes to

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    repo : str, optional
        A repository the developer chose, which wins

    Returns
    -------
    repo : str
        The repository
    """
    if repo is not None:
        return repo
    if finding.owner not in REPOS:
        raise FileError(
            f'{finding.id} is owned by "{finding.owner}", which has no '
            f'repository of its own.  Pass --repo, or give it an owner with '
            f'"bug_hunt.py update {finding.id} --owner ...".'
        )
    return REPOS[finding.owner]


def render_issue(
    finding: Finding,
    signature: str,
    repo: Optional[str] = None,
    title: Optional[str] = None,
) -> Issue:
    """
    The issue for a finding

    The evidence's opening paragraph, which summarizes the case for the
    finding, is part of the body; the excerpts after it are folded away.

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    signature : str
        The signature that ends the issue

    repo : str, optional
        The repository, if not the owner's

    title : str, optional
        The title, if not the claim, cut short

    Returns
    -------
    issue : bug_hunt_file.Issue
        The issue
    """
    missing = [
        name
        for name in ('claim', 'evidence', 'reproduce', 'expected')
        if not getattr(finding, name)
    ]
    if missing:
        raise FileError(
            f'{finding.id} has no {", ".join(missing)} yet.  Add them with '
            f'"bug_hunt.py update {finding.id}" before filing it.'
        )
    repo = repo_for(finding, repo)
    opening, excerpts = split_evidence(finding.evidence)
    lines = [_sentence(finding.claim), '']
    seen = _where_seen(finding)
    if seen:
        lines.extend([seen, ''])
    lines.extend([opening, ''])
    lines.extend([f'Expected: {_sentence(finding.expected)}', ''])
    lines.extend(
        ['To reproduce:', '', '```', finding.reproduce or '', '```', '']
    )
    if excerpts:
        lines.extend(
            [
                '<details>',
                '<summary>Evidence</summary>',
                '',
                '```',
                excerpts,
                '```',
                '',
                '</details>',
                '',
            ]
        )
    lines.extend([SIGNATURE_RULE.strip('\n'), '', signature])
    labels = ['bug']
    if finding.priority in PRIORITY_LABELS:
        labels.append(PRIORITY_LABELS[finding.priority])
    if finding.owner == 'e3sm' or any(
        occurrence.source == 'coupled' for occurrence in finding.occurrences
    ):
        labels.append('Coupled')
    for row in finding.rows:
        for part in row.split('/'):
            if part in ROW_LABELS and ROW_LABELS[part] not in labels:
                labels.append(ROW_LABELS[part])
    return Issue(
        repo=repo,
        title=title or _title(finding.claim),
        body='\n'.join(lines) + '\n',
        labels=labels,
    )


def post_issue(issue: Issue) -> str:
    """
    File an issue with ``gh``, with the labels the repository has

    Parameters
    ----------
    issue : bug_hunt_file.Issue
        The issue

    Returns
    -------
    ref : str
        ``<owner>/<repo>#<number>``
    """
    labels = [label for label in issue.labels if label in _labels(issue.repo)]
    args = ['issue', 'create', '--repo', issue.repo, '--title', issue.title]
    for label in labels:
        args.extend(['--label', label])
    with _body_file(issue.body) as filename:
        url = gh(args + ['--body-file', filename]).strip()
    number = url.rstrip('/').rsplit('/', 1)[-1]
    return f'{issue.repo}#{number}'


def batch_line(finding: Finding) -> str:
    """
    A finding's line in a clean-up batch

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    Returns
    -------
    line : str
        A checklist line
    """
    where = finding.where or ', '.join(finding.rows)
    urls = [
        occurrence.url
        for occurrence in finding.occurrences
        if occurrence.url and occurrence.url.startswith('http')
    ]
    line = f'- [ ] {_sentence(finding.claim)}'
    if where:
        line = f'{line} ({where})'
    if urls:
        line = f'{line} [evidence]({urls[0]})'
    return line


def find_batch(repo: str, theme: str) -> Optional[dict]:
    """
    The open clean-up batch for a theme, if there is one

    Parameters
    ----------
    repo : str
        The repository

    theme : str
        The theme

    Returns
    -------
    issue : dict, optional
        ``number``, ``title`` and ``body``, or ``None``
    """
    title = batch_title(theme)
    output = gh(
        [
            'issue',
            'list',
            '--repo',
            repo,
            '--state',
            'open',
            '--search',
            f'"{title}" in:title',
            '--json',
            'number,title,body',
        ]
    )
    for issue in json.loads(output):
        if issue['title'] == title:
            return issue
    return None


def batch_title(theme: str) -> str:
    """The title of the clean-up batch for a theme"""
    return f'Clean-up: {theme}'


def new_batch(
    repo: str, theme: str, lines: List[str], signature: str
) -> Issue:
    """
    The issue that starts a clean-up batch

    Parameters
    ----------
    repo : str
        The repository

    theme : str
        The batch's theme

    lines : list of str
        Its first checklist lines

    signature : str
        The signature that ends the issue

    Returns
    -------
    issue : bug_hunt_file.Issue
        The issue
    """
    body = '\n'.join(
        [
            f'Small bugs with a common theme, {theme}, to fix together in '
            f'one pull request.',
            '',
        ]
        + lines
        # without a blank line, the rule would make the last line a heading
        + ['', SIGNATURE_RULE.strip('\n'), '', signature]
    )
    labels = [CLEANUP_LABELS[repo], 'priority: low']
    return Issue(
        repo=repo, title=batch_title(theme), body=f'{body}\n', labels=labels
    )


def add_to_batch(repo: str, issue: dict, lines: List[str]) -> str:
    """
    Add lines to a clean-up batch by editing its body

    Parameters
    ----------
    repo : str
        The repository

    issue : dict
        The batch, as :py:func:`find_batch` returns it

    lines : list of str
        The lines to add, all in one edit, since each edit replaces the
        whole body

    Returns
    -------
    ref : str
        ``<owner>/<repo>#<number>``
    """
    body = issue['body']
    for line in lines:
        # a line already in the batch is not added twice
        if line not in body:
            body = add_line(body, line)
    with _body_file(body) as filename:
        gh(
            [
                'issue',
                'edit',
                str(issue['number']),
                '--repo',
                repo,
                '--body-file',
                filename,
            ]
        )
    return f'{repo}#{issue["number"]}'


def add_line(body: str, line: str) -> str:
    """
    A batch's body with a line added after its last checklist line, before
    the signature

    Parameters
    ----------
    body : str
        The body

    line : str
        The line

    Returns
    -------
    body : str
        The new body
    """
    head, rule, tail = body.partition(SIGNATURE_RULE)
    head = head.rstrip('\n')
    return f'{head}\n{line}\n{rule}{tail}' if rule else f'{head}\n{line}\n'


def handoff(finding: Finding, ref: str) -> str:
    """
    The prompt for a new session that fixes a filed finding

    Parameters
    ----------
    finding : bug_hunt_ledger.Finding
        The finding

    ref : str
        Its issue or batch, ``<owner>/<repo>#<number>``

    Returns
    -------
    prompt : str
        The prompt
    """
    repo = ref.partition('#')[0]
    base = BASE_BRANCHES.get(repo, 'the default branch')
    tests = sorted(
        {key.test for key in finding.keys if key.phase not in ('code',)}
    )
    if tests and finding.rows:
        done = (
            f'Done when {", ".join(tests)} passes on '
            f'{", ".join(finding.rows)}.'
        )
    else:
        done = 'Done when the case in the issue no longer fails.'
    return (
        f'Fix {ref} on a new branch from {base}, following '
        f'utils/bug_hunt/AGENTS.md in Polaris. The evidence and how to '
        f'reproduce it are in the issue. {done}'
    )


def signature_for(agent: str, user: str, co_drafted: bool = False) -> str:
    """
    The signature that Polaris' ``AGENTS.md`` prescribes, or its co-drafted
    form when the user gave substantial direction on the content
    """
    if co_drafted:
        return f'*Drafted by @{user} and {agent} together*'
    return (
        f"*Posted by {agent} on @{user}'s behalf. The testing, analysis and "
        f'wording above are AI-authored; please check them accordingly.*'
    )


def _where_seen(finding: Finding) -> str:
    if not finding.occurrences:
        return f'In `{finding.where}`.' if finding.where else ''
    # a row that stopped reporting has no results, not failures, and its
    # last night with results may not have passed
    missing = {key.test for key in finding.keys if key.phase == 'missing'}
    parts = []
    for occurrence in sorted(
        finding.occurrences, key=lambda item: (item.test, item.row)
    ):
        if occurrence.test in missing:
            since = ': no results'
            last = 'last on'
        else:
            since = ''
            last = 'last passed'
        if occurrence.first_failed:
            since = f'{since} since {occurrence.first_failed}'
        passed = (
            f' ({last} {occurrence.last_passed})'
            if occurrence.last_passed
            else ''
        )
        parts.append(
            f'- `{occurrence.test}` on {occurrence.row}{since}{passed}'
        )
    lines = ['Seen:'] + parts
    if finding.merged_between:
        lines.append(
            f'\nMerged between the last pass and the first failure: '
            f'{", ".join(finding.merged_between)}'
        )
    return '\n'.join(lines)


def _labels(repo: str) -> List[str]:
    output = gh(
        ['label', 'list', '--repo', repo, '--limit', '300', '--json', 'name']
    )
    return [label['name'] for label in json.loads(output)]


@contextlib.contextmanager
def _body_file(body: str) -> Iterator[str]:
    """A temporary file holding an issue body, removed afterward"""
    handle, filename = tempfile.mkstemp(suffix='.md')
    try:
        with os.fdopen(handle, 'w') as stream:
            stream.write(body)
        yield filename
    finally:
        os.remove(filename)


def _title(claim: str) -> str:
    title = claim.strip().rstrip('.')
    if len(title) <= 100:
        return title
    return f'{title[:97].rsplit(" ", 1)[0]} ...'


def _sentence(text: Optional[str]) -> str:
    text = (text or '').strip()
    if text and text[-1] not in '.!?':
        text = f'{text}.'
    return text
