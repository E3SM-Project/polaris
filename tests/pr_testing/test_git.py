import pr_test_git
import pytest

URL = 'https://example.com/x.git'


def test_fetch_retries_when_another_fetch_updates_the_ref(monkeypatch):
    calls = _fake_git(
        monkeypatch,
        [
            'error: fetching ref refs/omega-pr-test/x failed: incorrect old '
            'value provided',
            None,
        ],
    )

    pr_test_git.fetch('/repo', URL, ['a:b'])

    assert calls == [['fetch', '--quiet', URL, '+a:b']] * 2


def test_fetch_gives_up_on_other_errors(monkeypatch):
    calls = _fake_git(monkeypatch, ['fatal: could not read from remote'])

    with pytest.raises(pr_test_git.GitError, match='could not read'):
        pr_test_git.fetch('/repo', URL, ['a:b'])

    assert len(calls) == 1


def test_fetch_gives_up_after_its_attempts(monkeypatch):
    message = "error: cannot lock ref 'refs/omega-pr-test/x'"
    calls = _fake_git(monkeypatch, [message] * pr_test_git.FETCH_ATTEMPTS)

    with pytest.raises(pr_test_git.GitError, match='cannot lock ref'):
        pr_test_git.fetch('/repo', URL, ['a:b'])

    assert len(calls) == pr_test_git.FETCH_ATTEMPTS


def _fake_git(monkeypatch, errors):
    """Make git fail with each error in turn, or succeed for ``None``"""
    calls = []
    remaining = list(errors)

    def git(args, cwd):
        calls.append(args)
        error = remaining.pop(0)
        if error is not None:
            raise pr_test_git.GitError(error)
        return ''

    monkeypatch.setattr(pr_test_git, 'git', git)
    monkeypatch.setattr(pr_test_git.time, 'sleep', lambda seconds: None)
    return calls
