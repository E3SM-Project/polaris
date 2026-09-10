import os

import matplotlib.pyplot as plt
import numpy as np

from polaris.ocean.model import OceanIOStep, get_time_since_start
from polaris.viz import mplstyle_context

# TODO import rho_0 from constants

# Fields defined at the top of each layer that a model nonetheless writes on
# ``nVertLevels``, leaving the bottom of the column off, rather than on
# ``nVertLevelsP1``.  MPAS-Ocean writes ``BruntVaisalaFreqTop`` this way
# while giving ``RiTopOfCell`` and ``vertViscTopOfCell`` the interface
# dimension; Omega writes ``BruntVaisalaFreqTop`` on ``nVertLevelsP1``.
# Dimensions cannot tell such a field from a layer average, so it is named
# here.  A field is only ever read from this list when it arrives on
# ``nVertLevels``, so listing one that a model writes at interfaces is
# harmless.
TOP_OF_LAYER_FIELDS = ('BruntVaisalaFreqTop',)


class Viz(OceanIOStep):
    """
    A step for plotting the results of a single-column test
    """

    def __init__(
        self,
        component,
        indir,
        init,
        name='viz',
        ideal_age=False,
        comparisons=None,
        variables=None,
        output_file='output.nc',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        ideal_age : bool, optional
            Whether the initial condition should include the ideal age tracer

        comparisons : dict, optional
            A dictionary of comparison datasets to use for validation

        variables : dict, optional
            A dictionary of variables to plot along with their units
        """
        super().__init__(component=component, name=name, indir=indir)
        self.comparisons = (
            dict(comparisons) if comparisons else {'forward': '../forward'}
        )
        self.variables = (
            dict(variables)
            if variables
            else {
                'temperature': 'degC',
                'salinity': 'PSU',
                'velocity': 'm s$^{-1}$',
            }
        )
        if ideal_age:
            # Include age tracer
            self.variables['iAge'] = 'seconds'
        self.add_input_file(
            filename='mesh.nc', work_dir_target=f'{init.path}/culled_mesh.nc'
        )
        self.add_input_file(
            filename='init.nc', work_dir_target=f'{init.path}/init.nc'
        )
        for comparison_name, comparison_path in self.comparisons.items():
            self.add_input_file(
                filename=f'{comparison_name}.nc',
                target=f'{comparison_path}/{output_file}',
            )

    def run(self):
        """
        Run this step of the test case
        """
        with mplstyle_context():
            section = self.config['single_column']
            if section.has_option('run_duration'):
                t_target = section.getfloat('run_duration')
            else:
                self.logger.info(
                    'run_duration not found in config; using default plotting '
                    'time of 10 days'
                )
                t_target = 10.0

            ds_list = []
            time_ds = []
            # Remove missing comparison so it won't be used later
            comparisons = dict()
            for comparison_name in self.comparisons.keys():
                if os.path.exists(f'{comparison_name}.nc'):
                    comparisons[comparison_name] = self.comparisons[
                        comparison_name
                    ]
                else:
                    continue
                ds_comp = self.open_model_dataset(
                    f'{comparison_name}.nc',
                    decode_times=True,
                    mesh_filename='mesh.nc',
                    reconstruct_variables=['normalVelocity'],
                    config=self.config,
                )
                t_arr = get_time_since_start(ds_comp, units='days')
                t_index = np.argmin(np.abs(t_arr - t_target))
                time_ds.append(float(t_arr[t_index]))
                ds_list.append(ds_comp.isel(Time=t_index))
            ds_init = self.open_model_dataset('init.nc', config=self.config)
            ds_init = ds_init.isel(Time=0)
            z_mid_init = ds_init['zMid'].mean(dim='nCells')
            z_interface_init = ds_init['GeomZInterface'].mean(dim='nCells')

            z_mid_final = z_mid_init
            z_interface_final = z_interface_init
            self.logger.warn(
                'Using the initial vertical coordinate; may not represent '
                'the plotted state'
            )

            # The depth range of the plots, also used to select the data
            # that sets the x-axis range
            ymin = -100.0
            ymax = 0.0

            # Plot depth profiles of variables
            for field_name, field_units in self.variables.items():
                curves_plotted = 0
                x_limits: list[tuple[float, float]] = []
                fig = plt.figure(figsize=(3, 5))
                colors = ['k', 'b', 'r', 'darkgreen']
                for comparison_name, ds_comp, t_days, color in zip(
                    self.comparisons.keys(),
                    ds_list,
                    time_ds,
                    colors,
                    strict=False,
                ):
                    # TODO use this line when Omega zMid is correct
                    # z_mid_final = ds_comp['zMid'].mean(dim='nCells')
                    # TODO compare with z_mid computed from layerThickness
                    # z_mid_final = depth_from_thickness(ds_comp).mean(
                    #    dim='nCells'
                    # )
                    if field_name == 'velocity':
                        if (
                            'velocityZonal' not in ds_comp.keys()
                            and 'velocityMeridional' not in ds_comp.keys()
                        ):
                            self.logger.info(
                                '\tvelocityZonal,Meridional not '
                                f'found; skipping plot for '
                                f'{comparison_name}'
                            )
                            continue
                        self.logger.info(
                            f'Plot {field_name} for '
                            f'{comparison_name} at {t_days} days'
                        )
                        var = ds_comp['velocityZonal'].mean(dim='nCells')
                        z = _vertical_coord(
                            'velocityZonal',
                            var,
                            z_mid_final,
                            z_interface_final,
                        )
                        plt.plot(
                            var,
                            z,
                            '-',
                            color=color,
                            label=f'u {comparison_name}, {t_days:2g} days',
                        )
                        _add_visible_limits(x_limits, var, z, ymin, ymax)
                        var = ds_comp['velocityMeridional'].mean(dim='nCells')
                        z = _vertical_coord(
                            'velocityMeridional',
                            var,
                            z_mid_final,
                            z_interface_final,
                        )
                        plt.plot(
                            var,
                            z,
                            '--',
                            color=color,
                            label=f'v {comparison_name}, {t_days:2g} days',
                        )
                        _add_visible_limits(x_limits, var, z, ymin, ymax)
                        curves_plotted += 1
                    else:
                        if field_name not in ds_comp.keys():
                            self.logger.info(
                                f'\t{field_name} not found; skipping plot for '
                                f'{comparison_name}'
                            )
                            continue
                        var = ds_comp[field_name].mean(dim='nCells')
                        z = _vertical_coord(
                            field_name, var, z_mid_final, z_interface_final
                        )
                        # TODO delete this line when MPAS-O bug is fixed
                        if field_name == 'RiTopOfCell':
                            var[0] = np.nan
                        plt.plot(
                            var,
                            z,
                            '-',
                            color=color,
                            label=f'{comparison_name}, {t_days:2g} days',
                        )
                        _add_visible_limits(x_limits, var, z, ymin, ymax)
                        curves_plotted += 1
                        # Plot initial state if available and
                        # hasn't already been plotted
                        existing_labels = [
                            lbl
                            for lbl in plt.gca().get_legend_handles_labels()[1]
                            if isinstance(lbl, str)
                        ]
                        if (
                            field_name in ds_init.keys()
                            and 'initial' not in existing_labels
                        ):
                            var_init = ds_init[field_name].mean(dim='nCells')
                            z_init = _vertical_coord(
                                field_name,
                                var_init,
                                z_mid_init,
                                z_interface_init,
                            )
                            plt.plot(var_init, z_init, '--k', label='initial')
                            _add_visible_limits(
                                x_limits, var_init, z_init, ymin, ymax
                            )
                            curves_plotted += 1
                if curves_plotted == 0:
                    self.logger.warn(
                        f'No data plotted for {field_name}, skipping save'
                    )
                    plt.close()
                    continue
                plt.ylim(ymin, ymax)
                if x_limits:
                    x_min = min(limits[0] for limits in x_limits)
                    x_max = max(limits[1] for limits in x_limits)
                    x_margin = (x_max - x_min) * 0.05
                    if x_margin == 0.0:
                        # the field is constant over the visible depths, so
                        # fall back to a margin that does not collapse the
                        # axis to a single value
                        x_margin = 0.05 * max(abs(x_min), 1.0)
                    plt.xlim(x_min - x_margin, x_max + x_margin)
                plt.xlabel(f'{field_name} ({field_units})')
                plt.ylabel('z (m)')
                # Place a single legend centered below the x-axis
                fig.legend(
                    loc='upper center',
                    bbox_to_anchor=(0.5, -0.08),
                    ncol=1,
                    frameon=False,
                )
                plt.savefig(f'{field_name}.png', bbox_inches='tight')
                plt.close()


def _vertical_coord(field_name, var, z_mid, z_interface):
    """
    The vertical coordinate to plot ``var`` against

    A field on ``nVertLevelsP1`` is defined at layer interfaces --- the top
    of each layer, plus one more for the bottom of the column --- so it is
    plotted at interface elevations.  A field in
    :py:data:`TOP_OF_LAYER_FIELDS` is defined at the top of each layer but
    written on ``nVertLevels``, so it is plotted at the top interface of
    each layer.  Everything else is a layer quantity and is plotted at
    layer midpoints.
    """
    if 'nVertLevelsP1' in var.dims:
        return z_interface
    if field_name in TOP_OF_LAYER_FIELDS:
        return _layer_tops(z_interface)
    return z_mid


def _layer_tops(z_interface):
    """
    The elevation of the top interface of each layer, on ``nVertLevels``

    ``isel()`` changes the length of the dimension but not its name, so the
    result is renamed to the dimension the field it pairs with is on.
    """
    z_top = z_interface.isel(nVertLevelsP1=slice(0, -1))
    return z_top.rename({'nVertLevelsP1': 'nVertLevels'})


def _add_visible_limits(x_limits, var, z, ymin, ymax):
    """
    Add the range of ``var`` over the visible depths to the ``x_limits``
    list

    Depths outside ``ymin`` to ``ymax`` are excluded because they are not
    plotted, and NaNs are ignored.  Nothing is added if no finite value is
    visible.
    """
    visible = var[(z >= ymin) & (z <= ymax)]
    if int(visible.count()) == 0:
        return
    x_min = float(visible.min().values)
    x_max = float(visible.max().values)
    if not (np.isfinite(x_min) and np.isfinite(x_max)):
        return
    x_limits.append((x_min, x_max))
