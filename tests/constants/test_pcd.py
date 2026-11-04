import textwrap

import pytest

from polaris.constants.pcd import (
    _evaluate_constants,
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
        ('seawater_specific_heat_capacity_teos10', 3991.86795711963),
        ('ocean_reference_salinity_teos10', 35.16504),
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


@pytest.mark.parametrize(
    'name, expected',
    [
        # Omega's Psu2Gpkg
        ('reference_salinity_per_practical_salinity_teos10', 35.16504 / 35.0),
        ('mean_radius', (2.0 * 6378137.0 + 6356752.3141) / 3.0),
        (
            'latent_heat_of_sublimation_reference',
            333700.0 + 2501000.0,
        ),
    ],
)
def test_get_constant_formula(name, expected):
    # formulas are evaluated in double precision exactly as written, so the
    # values are bit-for-bit those that the compiled models use
    assert get_constant(name) == expected


def test_evaluate_constants_out_of_order():
    entries = {
        'half_b': {'name': 'half_b', 'formula': 'b / 2'},
        'b': {'name': 'b', 'formula': '-(a + 1) ** 2'},
        'a': {'name': 'a', 'value': 3},
    }
    constants = _evaluate_constants(entries)
    assert constants == {'a': 3, 'b': -16.0, 'half_b': -8.0}


@pytest.mark.parametrize(
    'entries, match',
    [
        (
            {
                'a': {'name': 'a', 'formula': 'b'},
                'b': {'name': 'b', 'formula': '2 * a'},
            },
            'Circular dependency between PCD formulas: a -> b -> a',
        ),
        (
            {'a': {'name': 'a', 'formula': 'b + 1'}},
            'references unknown constant b',
        ),
        (
            {
                'a': {'name': 'a', 'value': 4.0},
                'b': {'name': 'b', 'formula': 'sqrt(a)'},
            },
            'unsupported syntax: sqrt\\(a\\)',
        ),
        (
            {'a': {'name': 'a', 'formula': "'1'"}},
            'unsupported syntax',
        ),
    ],
)
def test_evaluate_constants_errors(entries, match):
    with pytest.raises(ValueError, match=match):
        _evaluate_constants(entries)


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

    with pytest.warns(UserWarning, match='share/pcd.yaml'):
        check_pcd_version_matches_branch(str(branch_dir), model='omega')
