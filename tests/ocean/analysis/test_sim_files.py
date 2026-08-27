import os

import pytest

from polaris.tasks.ocean.analysis.sim_files import (
    check_files_exist,
    expand_template,
    read_omega_config,
    year_range_key,
)


def test_year_range_key_is_zero_padded():
    """The range key matches the convention ncclimo uses in file names."""
    assert year_range_key(21, 40) == '0021-0040'
    assert year_range_key(1, 10) == '0001-0010'


def test_expand_template_over_years_and_months(tmp_path):
    """A template with $Y and $M gives one file per month, in order."""
    sim_files = expand_template(
        'output/ocn.hist.$Y-$M.nc', 3, 4, simulation_path=str(tmp_path)
    )
    assert len(sim_files) == 24
    assert sim_files[0].path == os.path.join(
        str(tmp_path), 'output/ocn.hist.0003-01.nc'
    )
    assert (sim_files[0].year, sim_files[0].month) == (3, 1)
    assert sim_files[-1].path == os.path.join(
        str(tmp_path), 'output/ocn.hist.0004-12.nc'
    )
    assert (sim_files[-1].year, sim_files[-1].month) == (4, 12)


def test_expand_template_over_years_only(tmp_path):
    """A template with $Y but no $M gives one file per year."""
    sim_files = expand_template(
        'stats.$Y.nc', 1, 3, simulation_path=str(tmp_path)
    )
    assert [sim_file.year for sim_file in sim_files] == [1, 2, 3]
    assert all(sim_file.month is None for sim_file in sim_files)


def test_expand_template_without_a_date(tmp_path):
    """Omega writes a run's analysis output to a single, undated file."""
    sim_files = expand_template(
        'global_stats_1DayInstants', 1, 60, simulation_path=str(tmp_path)
    )
    assert len(sim_files) == 1
    assert sim_files[0].path == os.path.join(
        str(tmp_path), 'global_stats_1DayInstants'
    )
    assert sim_files[0].year is None
    assert sim_files[0].month is None


def test_expand_template_absolute_ignores_simulation_path(tmp_path):
    """An absolute template is used as given."""
    template = str(tmp_path / 'elsewhere' / 'ocn.hist.$Y-$M.nc')
    sim_files = expand_template(template, 1, 1, simulation_path='/not/used')
    assert sim_files[0].path == str(
        tmp_path / 'elsewhere' / 'ocn.hist.0001-01.nc'
    )


def test_expand_template_relative_needs_a_simulation_path():
    """A relative template with nothing to resolve it against is an error."""
    with pytest.raises(ValueError, match='simulation_path'):
        expand_template('ocn.hist.$Y-$M.nc', 1, 1)


def test_expand_template_rejects_finer_date_fields(tmp_path):
    """Date fields finer than a month cannot be expanded."""
    with pytest.raises(ValueError, match=r'\$D'):
        expand_template(
            'restart/ocn.restart.$Y-$M-$D.nc',
            1,
            1,
            simulation_path=str(tmp_path),
        )


def test_expand_template_rejects_a_reversed_range(tmp_path):
    with pytest.raises(ValueError, match='after the end year'):
        expand_template('ocn.hist.$Y.nc', 5, 2, simulation_path=str(tmp_path))


def test_check_files_exist_passes_when_they_do(tmp_path):
    for month in range(1, 13):
        (tmp_path / f'ocn.hist.0001-{month:02d}.nc').touch()
    sim_files = expand_template(
        'ocn.hist.$Y-$M.nc', 1, 1, simulation_path=str(tmp_path)
    )
    check_files_exist(sim_files, 'monthly-mean', 'monthly_mean_template')


def test_check_files_exist_names_the_missing_months(tmp_path):
    """The error says which years and months are missing, and what to fix."""
    for month in range(1, 13):
        (tmp_path / f'ocn.hist.0001-{month:02d}.nc').touch()
    (tmp_path / 'ocn.hist.0002-01.nc').touch()
    sim_files = expand_template(
        'ocn.hist.$Y-$M.nc', 1, 2, simulation_path=str(tmp_path)
    )
    with pytest.raises(FileNotFoundError) as excinfo:
        check_files_exist(sim_files, 'monthly-mean', 'monthly_mean_template')
    message = str(excinfo.value)
    assert '11 of 24 monthly-mean files are missing' in message
    assert 'year 0002: months 02, 03, 04' in message
    assert 'year 0001' not in message
    assert 'monthly_mean_template' in message


def test_check_files_exist_reports_an_undated_file_by_path(tmp_path):
    sim_files = expand_template(
        'global_stats_1DayInstants', 1, 60, simulation_path=str(tmp_path)
    )
    with pytest.raises(FileNotFoundError) as excinfo:
        check_files_exist(
            sim_files, 'global statistics', 'global_stats_template'
        )
    assert 'global_stats_1DayInstants' in str(excinfo.value)


OMEGA_CONFIG = """\
Omega:
  IOStreams:
    HorzMeshIn:
      Filename: mesh.nc
      Mode: read
    InitialVertCoord:
      Filename: vert_coord.nc
      Mode: read
    RestartRead:
      UsePointerFile: true
      PointerFilename: ocn.pointer
      Mode: read
    History:
      Filename: output/ocn.hist.$Y-$M.nc
      Mode: write
      Freq: 1
      FreqUnits: months
  Analysis:
    GlobalStats:
      Enable: true
      Filename: global_stats
      ReductionPeriod: [1Month]
      SnapshotPeriod: [1Day]
    Moc:
      Enable: false
      Filename: moc
      ReductionPeriod: [1Month]
    Timeseries:
      Enable: true
      Filename: analysis.$Y.$M
      ReductionPeriod: [1Month]
"""


def _write_omega_config(tmp_path, text=OMEGA_CONFIG):
    filename = tmp_path / 'omega.yml'
    filename.write_text(text)
    return str(filename)


def test_read_omega_config_finds_streams(tmp_path):
    """The mesh, vertical coordinate and monthly means come from the config."""
    omega_config = read_omega_config(_write_omega_config(tmp_path))
    assert omega_config.stream_filename('HorzMeshIn') == 'mesh.nc'
    assert omega_config.stream_filename('InitialVertCoord') == 'vert_coord.nc'
    assert (
        omega_config.stream_filename('History') == 'output/ocn.hist.$Y-$M.nc'
    )


def test_read_omega_config_reports_what_it_cannot_supply(tmp_path):
    """An absent stream and a pointer-file stream are told apart."""
    omega_config = read_omega_config(_write_omega_config(tmp_path))
    assert omega_config.stream_status('History') == 'ok'
    assert omega_config.stream_status('Moc') == 'missing'
    assert omega_config.stream_status('RestartRead') == 'no_filename'
    assert omega_config.stream_filename('Moc') is None
    assert omega_config.stream_filename('RestartRead') is None


def test_read_omega_config_missing_file_names_the_option(tmp_path):
    with pytest.raises(FileNotFoundError, match='omega_config_filename'):
        read_omega_config(str(tmp_path / 'not_there.yml'))


def test_read_omega_config_rejects_a_foreign_file(tmp_path):
    filename = tmp_path / 'not_omega.yml'
    filename.write_text('mpas-ocean:\n  streams: {}\n')
    with pytest.raises(ValueError, match='does not look like an Omega'):
        read_omega_config(str(filename))


def test_analysis_group_status(tmp_path):
    """A group can be absent, turned off, or writing."""
    omega_config = read_omega_config(_write_omega_config(tmp_path))
    assert omega_config.analysis_group_status('GlobalStats') == 'ok'
    assert omega_config.analysis_group_status('Moc') == 'disabled'
    assert omega_config.analysis_group_status('Bogus') == 'missing'
    assert omega_config.analysis_streams('Moc') == []
    assert omega_config.analysis_streams('Bogus') == []


def test_analysis_streams_reconstruct_omega_file_names(tmp_path):
    """Time reductions come first, and snapshots are named differently."""
    omega_config = read_omega_config(_write_omega_config(tmp_path))
    streams = omega_config.analysis_streams('GlobalStats')
    assert [stream.filename for stream in streams] == [
        'global_stats_1MonthTimeStats',
        'global_stats_1DayInstants',
    ]
    assert [stream.is_reduction for stream in streams] == [True, False]
    assert [stream.period for stream in streams] == ['1Month', '1Day']


def test_analysis_streams_keep_a_timestamp_template(tmp_path):
    """The separator before the first $ moves into the timestamp template."""
    omega_config = read_omega_config(_write_omega_config(tmp_path))
    streams = omega_config.analysis_streams('Timeseries')
    assert streams[0].filename == 'analysis_1MonthTimeStats.$Y.$M'
