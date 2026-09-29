from polaris.run.serial import _write_output_for_pull_request

POLARIS_A = {'hash': 'a' * 40, 'describe': '1.0.0-801-gaaaaaaaaa'}
POLARIS_B = {'hash': 'b' * 40, 'describe': '1.0.0-790-gbbbbbbbbb'}
OMEGA_BASE = {'hash': 'c' * 40, 'describe': 'Omega-v0.1.0-5500-gccccccccc'}
OMEGA_PR = {'hash': 'd' * 40, 'describe': 'Omega-v0.1.0-5510-gddddddddd'}


def test_commits_with_shared_polaris(tmp_path, monkeypatch):
    baseline_dir = _write_provenance(
        tmp_path / 'baseline', POLARIS_A, OMEGA_BASE
    )
    pr_dir = _write_provenance(
        tmp_path / 'pr', POLARIS_A, OMEGA_PR, baseline_dir=baseline_dir
    )

    lines = _write_summary(pr_dir, monkeypatch)

    assert f'- Polaris: `{"a" * 40}` (`1.0.0-801-gaaaaaaaaa`)' in lines
    assert (
        f'- Baseline Omega: `{"c" * 40}` (`Omega-v0.1.0-5500-gccccccccc`)'
        in lines
    )
    assert (
        f'- PR Omega: `{"d" * 40}` (`Omega-v0.1.0-5510-gddddddddd`)' in lines
    )
    assert not any('Baseline Polaris' in line for line in lines)
    assert f'- Baseline build: `{tmp_path / "baseline" / "build"}`' in lines

    details = lines[lines.index('<details>') :]
    assert details == [
        '<details>',
        '<summary>Recent commits</summary>',
        '',
        'Polaris:',
        '```',
        'aaaaaaaaa Merge pull request #1 from someone/branch',
        'aaaaaaaa0 machine: update chrysalis',
        '```',
        'Baseline Omega:',
        '```',
        'ccccccccc Merge pull request #1 from someone/branch',
        'cccccccc0 machine: update chrysalis',
        '```',
        'PR Omega:',
        '```',
        'ddddddddd Merge pull request #1 from someone/branch',
        'dddddddd0 machine: update chrysalis',
        '```',
        '</details>',
    ]


def test_commits_with_different_polaris(tmp_path, monkeypatch):
    baseline_dir = _write_provenance(
        tmp_path / 'baseline', POLARIS_B, OMEGA_BASE
    )
    pr_dir = _write_provenance(
        tmp_path / 'pr', POLARIS_A, OMEGA_PR, baseline_dir=baseline_dir
    )

    lines = _write_summary(pr_dir, monkeypatch)

    assert f'- Baseline Polaris: `{"b" * 40}` (`1.0.0-790-gbbbbbbbbb`)' in (
        lines
    )
    assert f'- PR Polaris: `{"a" * 40}` (`1.0.0-801-gaaaaaaaaa`)' in lines
    assert not any(line.startswith('- Polaris:') for line in lines)


def test_commit_at_setup_is_marked(tmp_path, monkeypatch):
    pr_dir = _write_provenance(
        tmp_path / 'pr', POLARIS_A, OMEGA_PR, at_setup=True
    )

    lines = _write_summary(pr_dir, monkeypatch)

    assert (
        f'- PR Omega: `{"d" * 40}` (`Omega-v0.1.0-5510-gddddddddd`) '
        '(at setup, not build)' in lines
    )
    assert not any('Baseline' in line for line in lines)


def test_commits_from_old_provenance(tmp_path, monkeypatch):
    pr_dir = tmp_path / 'pr'
    pr_dir.mkdir()
    (pr_dir / 'provenance').write_text(
        'polaris git version: 1.0.0-700-g1234567\n\n'
        'component git version: Omega-v0.1.0-5000-g7654321\n\n'
        'machine: chrysalis\n\n'
        'tasks:\n',
        encoding='utf-8',
    )

    lines = _write_summary(pr_dir, monkeypatch)

    assert '- Polaris: `1.0.0-700-g1234567`' in lines
    assert '- PR Component: `Omega-v0.1.0-5000-g7654321`' in lines
    assert '<details>' not in lines


def _write_summary(pr_dir, monkeypatch):
    monkeypatch.delenv('SLURM_JOB_ID', raising=False)
    suite = {'work_dir': str(pr_dir), 'tasks': {}}
    results = {'total': 1, 'failures': [], 'diffs': []}
    _write_output_for_pull_request('omega_pr', suite, results)
    text = (pr_dir / 'omega_pr_output_for_pr.md').read_text(encoding='utf-8')
    return text.splitlines()


def _write_provenance(
    work_dir, polaris, omega, baseline_dir=None, at_setup=False
):
    work_dir.mkdir()
    marker = ' (at setup, not build)' if at_setup else ''
    lines = []
    lines.extend(_git_entries('polaris', polaris, ''))
    lines.extend(_git_entries('component', omega, marker))
    lines.append('command: polaris suite -c ocean -t omega_pr --model omega')
    lines.append('')
    lines.append('machine: chrysalis')
    lines.append('')
    lines.append('compiler: intel')
    lines.append('')
    lines.append('model: omega')
    lines.append('')
    lines.append(f'work directory: {work_dir}')
    lines.append('')
    lines.append(f'build directory: {work_dir / "build"}')
    lines.append('')
    if baseline_dir is not None:
        lines.append(f'baseline work directory: {baseline_dir}')
        lines.append('')
    lines.append('tasks:')
    (work_dir / 'provenance').write_text(
        '\n'.join(lines) + '\n', encoding='utf-8'
    )
    return work_dir


def _git_entries(name, info, marker):
    short = info['hash'][:9]
    # a second commit whose subject looks like a provenance key
    second = f'{info["hash"][:8]}0'
    return [
        f'{name} git version: {info["describe"]}{marker}',
        '',
        f'{name} git hash: {info["hash"]}{marker}',
        '',
        f'{name} git log:{marker}',
        f'  {short} Merge pull request #1 from someone/branch',
        f'  {second} machine: update chrysalis',
        '',
    ]
