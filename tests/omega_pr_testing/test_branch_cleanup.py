import omega_pr_cleanup

FORK = 'git@github.com:me/E3SM.git'


def test_find_test_branches(monkeypatch):
    sha = 'a' * 40
    refs = [
        'omega-pr-test/5-1111111',
        'omega-pr-test/5-1111111-baseline',
        'omega-pr-test/6-2222222',
        'omega-pr-test/7-3333333',
        'omega-pr-test/not-a-test-branch',
    ]
    output = '\n'.join(f'{sha}\trefs/heads/{ref}' for ref in refs)
    calls = []

    def git(args, cwd):
        calls.append(args)
        return output

    states = {5: 'MERGED', 6: 'CLOSED', 7: 'OPEN'}
    queried = []

    def get_pull_request(repo, number):
        queried.append(number)
        return {'state': states[number]}

    monkeypatch.setattr(omega_pr_cleanup.git_tools, 'git', git)
    monkeypatch.setattr(omega_pr_cleanup, 'get_pull_request', get_pull_request)

    branches = omega_pr_cleanup.find_test_branches('/omega', FORK)

    assert calls == [
        ['ls-remote', '--heads', FORK, 'refs/heads/omega-pr-test/*']
    ]
    assert queried == [5, 6, 7]
    assert [(b.name, b.state) for b in branches] == [
        ('omega-pr-test/5-1111111', 'MERGED'),
        ('omega-pr-test/5-1111111-baseline', 'MERGED'),
        ('omega-pr-test/6-2222222', 'CLOSED'),
        ('omega-pr-test/7-3333333', 'OPEN'),
    ]

    text = omega_pr_cleanup.format_branches(branches, FORK, deleted=False)
    assert 'Would delete (3):' in text
    assert 'omega-pr-test/6-2222222  (#6 closed)' in text
    assert 'Kept for open PRs (1):\n  omega-pr-test/7-3333333' in text


def test_delete_test_branches(monkeypatch):
    calls = []

    def git(args, cwd):
        calls.append(args)
        return ''

    monkeypatch.setattr(omega_pr_cleanup.git_tools, 'git', git)
    branches = [
        omega_pr_cleanup.TestBranch('omega-pr-test/5-1111111', 5, 'MERGED')
    ]

    omega_pr_cleanup.delete_test_branches('/omega', FORK, branches)
    omega_pr_cleanup.delete_test_branches('/omega', FORK, [])

    assert calls == [
        ['push', '--quiet', FORK, '--delete', 'omega-pr-test/5-1111111']
    ]
