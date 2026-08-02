"""
Time series of the spurious circulation, one set per pressure-gradient
scheme that was run.

The exact solution is a resting ocean, so every velocity in this task is
error.  What the metrics have to answer is how much of it there is, where it
sits in the water column, and how the schemes compare on a shared initial
condition.

No thresholds are applied.  They are meant to be set from what these metrics
measure rather than in advance, and a threshold guessed before the first
measurement is a guard that either cannot fail or fails for the wrong reason.
"""

import cmocean  # noqa: F401
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris.ocean.model import OceanIOStep, get_days_since_start

# The metrics written to metrics.csv, in order, with the column headings and
# the units they are reported in
METRIC_UNITS = {
    'max_speed': 'm/s',
    'max_speed_level': '0-based level index',
    'max_speed_bottom': 'm/s',
    'mean_kinetic_energy': 'm2/s2',
    'implied_acceleration': 'm/s2',
    'acceleration_ratio': '1',
}


class Analysis(OceanIOStep):
    """
    A step for measuring the spurious circulation in each seamount forward
    run and comparing the pressure-gradient schemes against each other.

    Attributes
    ----------
    forward_steps : dict
        The name of the forward step for each pressure-gradient scheme,
        keyed by the scheme
    """

    def __init__(self, component, indir, forward_steps):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            the directory the step is in, to which ``name`` will be appended

        forward_steps : dict
            The name of the forward step for each pressure-gradient scheme,
            keyed by the scheme
        """
        super().__init__(component=component, name='analysis', indir=indir)
        self.forward_steps = dict(forward_steps)

        self.add_input_file(
            filename='mesh.nc', target='../../init/culled_mesh.nc'
        )
        self.add_input_file(filename='init.nc', target='../../init/init.nc')
        self.add_vert_coord_input_file(target='../../init/vert_coord.nc')
        for scheme, step_name in self.forward_steps.items():
            self.add_input_file(
                filename=f'output_{scheme}.nc',
                target=f'../{step_name}/output.nc',
            )

        self.add_output_file('metrics.csv')

    def run(self):
        """
        Run this step of the task
        """
        config = self.config
        logger = self.logger

        ds_mesh = self.open_model_dataset('mesh.nc', config)
        ds_init = self.open_model_dataset('init.nc', config)
        ds_vert_coord = self.open_vert_coord_dataset(ds_init)

        coriolis = np.abs(config.getfloat('coriolis', 'constant_f'))
        reference_grad = config.getfloat(
            'seamount', 'reference_bottom_pressure_grad'
        )

        metrics = dict()
        for scheme in self.forward_steps:
            ds = self.open_model_dataset(
                f'output_{scheme}.nc', config, decode_times=True
            )
            metrics[scheme] = _compute_metrics(
                ds, ds_mesh, ds_vert_coord, coriolis, reference_grad
            )
            _plot_interface_tilt(ds, ds_mesh, ds_vert_coord, scheme)

        _write_metrics(metrics)
        _plot_metrics(metrics, reference_grad)
        _log_metrics(metrics, logger, reference_grad)


def _compute_metrics(ds, ds_mesh, ds_vert_coord, coriolis, reference_grad):
    """
    The spurious-circulation time series for one forward run.
    """
    cell_mask, edge_mask, bottom_edge_mask = _masks(ds, ds_mesh, ds_vert_coord)

    speed = np.abs(ds.normalVelocity).where(edge_mask)
    max_speed = speed.max(dim=('nEdges', 'nVertLevels'))
    # where in the water column the maximum sits.  The centered scheme's
    # error accumulates downward, so a maximum that is not at the bottom is
    # worth noticing rather than averaging away.
    max_speed_level = speed.max(dim='nEdges').argmax(dim='nVertLevels')
    max_speed_bottom = speed.where(bottom_edge_mask).max(
        dim=('nEdges', 'nVertLevels')
    )

    volume = (ds_mesh.areaCell * ds.layerThickness).where(cell_mask)
    mean_kinetic_energy = (ds.kineticEnergyCell * volume).sum(
        dim=('nCells', 'nVertLevels')
    ) / volume.sum(dim=('nCells', 'nVertLevels'))

    # The acceleration a spurious flow of this speed would be in balance
    # with, so that a velocity can be compared against a pressure gradient.
    # This is a balanced-state estimate: it is meaningful once the flow has
    # adjusted and overstates the acceleration while it is still spinning up.
    implied_acceleration = coriolis * max_speed

    return {
        'days': get_days_since_start(ds),
        'max_speed': max_speed.values,
        'max_speed_level': max_speed_level.values,
        'max_speed_bottom': max_speed_bottom.values,
        'mean_kinetic_energy': mean_kinetic_energy.values,
        'implied_acceleration': implied_acceleration.values,
        'acceleration_ratio': (implied_acceleration / reference_grad).values,
    }


def _masks(ds, ds_mesh, ds_vert_coord):
    """
    Cell and edge masks of the valid levels, and of the bottom level of each
    edge.

    An edge has water only where both of its cells do, so its deepest valid
    level is the shallower of the two ``maxLevelCell`` values.  On the
    seamount flanks that is what makes the bottom-layer metric follow the
    bathymetry rather than a fixed level index.
    """
    n_vert_levels = ds.sizes['nVertLevels']
    # one-based, to compare against minLevelCell and maxLevelCell
    level = xr.DataArray(
        np.arange(1, n_vert_levels + 1), dims=('nVertLevels',)
    )

    min_level_cell = ds_vert_coord.minLevelCell
    max_level_cell = ds_vert_coord.maxLevelCell
    cell_mask = np.logical_and(
        level >= min_level_cell, level <= max_level_cell
    )

    cells_on_edge = ds_mesh.cellsOnEdge - 1
    cell0 = cells_on_edge.isel(TWO=0)
    cell1 = cells_on_edge.isel(TWO=1)
    both_cells = np.logical_and(cell0 >= 0, cell1 >= 0)
    # clip so the gather is in range; the result is thrown away where a cell
    # is missing
    index0 = cell0.clip(min=0)
    index1 = cell1.clip(min=0)

    max_level_edge = xr.where(
        both_cells,
        np.minimum(
            max_level_cell.isel(nCells=index0),
            max_level_cell.isel(nCells=index1),
        ),
        0,
    )
    min_level_edge = xr.where(
        both_cells,
        np.maximum(
            min_level_cell.isel(nCells=index0),
            min_level_cell.isel(nCells=index1),
        ),
        n_vert_levels + 1,
    )

    edge_mask = np.logical_and(
        level >= min_level_edge, level <= max_level_edge
    )
    bottom_edge_mask = np.logical_and(level == max_level_edge, edge_mask)

    return cell_mask, edge_mask, bottom_edge_mask


def _interface_tilt(ds, ds_mesh, ds_vert_coord):
    """
    The magnitude of the slope of each layer interface at each edge, per
    level and time (m/km).

    Interfaces are built up from the sea floor rather than down from the sea
    surface, so this needs only ``layerThickness`` and ``bottomDepth`` and
    works for either model without the sea-surface height being in the
    output stream.
    """
    n_vert_levels = ds.sizes['nVertLevels']
    level = xr.DataArray(
        np.arange(1, n_vert_levels + 1), dims=('nVertLevels',)
    )
    cell_mask = np.logical_and(
        level >= ds_vert_coord.minLevelCell,
        level <= ds_vert_coord.maxLevelCell,
    )

    thickness = ds.layerThickness.where(cell_mask, 0.0)
    reversed_thickness = thickness.isel(nVertLevels=slice(None, None, -1))
    sum_from_level = reversed_thickness.cumsum(dim='nVertLevels').isel(
        nVertLevels=slice(None, None, -1)
    )
    # the interface at the top of each layer
    z_interface = -ds_vert_coord.bottomDepth + sum_from_level

    cells_on_edge = ds_mesh.cellsOnEdge - 1
    cell0 = cells_on_edge.isel(TWO=0)
    cell1 = cells_on_edge.isel(TWO=1)
    both_cells = np.logical_and(cell0 >= 0, cell1 >= 0)
    index0 = cell0.clip(min=0)
    index1 = cell1.clip(min=0)

    valid = np.logical_and(
        cell_mask.isel(nCells=index0), cell_mask.isel(nCells=index1)
    )
    valid = np.logical_and(valid, both_cells)

    delta = z_interface.isel(nCells=index1) - z_interface.isel(nCells=index0)
    # m per km, the unit coordinate tilt is usually quoted in
    tilt = 1.0e3 * np.abs(delta) / ds_mesh.dcEdge
    return tilt.where(valid)


def _plot_interface_tilt(ds, ds_mesh, ds_vert_coord, scheme):
    """
    How the tilt of each layer interface evolves.

    Sigma interfaces follow the bathymetry, so the surface starts level and
    the deepest interfaces start at the full bathymetric slope.  But the free
    surface moves the layers and the coordinate movement weights are uniform,
    so every interface takes a share of the surface-pressure change and the
    top interface can acquire a tilt it did not start with.  Whether it
    actually does is the cheapest explanation to check for a spurious
    velocity that peaks at the surface, so the plot shows the change since
    the first output time rather than the tilt itself, which is dominated by
    the bathymetry and barely moves on its own scale.
    """
    tilt = _interface_tilt(ds, ds_mesh, ds_vert_coord)
    max_tilt = tilt.max(dim='nEdges')
    change = max_tilt - max_tilt.isel(Time=0)
    days = get_days_since_start(ds)

    n_vert_levels = max_tilt.sizes['nVertLevels']
    figure, axes = plt.subplots(2, 1, figsize=[12, 10], dpi=100, sharex=True)

    limit = np.nanmax(np.abs(change.values))
    mesh = axes[0].pcolormesh(
        days,
        np.arange(n_vert_levels),
        change.values.transpose(),
        shading='nearest',
        cmap='cmo.balance',
        vmin=-limit,
        vmax=limit,
    )
    figure.colorbar(mesh, ax=axes[0], label='change in max tilt (m/km)')
    axes[0].invert_yaxis()
    axes[0].set_ylabel('Level index of the interface above the layer')
    axes[0].set_title(f'Change in interface tilt, {scheme} scheme')

    # level 0 is the free surface itself, which is where a barotropic
    # adjustment would show up
    axes[1].plot(days, max_tilt.isel(nVertLevels=0), '-o', label='surface')
    axes[1].plot(
        days,
        max_tilt.max(dim='nVertLevels'),
        '-s',
        label='max over levels',
    )
    axes[1].set_yscale('log')
    axes[1].set_xlabel('Time (days)')
    axes[1].set_ylabel('max interface tilt (m/km)')
    axes[1].legend()
    axes[1].grid(True, which='both', alpha=0.3)

    figure.savefig(
        f'interface_tilt_{scheme}.png', dpi=200, bbox_inches='tight'
    )
    plt.close(figure)


def _write_metrics(metrics):
    """
    Write the time series for every scheme to a single CSV.
    """
    columns = ['scheme', 'days'] + list(METRIC_UNITS)
    with open('metrics.csv', 'w') as csv_file:
        units = ['', 'days'] + [METRIC_UNITS[name] for name in METRIC_UNITS]
        csv_file.write(','.join(columns) + '\n')
        csv_file.write('# units: ' + ','.join(units) + '\n')
        for scheme, series in metrics.items():
            for index, day in enumerate(series['days']):
                values = [scheme, f'{day:.6f}']
                values += [
                    f'{series[name][index]:.8g}' for name in METRIC_UNITS
                ]
                csv_file.write(','.join(values) + '\n')


def _plot_metrics(metrics, reference_grad):
    """
    One panel per metric, with a line per scheme.
    """
    figure, axes = plt.subplots(4, 1, figsize=[12, 16], dpi=100, sharex=True)

    for scheme, series in metrics.items():
        days = series['days']
        axes[0].plot(days, series['max_speed'], '-o', label=f'{scheme}, all')
        axes[0].plot(
            days,
            series['max_speed_bottom'],
            '--s',
            label=f'{scheme}, bottom layer',
        )
        axes[1].plot(days, series['max_speed_level'], '-o', label=scheme)
        axes[2].plot(days, series['mean_kinetic_energy'], '-o', label=scheme)
        axes[3].plot(days, series['acceleration_ratio'], '-o', label=scheme)

    axes[0].set_ylabel('max |u| (m/s)')
    axes[0].set_yscale('log')
    axes[0].set_title('Spurious velocity')

    axes[1].set_ylabel('level index of max |u|')
    axes[1].invert_yaxis()
    axes[1].set_title('Where in the column the maximum sits, 0 is the surface')

    axes[2].set_ylabel('mean KE (m2/s2)')
    axes[2].set_yscale('log')
    axes[2].set_title('Volume-weighted mean kinetic energy')

    axes[3].set_ylabel(f'|f| max |u| / {reference_grad:.2g} m/s2')
    axes[3].set_yscale('log')
    axes[3].set_title(
        'Balanced acceleration implied by the spurious velocity, as a '
        'fraction of the reference bottom-layer pressure gradient'
    )
    axes[3].set_xlabel('Time (days)')

    for axis in axes:
        axis.legend()
        axis.grid(True, which='both', alpha=0.3)

    figure.savefig('spurious_velocity_t.png', dpi=200, bbox_inches='tight')
    plt.close(figure)


def _log_metrics(metrics, logger, reference_grad):
    """
    Log the first and last time of each series, which is the comparison the
    schemes are read off from.
    """
    logger.info('')
    logger.info(
        f'Spurious circulation, against a reference bottom-layer pressure '
        f'gradient of {reference_grad:.3g} m/s2:'
    )
    header = (
        f'{"scheme":>16s} {"day":>8s} {"max |u|":>12s} {"level":>6s} '
        f'{"bottom |u|":>12s} {"mean KE":>12s} {"|f|u/ref":>10s}'
    )
    logger.info(header)
    for scheme, series in metrics.items():
        for index in _first_and_last(series['days']):
            logger.info(
                f'{scheme:>16s} {series["days"][index]:8.3f} '
                f'{series["max_speed"][index]:12.4e} '
                f'{series["max_speed_level"][index]:6d} '
                f'{series["max_speed_bottom"][index]:12.4e} '
                f'{series["mean_kinetic_energy"][index]:12.4e} '
                f'{series["acceleration_ratio"][index]:10.3f}'
            )
    logger.info('')


def _first_and_last(days):
    """The indices worth logging, without repeating a single-time series."""
    if len(days) < 2:
        return [0]
    return [0, len(days) - 1]
