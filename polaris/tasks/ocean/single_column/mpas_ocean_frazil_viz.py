import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.vertical.diagnostics import (
    location_for_field,
    vertical_coord_from_location,
)

MPAS_OCEAN_FRAZIL_TENDENCIES = {
    'frazilLayerThicknessTendency': 'm s$^{-1}$',
    'frazilSalinityTendency': 's$^{-1}$',
    'frazilTemperatureTendency': 'm degC s$^{-1}$',
}

MPAS_OCEAN_FRAZIL_ACCUMULATED = {
    'accumulatedFrazilIceMass': 'Frazil ice mass (kg m$^{-2}$)',
    'accumulatedFrazilIceSalinity': ('Frazil-associated salt (kg m$^{-2}$)'),
}


def mpas_ocean_frazil_data(ds, ds_mesh):
    """Collect MPAS-Ocean frazil profiles and area-mean time series."""
    fields = {
        *MPAS_OCEAN_FRAZIL_TENDENCIES,
        *MPAS_OCEAN_FRAZIL_ACCUMULATED,
    }
    missing = [field for field in fields if field not in ds]
    if missing:
        raise ValueError(
            'MPAS-Ocean frazil output is missing required fields: '
            + ', '.join(sorted(missing))
        )
    if 'areaCell' not in ds_mesh:
        raise ValueError('MPAS-Ocean frazil mesh is missing areaCell')
    if ds.sizes.get('Time', 0) == 0:
        raise ValueError('MPAS-Ocean frazil output has no time records')

    time_hours = (
        np.asarray(ds['daysSinceStartOfSim'].values, dtype=float) * 24.0
    )
    # Keep exact day boundaries in the preceding day despite roundoff.
    output_days = np.maximum(1, np.ceil(time_hours / 24.0 - 1.0e-10))
    profile_indices = np.append(
        np.flatnonzero(np.diff(output_days) != 0),
        ds.sizes['Time'] - 1,
    )

    profiles: dict[str, list[np.ndarray]] = {
        field: [] for field in MPAS_OCEAN_FRAZIL_TENDENCIES
    }
    depths = []
    for time_index in profile_indices:
        snapshot = ds.isel(Time=time_index)
        active = snapshot.layerThickness.notnull() & (
            snapshot.layerThickness > 0.0
        )
        first_field = next(iter(MPAS_OCEAN_FRAZIL_TENDENCIES))
        first_var = snapshot[first_field]
        z = vertical_coord_from_location(
            snapshot,
            location_for_field(first_var, first_field),
        )
        depths.append(
            np.asarray(z.where(active).mean(dim='nCells', skipna=True).values)
        )
        for field in profiles:
            profile = (
                snapshot[field].where(active).mean(dim='nCells', skipna=True)
            )
            profiles[field].append(np.asarray(profile.values))

    cell_area = ds_mesh.areaCell
    total_area = cell_area.sum(dim='nCells')
    accumulated = {}
    for field in ('accumulatedFrazilIceMass', 'accumulatedFrazilIceSalinity'):
        accumulated[field] = np.asarray(
            ((ds[field] * cell_area).sum(dim='nCells') / total_area).values
        )
    return {
        'time_hours': time_hours,
        'profile_hours': time_hours[profile_indices],
        'depths': depths,
        'profiles': {
            field: np.stack(values) for field, values in profiles.items()
        },
        'accumulated': accumulated,
    }


def plot_mpas_ocean_frazil_profiles(series, styles):
    """Plot profiles of MPAS-Ocean frazil tendencies."""
    if not series:
        return

    profile_fields = tuple(MPAS_OCEAN_FRAZIL_TENDENCIES.items())
    fig, axes = plt.subplots(
        1, len(profile_fields), figsize=(15, 6), sharey=True
    )
    time_colors = plt.get_cmap('viridis')
    for item in series:
        name = item['name']
        data = item['frazil_data']
        for time_index, hours in enumerate(data['profile_hours']):
            color = time_colors(
                time_index / max(len(data['profile_hours']) - 1, 1)
            )
            for ax, (field, _units) in zip(axes, profile_fields, strict=True):
                ax.plot(
                    data['profiles'][field][time_index],
                    data['depths'][time_index],
                    color=color,
                    linestyle=styles[name]['linestyle'],
                    label=f'{name}, {hours:.3g} h',
                )

    for ax, (field, units) in zip(axes, profile_fields, strict=True):
        ax.set_xlabel(f'{field}\n({units})')
        ax.grid(alpha=0.3)
    axes[0].set_ylabel('z (m)')
    axes[0].legend(fontsize=7)
    fig.tight_layout()
    fig.savefig('frazil-tendency-profiles.png', dpi=150, bbox_inches='tight')
    plt.close(fig)


def plot_mpas_ocean_frazil(series, styles, plot_tendencies=True):
    """Plot MPAS-Ocean frazil tendency profiles and accumulated budgets."""
    if not series:
        return

    if plot_tendencies:
        plot_mpas_ocean_frazil_profiles(series, styles)

    fig, axes = plt.subplots(
        len(MPAS_OCEAN_FRAZIL_ACCUMULATED),
        1,
        figsize=(10, 8),
        sharex=True,
    )
    for item in series:
        name = item['name']
        data = item['frazil_data']
        for ax, (field, label) in zip(
            axes, MPAS_OCEAN_FRAZIL_ACCUMULATED.items(), strict=True
        ):
            ax.plot(
                data['time_hours'],
                data['accumulated'][field],
                lw=2,
                label=name,
                **styles[name],
            )
            ax.set_ylabel(label)
            ax.grid(alpha=0.3)
    axes[0].legend(fontsize=7)
    axes[0].set_title(
        'Area-weighted mean accumulated frazil quantities '
        '(may reset at coupling intervals)'
    )
    axes[-1].set_xlabel('time (hours)')
    fig.tight_layout()
    fig.savefig('accumulated-frazil.png', dpi=150, bbox_inches='tight')
    plt.close(fig)
