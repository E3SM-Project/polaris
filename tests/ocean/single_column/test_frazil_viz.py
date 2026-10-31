from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pytest
import xarray as xr

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.single_column.frazil import Frazil
from polaris.tasks.ocean.single_column.frazil.utils import FRAZIL_RATE_UNITS
from polaris.tasks.ocean.single_column.mpas_ocean_frazil_viz import (
    MPAS_OCEAN_FRAZIL_ACCUMULATED,
    MPAS_OCEAN_FRAZIL_TENDENCIES,
    mpas_ocean_frazil_data,
)
from polaris.tasks.ocean.single_column.viz import Viz


@pytest.mark.parametrize(
    'hours, expected',
    [
        ([0, 6, 12, 24, 30, 48, 54], [24, 48, 54]),
        ([1, 23, 25, 47, 49], [23, 47, 49]),
        ([0, 0.1, 0.2], [0.2]),
        ([24], [24]),
        ([24, 72], [24, 72]),
        ([24 + 1e-12, 48 + 1e-12, 50], [24 + 1e-12, 48 + 1e-12, 50]),
    ],
)
def test_daily_frazil_profiles(hours, expected):
    time = np.asarray(hours)
    shape = (len(time), 2, 2)
    ds = xr.Dataset(
        {
            'daysSinceStartOfSim': ('Time', time / 24.0),
            'layerThickness': (
                ('Time', 'nCells', 'nVertLevels'),
                np.ones(shape),
            ),
            'zMid': (
                ('Time', 'nCells', 'nVertLevels'),
                np.broadcast_to([-0.5, -1.5], shape),
            ),
        }
    )
    for field in MPAS_OCEAN_FRAZIL_TENDENCIES:
        ds[field] = (
            ('Time', 'nCells', 'nVertLevels'),
            np.broadcast_to(time[:, None, None], shape),
        )
    for field in MPAS_OCEAN_FRAZIL_ACCUMULATED:
        ds[field] = (
            ('Time', 'nCells'),
            np.broadcast_to(time[:, None], (len(time), 2)),
        )
    mesh = xr.Dataset({'areaCell': ('nCells', [1.0, 2.0])})

    data = mpas_ocean_frazil_data(ds, mesh)

    np.testing.assert_allclose(data['profile_hours'], expected)
    for field in MPAS_OCEAN_FRAZIL_TENDENCIES:
        np.testing.assert_allclose(
            data['profiles'][field],
            np.broadcast_to(np.asarray(expected)[:, None], (len(expected), 2)),
        )
    for field in MPAS_OCEAN_FRAZIL_ACCUMULATED:
        np.testing.assert_allclose(data['accumulated'][field], time)


@pytest.mark.parametrize('case', ['freezing', 'melting'])
def test_standard_omega_flux_history(case, monkeypatch, tmp_path):
    task = Frazil(Ocean(), f'column/frazil/{case}', case)
    task.config.set('ocean', 'model', 'omega')
    step = task.viz
    step.config = task.config
    hours = np.arange(1, 8) / 6.0
    ds = xr.Dataset({'daysSinceStartOfSim': ('Time', hours / 24.0)})
    for field in FRAZIL_RATE_UNITS:
        ds[field] = (('Time', 'nCells'), np.column_stack([hours, 3 * hours]))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(Viz, 'run', lambda self: None)
    monkeypatch.setattr(
        step, 'open_model_dataset', lambda *args, **kwargs: ds.copy()
    )
    with patch.object(plt, 'close'):
        step.run()
        fig = plt.gcf()
    try:
        assert len(fig.axes) == 3
        assert len(fig.axes[0].lines) == (3 if case == 'freezing' else 2)
        if case == 'freezing':
            np.testing.assert_allclose(
                np.asarray(fig.axes[0].lines[2].get_ydata(), dtype=float),
                task.config.getfloat(
                    'single_column_forcing', 'latent_heat_flux'
                ),
            )
        for ax in fig.axes:
            for line, name in zip(
                ax.lines[:2], ['FixedProperty', 'teos'], strict=True
            ):
                np.testing.assert_allclose(
                    np.asarray(line.get_xdata(), dtype=float), hours
                )
                np.testing.assert_allclose(
                    np.asarray(line.get_ydata(), dtype=float), 2 * hours
                )
                assert line.get_label() == name
        assert (tmp_path / 'frazil-fluxes.png').stat().st_size > 0
    finally:
        plt.close(fig)
    assert task.config.getfloat('single_column', 'output_interval') == (
        task.config.getfloat('single_column', 'time_step')
    )


def test_missing_omega_flux_is_reported(monkeypatch):
    task = Frazil(Ocean(), 'column/frazil/melting', 'melting')
    task.config.set('ocean', 'model', 'omega')
    task.viz.config = task.config
    monkeypatch.setattr(Viz, 'run', lambda self: None)
    monkeypatch.setattr(
        task.viz, 'open_model_dataset', lambda *args, **kwargs: xr.Dataset()
    )
    with pytest.raises(ValueError, match='Missing frazil flux fields'):
        task.viz.run()


def test_mpas_ocean_retains_generic_plots():
    task = Frazil(Ocean(), 'column/frazil/freezing', 'freezing')
    task.config.set('ocean', 'model', 'mpas-ocean')
    task.configure()
    task.viz.config = task.config
    with (
        patch.object(Viz, 'run') as generic_run,
        patch.object(task.viz, 'open_model_dataset') as open_dataset,
    ):
        task.viz.run()
    generic_run.assert_called_once()
    open_dataset.assert_not_called()
