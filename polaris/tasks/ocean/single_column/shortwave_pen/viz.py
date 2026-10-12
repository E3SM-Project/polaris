import os

import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep, get_time_since_start
from polaris.tasks.ocean.single_column.shortwave_pen.jerlov import (
    JERLOV_WATER_TYPES,
    jerlov_absorption_fraction,
    manizza_absorption_fraction,
    manizza_scale,
)
from polaris.viz import mplstyle_context

# the depth range of the profile plots
ZMIN = -100.0
ZMAX = 0.0

_COLORS = ['k', 'b', 'r', 'darkgreen', 'darkorange']


class Viz(OceanIOStep):
    """
    A step for plotting the ``shortwave_pen`` temperature profiles against
    water clarity, and the analytic absorption profiles the two models
    integrate.

    When ``single_column_shortwave_pen:reference_output_dir`` points at the
    work directory of this task from a run with the other ocean model, that
    run's profiles are overlaid as dashed lines.  Because Polaris chooses the
    ocean model once per work directory, that is how the two models are
    compared.

    Attributes
    ----------
    water_types : list of int
        The Jerlov water types that were run

    comparisons : dict
        A mapping from run name to the forward step directory it comes from
    """

    def __init__(self, component, indir, init, water_types, comparisons):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        init : polaris.Step
            The initial-condition step providing the mesh

        water_types : list of int
            The Jerlov water types that were run

        comparisons : dict
            A mapping from run name to the forward step directory it comes
            from
        """
        super().__init__(component=component, name='viz', indir=indir)
        self.water_types = sorted(water_types)
        self.comparisons = dict(comparisons)
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_input_file(
            filename='init.nc', work_dir_target=f'{init.path}/init.nc'
        )
        for name, path in self.comparisons.items():
            self.add_input_file(
                filename=f'{name}.nc', target=f'{path}/output.nc'
            )

    def setup(self):
        """
        Link the other model's output if a reference run has been configured
        """
        super().setup()
        reference_dir = self.config.get(
            'single_column_shortwave_pen', 'reference_output_dir'
        ).strip()
        if not reference_dir:
            return
        for name in self.comparisons:
            self.add_input_file(
                filename=f'ref_{name}.nc',
                target=os.path.join(
                    reference_dir, f'forward_{name}', 'output.nc'
                ),
            )

    def run(self):
        """
        Run this step of the test case
        """
        with mplstyle_context():
            self._plot_absorption_fraction()

            config = self.config
            ds_init = self.open_model_dataset('init.nc', config=config)
            ds_init = ds_init.isel(Time=0)
            z_mid = ds_init['zMid'].mean(dim='nCells')
            temperature_init = ds_init['temperature'].mean(dim='nCells')

            runs = self._load_runs()
            if not runs:
                self.logger.warn('No forward output found; skipping plots')
                return

            self._plot_profiles(runs, z_mid, temperature_init, anomaly=False)
            self._plot_profiles(runs, z_mid, temperature_init, anomaly=True)

    def _load_runs(self):
        """
        Read the final temperature profile of every run that produced output
        """
        config = self.config
        runs = dict()
        for name in self.comparisons:
            for prefix, is_reference in (('', False), ('ref_', True)):
                filename = f'{prefix}{name}.nc'
                if not os.path.exists(filename):
                    continue
                ds = self.open_model_dataset(
                    filename,
                    decode_times=True,
                    mesh_filename='mesh.nc',
                    config=config,
                )
                t_days = float(get_time_since_start(ds, units='days')[-1])
                runs[f'{prefix}{name}'] = dict(
                    name=name,
                    is_reference=is_reference,
                    t_days=t_days,
                    temperature=(
                        ds['temperature'].isel(Time=-1).mean(dim='nCells')
                    ),
                )
        return runs

    def _plot_profiles(self, runs, z_mid, temperature_init, anomaly):
        """
        Plot the final temperature profiles, or their change from the
        initial condition
        """
        fig = plt.figure(figsize=(4, 6))
        x_min = None
        x_max = None
        for _key, run in runs.items():
            var = run['temperature']
            if anomaly:
                var = var - temperature_init
            color, linestyle = self._style(run)
            label = run['name'].replace('_', ' ')
            if run['is_reference']:
                label = f'{label} (reference)'
            plt.plot(var, z_mid, linestyle, color=color, label=label)
            x_min, x_max = _update_limits(x_min, x_max, var, z_mid)
        if not anomaly:
            plt.plot(
                temperature_init, z_mid, '--', color='gray', label='initial'
            )
            x_min, x_max = _update_limits(
                x_min, x_max, temperature_init, z_mid
            )

        if anomaly:
            plt.axvline(0, color='k', linestyle=':', linewidth=0.8)
            plt.xlabel('temperature change (degC)')
            filename = 'temperature_anomaly.png'
        else:
            plt.xlabel('temperature (degC)')
            filename = 'temperature.png'
        plt.ylabel('z (m)')
        plt.ylim(ZMIN, ZMAX)
        if x_min is not None and x_max is not None:
            margin = max((x_max - x_min) * 0.05, 1e-12)
            plt.xlim(x_min - margin, x_max + margin)
        fig.legend(
            loc='upper center',
            bbox_to_anchor=(0.5, -0.05),
            ncol=1,
            frameon=False,
        )
        plt.savefig(filename, bbox_inches='tight')
        plt.close()

    def _plot_absorption_fraction(self):
        """
        Plot the analytic fraction of the incident shortwave flux reaching
        each depth, for MPAS-Ocean's two bands and Omega's three

        This uses only the schemes' parameters, so it is produced whether or
        not the forward runs have output.
        """
        section = self.config['single_column_shortwave_pen']
        coeff_red = section.getfloat('extinction_coeff_red')
        coeff_blue = section.getfloat('extinction_coeff_blue')
        near_ir_fraction = section.getfloat('near_ir_fraction')
        near_ir_coeff = section.getfloat('near_ir_coeff')
        red_fraction = section.getfloat('red_fraction')
        blue_fraction = section.getfloat('blue_fraction')

        depth = np.linspace(0.0, -ZMIN, 500)
        fig = plt.figure(figsize=(4, 6))
        for index, water_type in enumerate(self.water_types):
            color = _COLORS[index % len(_COLORS)]
            name = JERLOV_WATER_TYPES[water_type]
            plt.plot(
                jerlov_absorption_fraction(depth, water_type),
                -depth,
                '-',
                color=color,
                label=f'jerlov type{water_type} ({name})',
            )
            scale = manizza_scale(water_type)
            plt.plot(
                manizza_absorption_fraction(
                    depth,
                    near_ir_fraction=near_ir_fraction,
                    near_ir_coeff=near_ir_coeff,
                    red_fraction=red_fraction,
                    blue_fraction=blue_fraction,
                    extinction_coeff_red=coeff_red * scale,
                    extinction_coeff_blue=coeff_blue * scale,
                ),
                -depth,
                ':',
                color=color,
                label=f'manizza type{water_type} ({name})',
            )
        plt.xscale('log')
        plt.xlabel('fraction of incident shortwave flux')
        plt.ylabel('z (m)')
        plt.ylim(ZMIN, ZMAX)
        fig.legend(
            loc='upper center',
            bbox_to_anchor=(0.5, -0.05),
            ncol=1,
            frameon=False,
        )
        plt.savefig('absorption_fraction.png', bbox_inches='tight')
        plt.close()

    def _style(self, run):
        """The colour and line style for a run"""
        water_type = _water_type_from_name(run['name'])
        index = (
            self.water_types.index(water_type)
            if water_type in self.water_types
            else 0
        )
        color = _COLORS[index % len(_COLORS)]
        if run['is_reference']:
            linestyle = '--'
        elif run['name'].startswith('manizza'):
            linestyle = ':'
        else:
            linestyle = '-'
        return color, linestyle


def _water_type_from_name(name):
    """The Jerlov water type encoded in a run name such as ``jerlov_type3``"""
    return int(name.rsplit('type', 1)[-1])


def _update_limits(x_min, x_max, var, z):
    """Widen the x-axis limits to include the visible part of ``var``"""
    visible = var[(z >= ZMIN) & (z <= ZMAX)]
    if int(visible.count()) == 0:
        return x_min, x_max
    values = visible.values.astype(float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return x_min, x_max
    low = float(values.min())
    high = float(values.max())
    x_min = low if x_min is None else min(x_min, low)
    x_max = high if x_max is None else max(x_max, high)
    return x_min, x_max
