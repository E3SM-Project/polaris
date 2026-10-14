import omega_pr_status
import pr_test_github
import pr_test_status
from omega_pr_manifest import POLARIS_SUBMODULE, TEMPLATE_ROWS, Manifest
from pr_test_config import PrTestConfig, RemoteMachine

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
        '<!-- omega-pr-test {"schema": 2, "pr": 5, "pr_head": "' + HEAD + '", '
        '"rows": [{"row": "lint", "status": "complete", "result": "pass"}]} '
        '-->',
        '## Testing on pm-cpu and pm-gpu\n'
        '<!-- omega-pr-test {"schema": 2, "pr": 5, "pr_head": "' + HEAD + '", '
        '"rows": [{"row": "pm-cpu/gnu", "status": "complete", '
        '"result": "fail", "new_warnings": 3}, {"row": "pm-gpu/gnugpu", '
        '"status": "not-run", "result": "none"}]} -->',
        # a comment from before a machine's rows shared one
        '## Testing: chrysalis, intel, openmpi\n'
        '<!-- omega-pr-test {"schema": 1, "pr": 5, "pr_head": "'
        + OLD_HEAD
        + '", "row": "chrysalis/intel", "status": "complete", '
        '"result": "pass"} -->',
        '<!-- omega-pr-test {"schema": 2, "pr": 6, "rows": [{"row": '
        '"frontier/craygnu", "status": "complete", "result": "pass"}]} -->',
    ]
    monkeypatch.setattr(
        pr_test_github, 'get_comment_bodies', lambda repo, number: bodies
    )
    monkeypatch.setattr(
        pr_test_github,
        'get_pull_request',
        lambda repo, number: {'headRefOid': HEAD},
    )

    text = omega_pr_status.run_status(5)

    rows = {line.split()[0]: line for line in text.splitlines()[1:]}
    assert 'pass' in rows['lint']
    assert 'fail' in rows['pm-cpu/gnu']
    assert '3 new warnings' in rows['pm-cpu/gnu']
    assert 'not run' in rows['pm-gpu/gnugpu']
    assert 'pass' in rows['chrysalis/intel']
    assert 'stale' in rows['chrysalis/intel']
    # a marker for another PR is ignored
    assert rows['frontier/craygnu'].split() == ['frontier/craygnu', '-']


def test_run_status_names_machine_rows(monkeypatch):
    _no_comments(monkeypatch)
    monkeypatch.setattr(
        pr_test_status, 'discover_machine', lambda quiet: 'pm-cpu'
    )

    text = omega_pr_status.run_status(5, _manifest())

    assert text.splitlines()[-1] == (
        'Rows to test on this machine (pm-cpu): pm-cpu/gnu, pm-gpu/gnugpu'
    )


def test_run_status_off_the_machines(monkeypatch):
    _no_comments(monkeypatch)
    monkeypatch.setattr(pr_test_status, 'discover_machine', lambda quiet: None)

    text = omega_pr_status.run_status(5, _manifest())

    lines = text.splitlines()
    assert lines[-5:] == [
        "Rows to test from each machine's login nodes:",
        '  aurora: aurora/oneapi-ifx, aurora/oneapi-ifxgpu',
        '  chrysalis: chrysalis/intel',
        '  frontier: frontier/craygnu, frontier/craygnu-mphipcc',
        '  pm-cpu and pm-gpu: pm-cpu/gnu, pm-gpu/gnugpu',
    ]


def test_run_status_names_how_to_reach_machines(monkeypatch):
    _no_comments(monkeypatch)
    monkeypatch.setattr(pr_test_status, 'discover_machine', lambda quiet: None)
    config = PrTestConfig(
        work_base='/work',
        omega_repo='/omega',
        machines={'pm-cpu': RemoteMachine('pm', '~/polaris')},
    )

    text = omega_pr_status.run_status(5, _manifest(), config)

    lines = text.splitlines()
    assert lines[-2] == (
        '  frontier: frontier/craygnu, frontier/craygnu-mphipcc (no '
        '[machines] line, so an agent on the machine tests it)'
    )
    assert lines[-1] == (
        '  pm-cpu and pm-gpu: pm-cpu/gnu, pm-gpu/gnugpu (ssh pm, Polaris in '
        '~/polaris)'
    )


def _no_comments(monkeypatch):
    monkeypatch.setattr(
        pr_test_github, 'get_comment_bodies', lambda repo, number: []
    )
    monkeypatch.setattr(
        pr_test_github,
        'get_pull_request',
        lambda repo, number: {'headRefOid': HEAD},
    )


def _manifest():
    return Manifest(
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
