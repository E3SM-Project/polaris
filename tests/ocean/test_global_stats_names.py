import numpy as np
import pytest
import xarray as xr

from polaris.ocean.global_stats_names import (
    GLOBAL_STATS,
    available_stats,
    global_stats_var_names,
    select_global_stats,
)

# what mpaso_to_omega.yaml gives for the fields in the default list
OMEGA_FIELDS = {
    'temperature': 'Temperature',
    'salinity': 'Salinity',
    'normalVelocity': 'NormalVelocity',
    'kineticEnergyCell': 'KineticEnergyCell',
    'ssh': 'SshCell',
}


def make_dataset(var_names):
    """A dataset holding one time series per name, as the models write them"""
    time = np.arange(5.0)
    ds = xr.Dataset(coords={'Time': ('Time', time)})
    for var_name in var_names:
        ds[var_name] = ('Time', time)
    return ds


def test_the_two_models_compute_different_statistics():
    """MPAS-Ocean writes a root-mean-square where Omega writes an SD."""
    assert 'rms' in available_stats('mpas-ocean')
    assert 'std' not in available_stats('mpas-ocean')
    assert 'std' in available_stats('omega')
    assert 'rms' not in available_stats('omega')
    # what they do share, they share
    for stat in ['min', 'max', 'mean']:
        assert stat in available_stats('mpas-ocean')
        assert stat in available_stats('omega')


def test_unknown_model_raises():
    with pytest.raises(ValueError, match='mpas-atmosphere'):
        available_stats('mpas-atmosphere')


def test_omega_snapshot_var_names():
    """Snapshots carry no period, which is how the mock-up writes them."""
    var_names = global_stats_var_names(
        fields=['temperature', 'ssh'],
        stats=['mean', 'min', 'max', 'std'],
        model='omega',
        field_map=OMEGA_FIELDS,
    )
    assert var_names[('temperature', 'mean')] == 'Temperature_SpatialMean'
    assert var_names[('temperature', 'min')] == 'Temperature_SpatialMin'
    assert var_names[('temperature', 'max')] == 'Temperature_SpatialMax'
    assert var_names[('temperature', 'std')] == 'Temperature_SpatialStdDev'
    assert var_names[('ssh', 'mean')] == 'SshCell_SpatialMean'


def test_omega_time_mean_var_names():
    """A time reduction adds the period the variables were averaged over."""
    var_names = global_stats_var_names(
        fields=['temperature', 'kineticEnergyCell'],
        stats=['mean', 'std'],
        model='omega',
        field_map=OMEGA_FIELDS,
        time_mean_period='1Month',
    )
    assert (
        var_names[('temperature', 'mean')]
        == 'Temperature_SpatialMean_TimeMean1Month'
    )
    assert (
        var_names[('kineticEnergyCell', 'std')]
        == 'KineticEnergyCell_SpatialStdDev_TimeMean1Month'
    )


def test_mpas_ocean_var_names():
    """MPAS-Ocean appends the statistic to the field with no separator."""
    var_names = global_stats_var_names(
        fields=['temperature', 'layerThickness'],
        stats=['min', 'max', 'mean', 'rms'],
        model='mpas-ocean',
    )
    assert var_names[('temperature', 'min')] == 'temperatureMin'
    assert var_names[('temperature', 'max')] == 'temperatureMax'
    assert var_names[('temperature', 'mean')] == 'temperatureAvg'
    assert var_names[('temperature', 'rms')] == 'temperatureRms'
    assert var_names[('layerThickness', 'mean')] == 'layerThicknessAvg'


def test_mpas_ocean_writes_no_time_means():
    with pytest.raises(ValueError, match='1Month'):
        global_stats_var_names(
            fields=['temperature'],
            stats=['mean'],
            model='mpas-ocean',
            time_mean_period='1Month',
        )


def test_a_statistic_the_model_does_not_compute_raises():
    """Asking Omega for an RMS is a mistake in the caller, not a subset."""
    with pytest.raises(ValueError, match='rms'):
        global_stats_var_names(
            fields=['temperature'], stats=['rms'], model='omega'
        )
    with pytest.raises(ValueError, match='std'):
        global_stats_var_names(
            fields=['temperature'], stats=['std'], model='mpas-ocean'
        )


def test_unmapped_field_keeps_its_name():
    """A field only one model has has no map entry, so its name is used."""
    var_names = global_stats_var_names(
        fields=['PseudoThickness'],
        stats=['mean'],
        model='omega',
        field_map=OMEGA_FIELDS,
    )
    assert (
        var_names[('PseudoThickness', 'mean')] == 'PseudoThickness_SpatialMean'
    )


def test_var_names_keep_the_configured_order():
    """The plots come out in the order the config file asked for."""
    var_names = global_stats_var_names(
        fields=['ssh', 'temperature'],
        stats=['max', 'mean'],
        model='omega',
        field_map=OMEGA_FIELDS,
    )
    assert list(var_names) == [
        ('ssh', 'max'),
        ('ssh', 'mean'),
        ('temperature', 'max'),
        ('temperature', 'mean'),
    ]


def test_a_missing_statistic_is_skipped():
    """A statistic the simulation did not write is dropped, not raised on."""
    ds = make_dataset(
        [
            'Temperature_SpatialMean',
            'Temperature_SpatialMin',
            'SshCell_SpatialMean',
        ]
    )
    messages: list = []
    found = select_global_stats(
        ds=ds,
        fields=['temperature', 'ssh'],
        stats=['mean', 'min'],
        model='omega',
        field_map=OMEGA_FIELDS,
        log=messages.append,
    )
    assert found['temperature'] == {
        'mean': 'Temperature_SpatialMean',
        'min': 'Temperature_SpatialMin',
    }
    assert found['ssh'] == {'mean': 'SshCell_SpatialMean'}
    assert any('SshCell_SpatialMin' in message for message in messages)


def test_a_field_with_no_statistics_is_dropped():
    """A field the simulation did not write at all does not get a plot."""
    ds = make_dataset(['Temperature_SpatialMean'])
    messages: list = []
    found = select_global_stats(
        ds=ds,
        fields=['temperature', 'ssh'],
        stats=['mean'],
        model='omega',
        field_map=OMEGA_FIELDS,
        log=messages.append,
    )
    assert list(found) == ['temperature']
    assert any('no statistics of ssh' in message for message in messages)


def test_nothing_found_raises():
    """None of them is a step reading the wrong thing, so it interrupts."""
    ds = make_dataset(['Salinity_SpatialMean'])
    with pytest.raises(ValueError, match='years 21 through 40'):
        select_global_stats(
            ds=ds,
            fields=['temperature', 'ssh'],
            stats=['mean', 'min'],
            model='omega',
            field_map=OMEGA_FIELDS,
            source='stats.nc',
            hint='Check that years 21 through 40 are years it covers.',
        )


def test_selection_keeps_the_configured_order():
    ds = make_dataset(
        [
            'SshCell_SpatialMean',
            'Temperature_SpatialMean',
            'Temperature_SpatialMax',
        ]
    )
    found = select_global_stats(
        ds=ds,
        fields=['ssh', 'temperature'],
        stats=['max', 'mean'],
        model='omega',
        field_map=OMEGA_FIELDS,
    )
    assert list(found) == ['ssh', 'temperature']
    assert list(found['temperature']) == ['max', 'mean']


def test_default_stats_are_all_ones_omega_computes():
    """The stats in analysis.cfg are all ones Omega computes."""
    for stat in ['mean', 'min', 'max', 'std']:
        assert stat in GLOBAL_STATS['omega']
