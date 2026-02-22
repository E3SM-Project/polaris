import textwrap

import pytest

from polaris.constants.pcd import (
    check_pcd_version_matches_branch,
    get_constant,
    get_pcd_version,
    get_pcd_version_from_file,
)


@pytest.mark.parametrize(
    'name, expected',
    [
        ('pi', 3.141592653589793238462643),
        ('speed_of_light_in_vacuum', 299792458),
        ('total_solar_irradiance', 1360.8),
        ('water_triple_point_pressure', 611.655),
    ],
)
def test_get_constant_expected_values(name, expected):
    value = get_constant(name)
    if isinstance(expected, float):
        assert value == pytest.approx(expected)
    else:
        assert value == expected


def test_get_constant_missing_returns_none():
    assert get_constant('dummy_constant_that_does_not_exist') is None


def test_get_pcd_version_from_file(tmp_path):
    pcd_file = tmp_path / 'pcd.yaml'
    pcd_file.write_text(
        textwrap.dedent(
            """
            physical_constants_dictionary:
              version_number: 1.2.3
              set: []
            """
        ).strip()
        + '\n',
        encoding='utf-8',
    )

    assert get_pcd_version_from_file(str(pcd_file)) == '1.2.3'


def test_check_pcd_version_matches_branch_match(tmp_path):
    branch_dir = tmp_path / 'branch'
    share_dir = branch_dir / 'share'
    share_dir.mkdir(parents=True)
    version = get_pcd_version()

    (share_dir / 'pcd.yaml').write_text(
        textwrap.dedent(
            f"""
            physical_constants_dictionary:
              version_number: {version}
              set: []
            """
        ).strip()
        + '\n',
        encoding='utf-8',
    )

    check_pcd_version_matches_branch(str(branch_dir), model='omega')


def test_check_pcd_version_matches_branch_mismatch(tmp_path):
    branch_dir = tmp_path / 'branch'
    share_dir = branch_dir / 'share'
    share_dir.mkdir(parents=True)

    (share_dir / 'pcd.yaml').write_text(
        textwrap.dedent(
            """
            physical_constants_dictionary:
              version_number: 999.999.999
              set: []
            """
        ).strip()
        + '\n',
        encoding='utf-8',
    )

    with pytest.raises(ValueError, match='PCD version mismatch'):
        check_pcd_version_matches_branch(str(branch_dir), model='mpas-ocean')


def test_check_pcd_version_matches_branch_missing(tmp_path):
    branch_dir = tmp_path / 'branch'
    branch_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match='share/pcd.yaml'):
        check_pcd_version_matches_branch(str(branch_dir), model='omega')
