import pytest
from pr_test_config import ConfigError, RemoteMachine, read_config

SETTINGS = """[polaris_pr_test]
work_base = /scratch/polaris_pr_test
omega_repo = /home/me/Omega
"""


def test_read_config_without_machines(tmp_path):
    config = read_config(_write(tmp_path, SETTINGS))

    assert config.work_base == '/scratch/polaris_pr_test'
    assert config.machines == {}
    assert config.find_machine('chrysalis') is None
    assert config.polaris_main is None


def test_read_config_polaris_main(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    config = read_config(
        _write(tmp_path, f'{SETTINGS}polaris_main = ~/polaris/main\n')
    )

    assert config.polaris_main == str(tmp_path / 'polaris' / 'main')


def test_read_config_old_section(tmp_path):
    old = SETTINGS.replace('[polaris_pr_test]', '[omega_pr_test]')

    config = read_config(_write(tmp_path, old))

    assert config.work_base == '/scratch/polaris_pr_test'


def test_read_config_old_name(tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    (tmp_path / '.config').mkdir()
    old = tmp_path / '.config' / 'omega_pr_test.cfg'
    old.write_text(SETTINGS)

    with pytest.raises(ConfigError, match=f'mv {old} '):
        read_config()

    old.rename(tmp_path / '.config' / 'polaris_pr_test.cfg')
    assert read_config().work_base == '/scratch/polaris_pr_test'


def test_read_config_machines(tmp_path):
    config = read_config(
        _write(
            tmp_path,
            f'{SETTINGS}\n[machines]\n'
            'chrysalis = chrys:/home/me/polaris\n'
            'pm-gpu = pm: ~/polaris\n',
        )
    )

    assert config.find_machine('chrysalis') == RemoteMachine(
        'chrys', '/home/me/polaris'
    )
    # the path is the machine's to expand, not this computer's
    assert config.find_machine('pm-gpu') == RemoteMachine('pm', '~/polaris')
    # pm-cpu shares pm-gpu's login nodes
    assert config.find_machine('pm-cpu') == RemoteMachine('pm', '~/polaris')
    assert config.find_machine('aurora') is None


@pytest.mark.parametrize(
    'line, message',
    [
        ('perlmutter = pm:/polaris', 'not a Polaris machine'),
        ('default = pm:/polaris', 'not a Polaris machine'),
        ('aurora = <host>:/path/to/polaris', 'not as <ssh host>'),
        ('aurora = auro:polaris', 'not as <ssh host>'),
        ('aurora = auro', 'not as <ssh host>'),
        (
            'pm-cpu = pm:/polaris\npm-gpu = pm:/other',
            'tested from the same login nodes',
        ),
    ],
)
def test_read_config_bad_machines(tmp_path, line, message):
    filename = _write(tmp_path, f'{SETTINGS}\n[machines]\n{line}\n')

    with pytest.raises(ConfigError, match=message):
        read_config(filename)


def _write(tmp_path, text):
    path = tmp_path / 'polaris_pr_test.cfg'
    path.write_text(text)
    return str(path)
