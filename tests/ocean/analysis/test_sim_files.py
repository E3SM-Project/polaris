import os

import pytest

from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.analysis.sim_files import (
    SimulationFiles,
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
    check_files_exist(sim_files, 'monthly-mean', 'the History stream')


def test_check_files_exist_names_the_missing_months(tmp_path):
    """The error says which years and months are missing, and what to fix."""
    for month in range(1, 13):
        (tmp_path / f'ocn.hist.0001-{month:02d}.nc').touch()
    (tmp_path / 'ocn.hist.0002-01.nc').touch()
    sim_files = expand_template(
        'ocn.hist.$Y-$M.nc', 1, 2, simulation_path=str(tmp_path)
    )
    with pytest.raises(FileNotFoundError) as excinfo:
        check_files_exist(sim_files, 'monthly-mean', 'the History stream')
    message = str(excinfo.value)
    assert '11 of 24 monthly-mean files are missing' in message
    assert 'year 0002: months 02, 03, 04' in message
    assert 'year 0001' not in message
    assert 'the History stream' in message


def test_check_files_exist_reports_an_undated_file_by_path(tmp_path):
    sim_files = expand_template(
        'global_stats_1DayInstants', 1, 60, simulation_path=str(tmp_path)
    )
    with pytest.raises(FileNotFoundError) as excinfo:
        check_files_exist(
            sim_files, 'global statistics', 'the GlobalStats group'
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


def _make_config(model='omega', **options):
    """Build a config with the analysis defaults and the given overrides."""
    config = PolarisConfigParser()
    config.add_from_package('polaris.ocean', 'ocean.cfg')
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')
    config.set('ocean', 'model', model)
    for option, value in options.items():
        config.set('ocean_analysis', option, value)
    return config


def _make_simulation(tmp_path, text=OMEGA_CONFIG):
    """Write an Omega config and the output files it names."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    omega_config_filename = _write_omega_config(tmp_path, text)
    (tmp_path / 'mesh.nc').touch()
    (tmp_path / 'vert_coord.nc').touch()
    (tmp_path / 'output').mkdir()
    for month in range(1, 13):
        (tmp_path / 'output' / f'ocn.hist.0001-{month:02d}.nc').touch()
    (tmp_path / 'global_stats_1MonthTimeStats').touch()
    return omega_config_filename


def test_simulation_files_come_from_the_omega_config(tmp_path):
    """The Omega config is the only description of where the output lives."""
    omega_config_filename = _make_simulation(tmp_path)
    config = _make_config(omega_config_filename=omega_config_filename)
    messages: list = []
    sim = SimulationFiles(config, log=messages.append)

    assert sim.simulation_path == str(tmp_path)
    assert sim.mesh_filename() == str(tmp_path / 'mesh.nc')
    assert sim.vert_coord_filename() == str(tmp_path / 'vert_coord.nc')
    monthly = sim.monthly_mean_files(1, 1)
    assert len(monthly) == 12
    assert monthly[0].path == str(tmp_path / 'output' / 'ocn.hist.0001-01.nc')
    stats = sim.global_stats_files(1, 1)
    assert [sim_file.path for sim_file in stats] == [
        str(tmp_path / 'global_stats_1MonthTimeStats')
    ]
    assert any('HorzMeshIn stream' in message for message in messages)
    assert any('1Month time-mean stream' in message for message in messages)


def test_a_mesh_option_beats_the_omega_config(tmp_path):
    """A mesh that has moved since the run can be pointed at by hand."""
    omega_config_filename = _make_simulation(tmp_path)
    elsewhere = tmp_path / 'elsewhere'
    elsewhere.mkdir()
    (elsewhere / 'moved_mesh.nc').touch()
    config = _make_config(
        omega_config_filename=omega_config_filename,
        mesh_filename=str(elsewhere / 'moved_mesh.nc'),
    )
    messages: list = []
    sim = SimulationFiles(config, log=messages.append)

    assert sim.mesh_filename() == str(elsewhere / 'moved_mesh.nc')
    assert any(
        'from [ocean_analysis] mesh_filename' in message
        for message in messages
    )


def test_simulation_path_can_be_set_by_hand(tmp_path):
    """Output that has moved away from the config file is still reachable."""
    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    omega_config_filename = _write_omega_config(config_dir)
    _make_simulation(tmp_path / 'run')
    config = _make_config(
        omega_config_filename=omega_config_filename,
        simulation_path=str(tmp_path / 'run'),
    )
    sim = SimulationFiles(config, log=lambda message: None)
    assert sim.mesh_filename() == str(tmp_path / 'run' / 'mesh.nc')


def test_missing_moc_output_is_reported_not_raised(tmp_path):
    """A simulation that predates Omega's MOC diagnostic is an ordinary
    case."""
    text = OMEGA_CONFIG.replace(
        '    Moc:\n      Enable: false\n'
        '      Filename: moc\n      ReductionPeriod: [1Month]\n',
        '',
    )
    omega_config_filename = _make_simulation(tmp_path, text)
    config = _make_config(omega_config_filename=omega_config_filename)
    messages: list = []
    sim = SimulationFiles(config, log=messages.append)

    assert sim.moc_files(1, 1) is None
    assert any(
        'no meridional overturning circulation output' in message
        for message in messages
    )
    assert any('no Moc analysis group' in message for message in messages)


def test_a_disabled_moc_group_is_reported_not_raised(tmp_path):
    omega_config_filename = _make_simulation(tmp_path)
    config = _make_config(omega_config_filename=omega_config_filename)
    messages: list = []
    sim = SimulationFiles(config, log=messages.append)

    assert sim.moc_files(1, 1) is None
    assert any('is turned off' in message for message in messages)


def test_missing_global_stats_output_is_an_error(tmp_path):
    """Global statistics are required, so their absence is reported loudly."""
    text = OMEGA_CONFIG.replace(
        'GlobalStats:\n      Enable: true', 'GlobalStats:\n      Enable: false'
    )
    omega_config_filename = _make_simulation(tmp_path, text)
    config = _make_config(omega_config_filename=omega_config_filename)
    sim = SimulationFiles(config, log=lambda message: None)
    with pytest.raises(ValueError, match='is turned off'):
        sim.global_stats_files(1, 1)


def test_an_omega_config_is_required(tmp_path):
    """An Omega run always writes one, so its absence is an error."""
    config = _make_config()
    with pytest.raises(ValueError, match='omega_config_filename'):
        SimulationFiles(config, log=lambda message: None)


def test_mpas_ocean_is_not_supported(tmp_path):
    """Reading MPAS-Ocean output would need a translator we have not
    written."""
    omega_config_filename = _make_simulation(tmp_path)
    config = _make_config(
        model='mpas-ocean', omega_config_filename=omega_config_filename
    )
    with pytest.raises(ValueError, match='MPAS-Ocean output is not'):
        SimulationFiles(config, log=lambda message: None)
