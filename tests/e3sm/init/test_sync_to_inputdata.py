import os
import shutil
import subprocess

import pytest

import polaris.e3sm.init as package
from polaris.e3sm.init.assemble import SYNC_SCRIPT
from polaris.e3sm.init.inputdata import ASSEMBLED_FILES


@pytest.mark.skipif(
    shutil.which('rsync') is None, reason='rsync is not installed'
)
def test_the_sync_script_copies_and_sets_permissions(tmp_path):
    """
    Files land as real files rather than the symlinks the staged tree is made
    of, directories come out 2775 (setgid, as inputdata directories are) and
    files 664.
    """
    work_dir = tmp_path / 'assemble' / 'all'
    staged_dir = work_dir / ASSEMBLED_FILES / 'inputdata' / 'ocn' / 'mpas-o'
    staged_dir.mkdir(parents=True)

    product = tmp_path / 'product.nc'
    product.write_text('contents')
    (staged_dir / 'staged.nc').symlink_to(product)

    script = work_dir / SYNC_SCRIPT
    script.symlink_to(_sync_script_source())

    dest = tmp_path / 'inputdata'
    dest.mkdir()
    subprocess.run(['bash', str(script), str(dest)], check=True)

    copied = dest / 'ocn' / 'mpas-o' / 'staged.nc'
    assert copied.is_file() and not copied.is_symlink()
    assert copied.read_text() == 'contents'
    assert oct(copied.stat().st_mode)[-3:] == '664'
    assert oct((dest / 'ocn' / 'mpas-o').stat().st_mode)[-4:] == '2775'


@pytest.mark.skipif(
    shutil.which('rsync') is None, reason='rsync is not installed'
)
def test_the_sync_script_dry_run_copies_nothing(tmp_path):
    """
    A dry run lists what would be synced and leaves the destination as it was.
    """
    work_dir = tmp_path / 'assemble' / 'all'
    staged_dir = work_dir / ASSEMBLED_FILES / 'inputdata' / 'ocn' / 'mpas-o'
    staged_dir.mkdir(parents=True)

    product = tmp_path / 'product.nc'
    product.write_text('contents')
    (staged_dir / 'staged.nc').symlink_to(product)

    script = work_dir / SYNC_SCRIPT
    script.symlink_to(_sync_script_source())

    dest = tmp_path / 'inputdata'
    dest.mkdir()
    result = subprocess.run(
        ['bash', str(script), '--dry-run', str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )

    assert 'staged.nc' in result.stdout
    assert list(dest.iterdir()) == []


@pytest.mark.skipif(
    shutil.which('rsync') is None, reason='rsync is not installed'
)
def test_the_sync_script_refuses_a_destination_that_is_not_there(tmp_path):
    """
    An inputdata directory is curated by someone else; a typo should stop the
    copy rather than create a new tree next to the real one.
    """
    work_dir = tmp_path / 'assemble' / 'all'
    (work_dir / ASSEMBLED_FILES / 'inputdata').mkdir(parents=True)
    script = work_dir / SYNC_SCRIPT
    script.symlink_to(_sync_script_source())

    result = subprocess.run(
        ['bash', str(script), str(tmp_path / 'typo')],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert 'does not exist' in result.stderr

    result = subprocess.run(
        ['bash', str(script)], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert 'usage' in result.stderr


def _sync_script_source():
    """
    The script as it ships in the package.
    """
    return os.path.join(os.path.dirname(package.__file__), SYNC_SCRIPT)
