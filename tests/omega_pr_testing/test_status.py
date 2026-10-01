import pr_test_github
import pr_test_status
from pr_test_manifest import POLARIS_SUBMODULE, TEMPLATE_ROWS, Manifest

HEAD = 'a' * 40
OLD_HEAD = 'b' * 40


def test_format_status():
    markers = [
        _marker('chrysalis/intel', OLD_HEAD, result='fail'),
        _marker('chrysalis/intel', HEAD, result='pass', new_warnings=2),
        _marker('aurora/oneapi-ifx', HEAD, status='not-run', result='none'),
        _marker('lint', OLD_HEAD, result='pass'),
        _marker('chrysalis/gnu', HEAD, result='pass'),
    ]

    lines = pr_test_status.format_status(
        ['lint', 'chrysalis/intel', 'aurora/oneapi-ifx', 'pm-cpu/gnu'],
        markers,
        HEAD,
    ).splitlines()

    header = ['row', 'result', 'PR', 'head', 'test', 'commit']
    assert lines[0].split() == header
    rows = {line.split()[0]: line for line in lines[1:]}
    assert 'pass' in rows['chrysalis/intel']
    assert '2 new warnings' in rows['chrysalis/intel']
    assert 'stale' not in rows['chrysalis/intel']
    assert 'not run' in rows['aurora/oneapi-ifx']
    assert 'stale: the PR has moved' in rows['lint']
    assert rows['pm-cpu/gnu'].split() == ['pm-cpu/gnu', '-']
    # a row the list did not name still shows up, at the end
    assert lines[-1].startswith('chrysalis/gnu')


def test_run_status(monkeypatch):
    bodies = [
        'A comment from a person',
        '## Testing: lint and docs\n'
        '<!-- omega-pr-test {"pr": 5, "pr_head": "' + HEAD + '", '
        '"row": "lint", "status": "complete", "result": "pass"} -->',
        '<!-- omega-pr-test {"pr": 6, "row": "pm-cpu/gnu"} -->',
    ]
    monkeypatch.setattr(
        pr_test_github, 'get_comment_bodies', lambda number: bodies
    )
    monkeypatch.setattr(
        pr_test_github,
        'get_pull_request',
        lambda number: {'headRefOid': HEAD},
    )

    text = pr_test_status.run_status(5)

    rows = {line.split()[0]: line for line in text.splitlines()[1:]}
    assert 'pass' in rows['lint']
    # a marker for another PR is ignored
    assert rows['pm-cpu/gnu'].split() == ['pm-cpu/gnu', '-']


def test_run_status_names_machine_rows(monkeypatch):
    monkeypatch.setattr(
        pr_test_github, 'get_comment_bodies', lambda number: []
    )
    monkeypatch.setattr(
        pr_test_github,
        'get_pull_request',
        lambda number: {'headRefOid': HEAD},
    )
    monkeypatch.setattr(
        pr_test_status, 'discover_machine', lambda quiet: 'pm-cpu'
    )
    manifest = Manifest(
        requester='tester',
        pull_request=5,
        pr_head=HEAD,
        base_branch='develop',
        base_head=OLD_HEAD,
        test_commit='c' * 40,
        baseline_commit='d' * 40,
        baseline_source=POLARIS_SUBMODULE,
        baseline_reason=None,
        polaris_commit='e' * 40,
        baseline_polaris_commit='e' * 40,
        rows=TEMPLATE_ROWS,
    )

    text = pr_test_status.run_status(5, manifest)

    assert text.splitlines()[-1] == (
        'Rows to test on this machine (pm-cpu): pm-cpu/gnu, pm-gpu/gnugpu'
    )


def _marker(row, pr_head, status='complete', result='pass', **extra):
    marker = {
        'pr': 5,
        'pr_head': pr_head,
        'test': 'c' * 40,
        'row': row,
        'status': status,
        'result': result,
    }
    marker.update(extra)
    return marker
