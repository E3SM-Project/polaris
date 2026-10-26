"""Combined resolved and parameterized buoyancy-flux diagnostics."""

import csv

import cftime
import matplotlib.pyplot as plt
import numpy as np
import xarray as xr

from polaris.mesh.reconstruct import (
    build_reconstruction_weights,
    tangential_reconstruction,
)
from polaris.mpas.time import time_since_start
from polaris.ocean.vertical.diagnostics import vert_velocity_top_from_ds
from polaris.tasks.ocean.mixed_layer_eddies.diagnostics import (
    Gravity,
    RhoSw,
    compute_model_stream_function,
    get_density,
    get_frontal_cell_mask,
    get_geom_thickness,
)
from polaris.viz import mplstyle_context


def analyze_combined_flux(step, runs):
    """
    Plot one time-averaged flux point per run against a 1:1 reference.

    Each run supplies its name, mesh filename, snapshot filename, and whether
    the parameterization is enabled.
    """
    config = step.config
    if not runs:
        raise ValueError('Flux analysis requires at least one simulation')
    section = config['mixed_layer_eddies_analysis']
    average_start = section.getfloat('flux_average_start_day')
    average_end = section.getfloat('flux_average_end_day')
    if not (
        np.isfinite([average_start, average_end]).all()
        and 0.0 <= average_start < average_end
    ):
        raise ValueError('Invalid flux averaging window')
    ce = config.getfloat('mixed_layer_eddies_mle', 'ce')
    if not np.isfinite(ce) or ce <= 0.0:
        raise ValueError('Flux scaling requires finite positive C_e')
    samples = []
    averages = []
    for name, mesh_file, eddy_file, mle_enabled in runs:
        with (
            step.open_model_dataset(mesh_file) as mesh,
            step.open_model_dataset(eddy_file) as ds,
        ):
            # Use days since the original simulation start, not the
            # restart segment's start, to select the inclusive window.
            days = get_snapshot_days(ds)
            selected = np.flatnonzero(
                (days >= average_start - 1.0e-10)
                & (days <= average_end + 1.0e-10)
            )
            times = days[selected]
            step.logger.info(
                f'{name}: {len(times)} output times between days '
                f'{average_start:g} and {average_end:g}'
            )
            if len(times) < 2:
                raise ValueError(
                    f'{name}: time averaging requires at least two '
                    'output times in the averaging window'
                )
            stencil, weights = build_reconstruction_weights(mesh, 'cell')
            run_samples = []
            # Diagnose each saved snapshot, not each model timestep.
            # Coarse timesteps do not divide an hour exactly: output at
            # the timestep crossing each hourly alarm has unequal spacing.
            for index in selected:
                day = days[index]
                try:
                    result = compute_combined_flux(
                        config,
                        mesh,
                        ds.isel(Time=index).load(),
                        stencil,
                        weights,
                        mle_enabled=mle_enabled,
                    )
                except ValueError as error:
                    raise ValueError(
                        f'{name}, day {day:g}: {error}'
                    ) from error
                run_samples.append(dict(run=name, day=day, **result))
        samples.extend(run_samples)
        window = [
            sample
            for sample in run_samples
            if average_start - 1.0e-10
            <= sample['day']
            <= average_end + 1.0e-10
        ]
        # Weight signed quantities by actual timestamp spacing and divide
        # by the sampled duration; take magnitudes only after averaging.
        x = (
            ce
            * np.trapezoid(
                [sample['signed_scale'] for sample in window], times
            )
            / (times[-1] - times[0])
        )
        y = np.trapezoid(
            [sample['signed_diagnosed'] for sample in window], times
        ) / (times[-1] - times[0])
        resolved_y = np.trapezoid(
            [
                sample['resolved_flux'] / sample['buoyancy_gradient']
                for sample in window
            ],
            times,
        ) / (times[-1] - times[0])
        averages.append(
            dict(
                run=name,
                start_day=average_start,
                end_day=average_end,
                first_sample_day=float(times[0]),
                last_sample_day=float(times[-1]),
                samples=len(window),
                ce_configured=ce,
                signed_scaled_mean=float(x),
                signed_response_mean=float(y),
                x=abs(float(x)),
                y=abs(float(y)),
                resolved_y=abs(float(resolved_y)),
            )
        )
        step.logger.info(
            f'{name}: days {average_start:g}--{average_end:g}, '
            f'{len(window)} snapshots; X={abs(x):.4g}, Y={abs(y):.4g} m2 s-1'
        )
    _plot_average_flux(averages, any(run[3] for run in runs))
    for filename, records in (
        ('combined_buoyancy_flux.csv', samples),
        ('combined_buoyancy_flux_average.csv', averages),
    ):
        with open(filename, 'w', newline='') as output:
            writer = csv.DictWriter(output, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)


def get_snapshot_days(ds):
    """Read absolute simulation days without changing elapsed-time helpers."""
    if 'daysSinceStartOfSim' in ds:
        days = ds.daysSinceStartOfSim.values.astype(float)
    elif 'xtime' in ds:
        days = (
            time_since_start(
                ds.xtime.values, start_xtime='0001-01-01_00:00:00'
            )
            / 86400.0
        )
    elif 'Time' in ds.coords:
        days = np.asarray(
            cftime.date2num(
                ds.Time.values,
                units='days since 0001-01-01 00:00:00',
                calendar=ds.Time.dt.calendar,
                has_year_zero=True,
            ),
            dtype=float,
        )
    else:
        raise ValueError('Flux analysis requires model snapshot timestamps')
    if (
        days.shape != (ds.sizes['Time'],)
        or not np.isfinite(days).all()
        or np.any(np.diff(days) <= 0.0)
    ):
        raise ValueError(
            'Snapshot days must be finite and strictly increasing'
        )
    return days


def compute_combined_flux(config, mesh, ds, stencil, weights, *, mle_enabled):
    """
    Diagnose one snapshot in the central frontal band.

    Average along-front covariances before averaging across the band.
    Sample at half the band-mean model mixed-layer depth. The returned
    fluxes are equivalent advective fluxes, not numerical tracer fluxes.
    Include parameterized transport only when explicitly enabled; its
    velocity field is then required even if its contribution is zero.
    """
    section = config['mixed_layer_eddies_analysis']
    mask = get_frontal_cell_mask(
        mesh, section.getfloat('frontal_zone_fraction')
    ).values
    area = mesh.areaCell.values
    _, rows = np.unique(np.round(mesh.yCell.values, 3), return_inverse=True)
    row_area = np.bincount(rows, weights=area)
    row_y = np.bincount(rows, weights=area * mesh.yCell.values) / row_area
    selected = np.unique(rows[mask])
    if selected.size < 2:
        raise ValueError('Flux diagnosis requires at least two mesh rows')

    thickness = (
        get_geom_thickness(config, ds)
        .transpose('nCells', 'nVertLevels')
        .values
    )
    ssh = ds.ssh.values
    interfaces = np.column_stack(
        (ssh, ssh[:, None] - np.cumsum(thickness, axis=1))
    )
    midpoints = 0.5 * (interfaces[:, :-1] + interfaces[:, 1:])
    if 'dThreshMLD' not in ds:
        raise ValueError('Flux diagnosis requires model mixed-layer depth')
    mld = ds.dThreshMLD.transpose('nCells').values
    if (
        not np.isfinite(mld[mask]).all()
        or np.any(mld[mask] <= 0.0)
        or np.any(mld[mask] > np.sum(thickness[mask], axis=1))
    ):
        raise ValueError(
            'Model mixed-layer depth must be finite, positive and '
            'within the water column'
        )
    h = float(np.average(mld[mask], weights=area[mask]))
    buoyancy = (
        -Gravity
        * (
            get_density(config, ds).transpose('nCells', 'nVertLevels').values
            - RhoSw
        )
        / RhoSw
    )
    bottom = float(np.min(-interfaces[mask, -1]))
    dz = bottom / thickness.shape[1]
    depths = (np.arange(thickness.shape[1]) + 0.5) * dz
    band_profiles = np.array(
        [
            _row_mean(_at_height(buoyancy, midpoints, -depth), rows, area)
            for depth in depths
        ]
    ).T
    band_weights = row_area[selected]
    target = -0.5 * h
    b = _at_height(buoyancy, midpoints, target)

    if 'VerticalPseudoVelocity' in ds:
        velocity = vert_velocity_top_from_ds(ds)
    else:
        velocity = ds.vertVelocityTop
    w = _at_height(
        velocity.transpose('nCells', 'nVertLevelsP1').values,
        interfaces,
        target,
    )
    b_row = _row_mean(b, rows, area)
    w_row = _row_mean(w, rows, area)
    resolved = _row_mean((w - w_row[rows]) * (b - b_row[rows]), rows, area)
    by = np.gradient(b_row, row_y)
    by_half = float(np.average(by[selected], weights=band_weights))
    by_profile = np.gradient(band_profiles, row_y, axis=0)
    # Include a surface value and interpolate to the diagnosed base before
    # integrating, rather than selecting a resolution-dependent layer count.
    ml_depths = np.concatenate(([0.0], depths[depths < h], [h]))
    ml_by = np.array(
        [
            np.interp(ml_depths, depths, profile)
            for profile in by_profile[selected]
        ]
    )
    by_ml = float(
        np.average(
            np.trapezoid(ml_by, ml_depths, axis=1) / h,
            weights=band_weights,
        )
    )

    parameterized = np.zeros_like(resolved)
    if mle_enabled:
        if 'normalMLEvelocity' not in ds:
            raise ValueError(
                'Enabled MLE parameterization requires normalMLEvelocity'
            )
        edges = np.arange(mesh.sizes['nEdges'])
        psi = compute_model_stream_function(
            config, mesh, ds, edges, ds.normalMLEvelocity
        )
        cells = mesh.cellsOnEdge.values - 1
        edge_z = 0.5 * (interfaces[cells[:, 0]] + interfaces[cells[:, 1]])
        psi_at_depth = xr.DataArray(
            _at_height(psi, edge_z, target), dims='nEdges'
        )
        grad_normal = xr.DataArray(
            (b[cells[:, 1]] - b[cells[:, 0]]) / mesh.dcEdge.values,
            dims='nEdges',
        )
        px, py, _ = tangential_reconstruction(
            mesh, psi_at_depth, stencil, weights
        )
        bx, by_cell, _ = tangential_reconstruction(
            mesh, grad_normal, stencil, weights
        )
        # The recovered edge streamfunction is opposite to the buoyancy
        # gradient: its vertical skew flux is -psi_normal dot grad(b).
        parameterized = _row_mean(
            -(px.values * bx.values + py.values * by_cell.values),
            rows,
            area,
        )

    resolved_flux = float(np.average(resolved[selected], weights=band_weights))
    parameterized_flux = float(
        np.average(parameterized[selected], weights=band_weights)
    )
    f = float(np.average(np.abs(mesh.fCell.values[mask]), weights=area[mask]))
    if f == 0.0 or abs(by_half) < 1.0e-12 or abs(by_ml) < 1.0e-12:
        raise ValueError(
            'Combined-flux scaling is undefined: zero Coriolis parameter '
            'or frontal buoyancy gradient below 1e-12 s-2'
        )
    result = dict(
        mixed_layer_depth=h,
        buoyancy_gradient=by_half,
        mixed_layer_buoyancy_gradient=by_ml,
        resolved_flux=resolved_flux,
        parameterized_flux=parameterized_flux,
        combined_flux=resolved_flux + parameterized_flux,
        signed_scale=h**2 * by_ml / f,
        signed_diagnosed=(resolved_flux + parameterized_flux) / by_half,
        scale=h**2 * abs(by_ml) / f,
        diagnosed=abs((resolved_flux + parameterized_flux) / by_half),
    )
    if not all(np.isfinite(value) for value in result.values()):
        raise ValueError('Nonfinite combined buoyancy-flux diagnostic')
    return result


def _row_mean(values, rows, area):
    """Area-weighted along-front means at native mesh rows."""
    return np.bincount(rows, weights=values * area) / np.bincount(
        rows, weights=area
    )


def _plot_average_flux(averages, combined):
    """Compare time-averaged transport with the configured scaling."""
    with mplstyle_context():
        fig, ax = plt.subplots(figsize=(6.5, 5.5))
        colors = {'resolved': 'black', '8km': 'tab:blue', '16km': 'tab:orange'}
        for sample in averages:
            name = sample['run']
            resolution = name.split('_')[0]
            color = colors[resolution]
            label = (
                '500m (resolved)'
                if name == 'resolved'
                else name.replace('_', ' ')
            )
            ax.scatter(
                sample['x'],
                sample['y'],
                color=color,
                marker='D' if name.endswith('_off') else 'o',
                label=f'{label}, total',
            )
            if name.endswith('_on'):
                ax.scatter(
                    sample['x'],
                    sample['resolved_y'],
                    facecolors='none',
                    edgecolors=color,
                    marker='D',
                    label=f'{label}, resolved only',
                )
        bounds = (
            min(sample['resolved_y'] for sample in averages),
            1.0e0,
        )
        ax.plot(bounds, bounds, 'k--', label='1:1')
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlim(bounds)
        ax.set_ylim(bounds)
        ax.set_aspect('equal', adjustable='box')
        ax.set_xlabel(
            r'$|\langle C_e H^2 \overline{b_y}^{\,z}/|f|'
            r'\rangle_t|$ (m$^2$ s$^{-1}$)'
        )
        ax.set_ylabel('Normalized buoyancy flux (m² s⁻¹)')
        ax.set_title(
            f'Days {averages[0]["start_day"]:g}–'
            f'{averages[0]["end_day"]:g} time averages'
        )
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig('combined_buoyancy_flux.png', dpi=150)
        plt.close(fig)


def _at_height(values, heights, target):
    """Interpolate descending column profiles to a common physical height."""
    index = np.sum(heights > target, axis=1) - 1
    index = np.clip(index, 0, heights.shape[1] - 2)
    column = np.arange(len(index))
    upper = heights[column, index]
    lower = heights[column, index + 1]
    fraction = np.clip((upper - target) / (upper - lower), 0.0, 1.0)
    return (1.0 - fraction) * values[column, index] + fraction * values[
        column, index + 1
    ]
