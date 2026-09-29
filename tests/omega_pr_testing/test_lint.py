import pr_test_github
import pr_test_init
import pr_test_lint
import pr_test_report
import pytest
from pr_test_fixtures import make_fixture

CI_RUN = {
    'name': 'lint and test docs',
    'status': 'completed',
    'conclusion': 'success',
    'id': 42,
    'html_url': 'https://github.com/E3SM-Project/Omega/actions/job/42',
}


@pytest.fixture
def pushed(tmp_path, monkeypatch):
    """A fixture whose test branch has been pushed to the fork"""
    fixture = make_fixture(tmp_path, monkeypatch)
    result = pr_test_init.initiate(
        config=fixture.config,
        pull_request=5,
        polaris_dir=fixture.polaris_dir,
        push=True,
    )
    return fixture, result.manifest


def test_lint_from_ci(pushed, monkeypatch):
    fixture, manifest = pushed
    _mock_ci(monkeypatch, [CI_RUN], ['success', 'success'])

    text, url, path, from_ci = pr_test_lint.run_lint(
        fixture.config, fixture.fork, manifest.branch, agent='Claude Code'
    )

    assert url is None
    assert from_ci
    assert text.startswith('## Testing: lint and docs\n<!-- omega-pr-test ')
    assert '- pre-commit on the files the PR changes: passed (CI)' in text
    assert '- Documentation build (`make html-strict`): passed (CI)' in text
    assert "on @tester's behalf" in text
    marker = pr_test_report.parse_marker(text)
    assert marker is not None
    assert (marker['row'], marker['result']) == ('lint', 'pass')
    assert marker['pr_head'] == fixture.pr_head
    with open(path, encoding='utf-8') as f:
        assert f.read() == text


def test_lint_runs_locally_when_ci_failed(pushed, monkeypatch, tmp_path):
    fixture, manifest = pushed
    failed = dict(CI_RUN, conclusion='failure')
    _mock_ci(monkeypatch, [failed], [])
    fixture.config.omega_dev_env = str(
        _make_dev_env(tmp_path / 'omega_dev', make_exit=2)
    )

    text, _, _, from_ci = pr_test_lint.run_lint(
        fixture.config, fixture.fork, manifest.branch
    )

    assert not from_ci
    assert 'finished with `failure`' in text
    assert '- pre-commit on the files the PR changes: passed (local run' in (
        text
    )
    assert '- Documentation build (`make html-strict`): failed (local' in (
        text
    )
    marker = pr_test_report.parse_marker(text)
    assert marker is not None and marker['result'] == 'fail'
    # pre-commit was given the file the PR changes, and ran in its own tree
    args = (tmp_path / 'omega_dev' / 'pre-commit.args').read_text()
    assert args.split() == [
        'run',
        '--show-diff-on-failure',
        '--files',
        'c.txt',
    ]
    assert 'Signature' not in text and '---' not in text


def test_lint_needs_dev_env_without_ci(pushed, monkeypatch):
    fixture, manifest = pushed
    _mock_ci(monkeypatch, [], [])

    with pytest.raises(pr_test_lint.LintError, match='omega_dev_env'):
        pr_test_lint.run_lint(fixture.config, fixture.fork, manifest.branch)


def test_lint_does_not_post_ci_results(pushed, monkeypatch):
    fixture, manifest = pushed
    _mock_ci(monkeypatch, [CI_RUN], ['success', 'success'])
    posted = _mock_post(monkeypatch)

    _, url, _, from_ci = pr_test_lint.run_lint(
        fixture.config, fixture.fork, manifest.branch, post=True
    )

    assert from_ci
    assert url is None
    assert posted == []


def test_lint_posts_local_results(pushed, monkeypatch, tmp_path):
    fixture, manifest = pushed
    _mock_ci(monkeypatch, [], [])
    fixture.config.omega_dev_env = str(
        _make_dev_env(tmp_path / 'omega_dev', make_exit=0)
    )
    posted = _mock_post(monkeypatch)

    _, url, path, from_ci = pr_test_lint.run_lint(
        fixture.config, fixture.fork, manifest.branch, post=True
    )

    assert not from_ci
    assert url == 'https://github.com/E3SM-Project/Omega/pull/5#comment'
    assert posted == [(5, path)]


def _mock_post(monkeypatch):
    posted = []

    def post_comment(number, body_file):
        posted.append((number, body_file))
        return 'https://github.com/E3SM-Project/Omega/pull/5#comment'

    monkeypatch.setattr(pr_test_github, 'post_comment', post_comment)
    return posted


def _mock_ci(monkeypatch, runs, conclusions):
    steps = [
        {'name': name, 'conclusion': conclusion}
        for name, conclusion in zip(
            ['Run pre-commit', 'Build Sphinx Docs'], conclusions, strict=False
        )
    ]
    monkeypatch.setattr(pr_test_github, 'get_check_runs', lambda sha: runs)
    monkeypatch.setattr(pr_test_github, 'get_job_steps', lambda job_id: steps)


def _make_dev_env(env_dir, make_exit):
    """Stand-ins for the pre-commit and make of an omega_dev environment"""
    bin_dir = env_dir / 'bin'
    bin_dir.mkdir(parents=True)
    pre_commit = bin_dir / 'pre-commit'
    pre_commit.write_text(
        f'#!/bin/bash\necho "$@" > {env_dir}/pre-commit.args\nexit 0\n'
    )
    make = bin_dir / 'make'
    make.write_text(f'#!/bin/bash\necho "docs failed"\nexit {make_exit}\n')
    for script in [pre_commit, make]:
        script.chmod(0o755)
    return env_dir
