from datetime import datetime

import pytest

from polaris.config import PolarisConfigParser
from polaris.e3sm.init.inputdata import get_creation_date, set_creation_date

SECTION = 'inputs'


def test_a_date_already_set_is_kept(tmp_path):
    config = _config(tmp_path, creation_date='20240101')
    _record(tmp_path, config.filepath, '20230303')
    assert set_creation_date(config, SECTION) == '20240101'


def test_a_new_setup_keeps_the_date_the_work_directory_recorded(tmp_path):
    """
    Setting a work directory up again must not rename files already staged
    from it.
    """
    config = _config(tmp_path)
    _record(tmp_path, config.filepath, '20230303')
    assert set_creation_date(config, SECTION) == '20230303'
    assert get_creation_date(config, SECTION) == '20230303'


def test_the_record_can_be_in_another_config_file(tmp_path):
    config = _config(tmp_path)
    _record(tmp_path, 'other/shared.cfg', '20230303')
    date = set_creation_date(config, SECTION, recorded_in='other/shared.cfg')
    assert date == '20230303'


def test_with_no_record_the_date_is_today(tmp_path):
    config = _config(tmp_path)
    today = datetime.now().strftime('%Y%m%d')
    assert set_creation_date(config, SECTION) == today


def test_each_option_is_set_on_its_own(tmp_path):
    config = _config(tmp_path, ocean_creation_date='20240505')
    _record(tmp_path, config.filepath, '20230303')
    assert set_creation_date(config, SECTION) == '20230303'
    date = set_creation_date(config, SECTION, option='ocean_creation_date')
    assert date == '20240505'


def test_an_unset_option_is_reported_by_name():
    config = PolarisConfigParser()
    with pytest.raises(ValueError, match='ocean_creation_date'):
        get_creation_date(config, SECTION, 'ocean_creation_date')


def _config(tmp_path, creation_date='', ocean_creation_date=''):
    """A config as setup leaves it: the work directory, and blank dates."""
    path = tmp_path / 'defaults.cfg'
    path.write_text(
        f'[paths]\nbase_work_dir = {tmp_path}\n'
        f'[{SECTION}]\ncreation_date = {creation_date}\n'
        f'ocean_creation_date = {ocean_creation_date}\n'
    )
    config = PolarisConfigParser(filepath='component/inputs.cfg')
    config.add_from_file(str(path))
    return config


def _record(tmp_path, filepath, creation_date):
    """What an earlier setup wrote to the work directory."""
    path = tmp_path / filepath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[{SECTION}]\ncreation_date = {creation_date}\n')
