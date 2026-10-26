import json
import os
import subprocess
import time

import pr_test_cleanup
import pr_test_github
import pytest

NOW = time.time()
OLD = NOW - 30 * 86400
POLARIS = 'c' * 40


def test_find_paths_leaves_out_urls():
    text = (
        'Logs are in `/scratch/me/pr1-abcdef0/build/build_omega.log`, '
        'see https://web.example.gov/public/me/plot.png and '
        '/scratch/me/pr2-1234567/.\n'
    )

    assert pr_test_cleanup.find_paths(text) == [
        '/scratch/me/pr1-abcdef0/build/build_omega.log',
        '/scratch/me/pr2-1234567',
    ]


def test_collect_citations(monkeypatch):
    texts = {
        'E3SM-Project/Omega': {5: ['in /a/b/c', 'and /a/d']},
        'E3SM-Project/polaris': {7: ['also /a/b/c']},
    }
    monkeypatch.setattr(
        pr_test_cleanup,
        'get_open_pull_request_texts',
        lambda repo: texts[repo],
    )

    assert pr_test_cleanup.collect_citations() == [
        ('/a/b/c', 'E3SM-Project/Omega#5'),
        ('/a/b/c', 'E3SM-Project/polaris#7'),
        ('/a/d', 'E3SM-Project/Omega#5'),
    ]


def test_citations_round_trip(tmp_path):
    filename = str(tmp_path / 'cited_paths.txt')
    pr_test_cleanup.write_citations(filename, [('/a/b', 'repo#1')])

    assert pr_test_cleanup.read_citations(filename) == {'/a/b'}


def test_read_citations_refuses_an_old_list(tmp_path):
    filename = str(tmp_path / 'cited_paths.txt')
    pr_test_cleanup.write_citations(filename, [('/a/b', 'repo#1')])
    later = NOW + (pr_test_cleanup.MAX_CITED_AGE_HOURS + 1) * 3600

    with pytest.raises(pr_test_cleanup.CleanupError, match='hours ago'):
        pr_test_cleanup.read_citations(filename, now=later)


def test_read_citations_needs_a_list(tmp_path):
    with pytest.raises(pr_test_cleanup.CleanupError, match='cited command'):
        pr_test_cleanup.read_citations(str(tmp_path / 'missing.txt'))

    other = tmp_path / 'other.txt'
    other.write_text('/a/b\n')
    with pytest.raises(pr_test_cleanup.CleanupError, match='not written'):
        pr_test_cleanup.read_citations(str(other))


def test_plan_cleanup(tmp_path):
    work_base = str(tmp_path)
    cited_run = _run(work_base, 'pr1-1111111', baseline='b_omega-aaaaaaa')
    old_run = _run(work_base, 'pr2-2222222', baseline='b_omega-bbbbbbb')
    moved_aside = _run(work_base, 'pr2-2222222.polaris-0000000')
    new_run = _run(work_base, 'pr3-3333333', tree='3' * 12, recent=True)
    used = _baseline(work_base, 'b_omega-aaaaaaa', tree='a' * 12)
    unused = _baseline(work_base, 'b_omega-bbbbbbb')
    current = _baseline(work_base, f'm_c_polaris-{POLARIS[:7]}_omega-ccccccc')
    trees = {
        name: _tree(work_base, name * 12) for name in ['a', 'b', 'c', '3', 'd']
    }
    stale_marker = os.path.join(work_base, 'omega', 'e' * 12 + '.ready')
    _touch(stale_marker)
    notes = os.path.join(work_base, 'notes.md')
    _touch(notes)
    cited = {
        os.path.join(cited_run, 'm_c', 'build', 'build_omega.log'),
        work_base,
    }

    entries = pr_test_cleanup.plan_cleanup(
        work_base, cited, keep_days=3, polaris_hashes=[POLARIS], now=NOW
    )

    keep = {entry.path: entry.keep for entry in entries}
    assert str(keep[cited_run]).startswith('cited: ')
    assert keep[old_run] is None
    assert keep[moved_aside] is None
    assert keep[new_run] == 'modified recently'
    assert keep[used] == 'the baseline of a kept run'
    assert keep[unused] is None
    assert keep[current] == 'for the current Polaris commit'
    # the baseline of the cited run, by name and by its build
    assert keep[trees['a']] == 'used by a kept run or baseline'
    assert keep[trees['b']] is None
    # the current baseline's commit
    assert keep[trees['c']] == 'used by a kept run or baseline'
    # made in the last few days
    assert keep[trees['3']] is not None
    assert keep[trees['d']] is None
    assert keep[stale_marker] is None
    # anything else is not the utility's
    assert notes not in keep


def test_remove(tmp_path):
    clone = tmp_path / 'clone'
    clone.mkdir()
    _git(clone, 'init', '--quiet')
    _git(clone, 'commit', '--quiet', '--allow-empty', '-m', 'first')
    work_base = tmp_path / 'work_base'
    tree = work_base / 'omega' / ('f' * 12)
    tree.parent.mkdir(parents=True)
    _git(clone, 'worktree', 'add', '--quiet', '--detach', str(tree))
    _touch(f'{tree}.ready')
    run = _run(str(work_base), 'pr1-1111111')
    kept = _run(str(work_base), 'pr2-2222222')
    marker = str(work_base / 'omega' / ('e' * 12 + '.ready'))
    _touch(marker)
    entries = [
        pr_test_cleanup.Entry(str(tree), 'worktree'),
        pr_test_cleanup.Entry(run, 'run'),
        pr_test_cleanup.Entry(kept, 'run', keep='modified recently'),
        pr_test_cleanup.Entry(marker, 'marker'),
    ]

    removed = pr_test_cleanup.remove(entries)

    assert removed == [str(tree), run, marker]
    assert not tree.exists()
    assert not os.path.exists(f'{tree}.ready')
    assert os.path.exists(kept)
    assert str(tree) not in _git(clone, 'worktree', 'list')

    text = pr_test_cleanup.format_plan(entries, str(work_base), True)
    assert 'Removed (3):\n  omega/ffffffffffff\n' in text
    assert 'pr2-2222222  (modified recently)' in text


def test_get_open_pull_request_texts(monkeypatch):
    monkeypatch.setattr(pr_test_github, 'gh_usable', lambda: False)
    pages = {
        'repos/r/pulls?state=open&per_page=100': [
            [{'number': 5, 'body': 'description'}]
        ],
        'repos/r/issues/5/comments?per_page=100': [[{'body': 'comment'}]],
        'repos/r/pulls/5/reviews?per_page=100': [[{'body': None}]],
        'repos/r/pulls/5/comments?per_page=100': [[{'body': 'inline'}]],
    }
    monkeypatch.setattr(pr_test_github, 'api_get', lambda path: pages[path])

    assert pr_test_github.get_open_pull_request_texts('r') == {
        5: ['description', 'comment', '', 'inline']
    }


def _run(work_base, name, baseline=None, tree=None, recent=False):
    """A run with one row, its setup state and its PR build"""
    row_dir = os.path.join(work_base, name, 'm_c')
    build_dir = os.path.join(row_dir, 'build')
    os.makedirs(build_dir)
    state = {'pr_build_dir': build_dir}
    if baseline is not None:
        state['baseline_work_dir'] = os.path.join(
            work_base, 'baselines', baseline, 'omega_pr'
        )
    with open(os.path.join(row_dir, 'setup.json'), 'w') as f:
        json.dump(state, f)
    if tree is not None:
        _cmake_cache(build_dir, os.path.join(work_base, 'omega', tree))
    _age(os.path.join(work_base, name), NOW if recent else OLD)
    return os.path.join(work_base, name)


def _baseline(work_base, name, tree=None):
    path = os.path.join(work_base, 'baselines', name)
    os.makedirs(os.path.join(path, 'build'))
    os.makedirs(os.path.join(path, 'omega_pr'))
    if tree is not None:
        _cmake_cache(
            os.path.join(path, 'build'),
            os.path.join(work_base, 'omega', tree),
        )
    _age(path, OLD)
    return path


def _tree(work_base, name):
    path = os.path.join(work_base, 'omega', name)
    os.makedirs(os.path.join(path, 'components', 'omega'))
    _touch(f'{path}.ready')
    recent = name.startswith('3')
    _age(path, NOW if recent else OLD)
    _age(f'{path}.ready', NOW if recent else OLD)
    return path


def _cmake_cache(build_dir, tree):
    with open(os.path.join(build_dir, 'CMakeCache.txt'), 'w') as f:
        f.write(
            f'OmegaOceanModel_SOURCE_DIR:STATIC='
            f'{os.path.join(tree, "components", "omega")}\n'
        )


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w'):
        pass


def _age(path, when):
    """Set the modification time of a path and everything in it"""
    for root, dirs, files in os.walk(path):
        for name in dirs + files:
            os.utime(os.path.join(root, name), (when, when))
    os.utime(path, (when, when))


def _git(repo, *args):
    env = dict(
        os.environ,
        GIT_CONFIG_GLOBAL='/dev/null',
        GIT_AUTHOR_NAME='a',
        GIT_AUTHOR_EMAIL='a@example.com',
        GIT_COMMITTER_NAME='a',
        GIT_COMMITTER_EMAIL='a@example.com',
    )
    return subprocess.run(
        ['git'] + list(args),
        cwd=repo,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
