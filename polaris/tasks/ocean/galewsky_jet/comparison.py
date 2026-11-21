import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.galewsky_jet.diagnostics import (
    contour_lon_lat,
    divergence,
    get_output_times,
    global_l2,
    relative_vorticity,
)
from polaris.tasks.ocean.galewsky_jet.initial_state import (
    balanced_height,
    get_jet_params,
)
from polaris.viz import mplstyle_context

# reference values from Table 1 of Galewsky et al. (2004).  Table 1's l2(h)
# of 9778 m is left out: the l2 norm of a field whose global mean is 10 km
# cannot be less than 10 km.
TABLE1_ADJUSTMENT = {
    'l2(div) (1/s)': 4.0e-7,
    'max(div) (1/s)': 3.7e-6,
    'min(div) (1/s)': -2.0e-6,
    'max(h) (m)': 10182.0,
    'min(h) (m)': 9052.0,
}

TABLE1_UNSTABLE = {
    'l2(vort) (1/s)': 2.1e-5,
    'max(vort) (1/s)': 9.3e-5,
    'min(vort) (1/s)': -7.3e-5,
}


class ComparisonAnalysis(OceanIOStep):
    """
    A base class for steps that compare the perturbed jet at each resolution
    with the figures of Galewsky et al. (2006) and Table 1 of Galewsky et al.
    (2004)

    Attributes
    ----------
    task_name : str
        The task, ``adjustment`` or ``unstable``

    resolutions : dict
        A dictionary with mesh names as keys and dicts with ``init`` and
        ``forward`` steps as values
    """

    def __init__(self, component, subdir, task_name, resolutions):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step resides in

        task_name : str
            The task, ``adjustment`` or ``unstable``

        resolutions : dict
            A dictionary with mesh names as keys and dicts with ``init`` and
            ``forward`` steps as values
        """
        super().__init__(component=component, name='analysis', subdir=subdir)
        self.task_name = task_name
        self.resolutions = resolutions

    def setup(self):
        """
        Add input files for each resolution, which may have been changed by
        user config options
        """
        super().setup()
        for mesh_name, steps in self.resolutions.items():
            init = steps['init']
            forward = steps['forward']
            self.add_input_file(
                filename=f'mesh_{mesh_name}.nc',
                work_dir_target=f'{init.path}/culled_mesh.nc',
            )
            self.add_input_file(
                filename=f'init_{mesh_name}.nc',
                work_dir_target=f'{init.path}/init.nc',
            )
            self.add_vert_coord_input_file(
                filename=f'vert_coord_{mesh_name}.nc',
                work_dir_target=f'{init.path}/vert_coord.nc',
            )
            self.add_input_file(
                filename=f'output_{mesh_name}.nc',
                work_dir_target=f'{forward.path}/output.nc',
            )
            self.add_output_file(f'{self.task_name}_{mesh_name}.png')
        self.add_output_file('table1_comparison.csv')

    def run(self):
        """
        Make the figures and the table comparing with Table 1
        """
        section = self.config[f'galewsky_jet_{self.task_name}']
        plot_times = section.getlist('plot_times', dtype=float)
        table_time = section.getfloat('table_time')

        rows = []
        for mesh_name in self.resolutions:
            fields = self.compute_fields(mesh_name, plot_times + [table_time])
            self.plot_resolution(mesh_name, fields, plot_times)
            row = {'resolution': mesh_name}
            row.update(self.table_row(fields[table_time]))
            rows.append(row)

        self.plot_all_resolutions(plot_times[-1])

        reference = {'resolution': 'Galewsky et al. (2004)'}
        reference.update(self.table1())
        rows.append(reference)
        df = pd.DataFrame(rows)
        df.to_csv(self.work_path('table1_comparison.csv'), index=False)
        self.logger.info(
            f'Comparison with Table 1 of Galewsky et al. (2004) at '
            f'{table_time:g} h:\n{df.to_string(index=False)}\n'
        )

    def compute_fields(self, mesh_name, times):
        """
        Compute the fields to plot and tabulate at the given times

        Parameters
        ----------
        mesh_name : str
            The name of the mesh

        times : list of float
            The times in hours

        Returns
        -------
        fields : dict
            A dict with times as keys and dicts of fields as values
        """
        raise NotImplementedError('Subclasses must override compute_fields')

    def plot_resolution(self, mesh_name, fields, plot_times):
        """
        Plot the fields at each plot time for one resolution

        Parameters
        ----------
        mesh_name : str
            The name of the mesh

        fields : dict
            A dict with times as keys and dicts of fields as values

        plot_times : list of float
            The times in hours
        """
        raise NotImplementedError('Subclasses must override plot_resolution')

    def plot_all_resolutions(self, time):
        """
        Plot all resolutions at one time, if the subclass does so

        Parameters
        ----------
        time : float
            The time in hours
        """
        pass

    def table_row(self, fields):
        """
        The values to compare with Table 1 for one resolution

        Parameters
        ----------
        fields : dict
            The fields at the time of the comparison

        Returns
        -------
        row : dict
            The values with the same keys as ``table1()``
        """
        raise NotImplementedError('Subclasses must override table_row')

    def table1(self):
        """
        The reference values from Table 1 of Galewsky et al. (2004)

        Returns
        -------
        reference : dict
            The reference values
        """
        raise NotImplementedError('Subclasses must override table1')

    def open_resolution(self, mesh_name, times):
        """
        Open the mesh and output for one resolution, and find the output
        record nearest each requested time

        Parameters
        ----------
        mesh_name : str
            The name of the mesh

        times : list of float
            The times in hours

        Returns
        -------
        ds_mesh : xarray.Dataset
            The mesh

        ds_out : xarray.Dataset
            The model output

        bottom_depth : numpy.ndarray
            The bottom depth at cells

        indices : dict
            The time index of the output record for each requested time
        """
        config = self.config
        model = config.get('ocean', 'model')
        ds_mesh = self.open_model_dataset(
            self.work_path(f'mesh_{mesh_name}.nc'), config
        )
        ds_init = self.open_model_dataset(
            self.work_path(f'init_{mesh_name}.nc'), config
        )
        ds_vert_coord = self.open_vert_coord_dataset(
            ds_init,
            vert_coord_filename=self.work_path(f'vert_coord_{mesh_name}.nc'),
        )
        ds_out = self.open_model_dataset(
            self.work_path(f'output_{mesh_name}.nc'),
            config,
            decode_times=False,
        )
        output_times = get_output_times(ds_out, model)
        indices = {}
        for time in times:
            index = int(np.argmin(np.abs(output_times - 3600.0 * time)))
            if abs(output_times[index] - 3600.0 * time) > 1.0:
                raise ValueError(
                    f'No output at {time:g} h in output_{mesh_name}.nc'
                )
            indices[time] = index
        bottom_depth = ds_vert_coord.bottomDepth.values
        return ds_mesh, ds_out, bottom_depth, indices


class AdjustmentAnalysis(ComparisonAnalysis):
    """
    A step comparing the early gravity-wave adjustment of the perturbed jet
    with Fig. 2 of Galewsky et al. (2006) and Table 1 of Galewsky et al.
    (2004)
    """

    def __init__(self, component, subdir, resolutions):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step resides in

        resolutions : dict
            A dictionary with mesh names as keys and dicts with ``init`` and
            ``forward`` steps as values
        """
        super().__init__(
            component=component,
            subdir=subdir,
            task_name='adjustment',
            resolutions=resolutions,
        )

    def compute_fields(self, mesh_name, times):
        """
        Compute the height, its change from the balanced state, and the
        divergence at the given times
        """
        ds_mesh, ds_out, bottom_depth, indices = self.open_resolution(
            mesh_name, times
        )
        params = get_jet_params(self.config)
        h_balanced = balanced_height(
            ds_mesh.latCell.values,
            u_max=params['u_max'],
            phi0=params['phi0'],
            phi1=params['phi1'],
            h_mean=params['h_mean'],
        )
        fields = {}
        for time, index in indices.items():
            ds = ds_out.isel(Time=index)
            h = ds.ssh.values + bottom_depth
            normal_velocity = ds.normalVelocity.isel(nVertLevels=0).values
            fields[time] = dict(
                h=h,
                h_change=h - h_balanced,
                div=divergence(ds_mesh, normal_velocity),
                lon=np.rad2deg(ds_mesh.lonCell.values),
                lat=np.rad2deg(ds_mesh.latCell.values),
                area=ds_mesh.areaCell.values,
            )
        return fields

    def plot_resolution(self, mesh_name, fields, plot_times):
        """
        Plot the height change and divergence as in Fig. 2 of Galewsky et
        al. (2006)
        """
        section = self.config['galewsky_jet_adjustment']
        h_interval = section.getfloat('h_contour_interval')
        div_interval = section.getfloat('div_contour_interval')
        columns = [
            (
                'h_change',
                f'Height minus balanced height (interval {h_interval:g} m)',
                h_interval,
            ),
            (
                'div',
                f'Divergence (interval {div_interval:g} 1/s)',
                div_interval,
            ),
        ]
        nrows = len(plot_times)
        with mplstyle_context():
            fig = Figure(figsize=(10.0, 2.6 * nrows), constrained_layout=True)
            axes = fig.subplots(nrows, 2, squeeze=False)
            for row, time in enumerate(plot_times):
                for col, (name, title, interval) in enumerate(columns):
                    ax = axes[row, col]
                    field = fields[time]
                    contour_lon_lat(
                        ax,
                        field['lon'],
                        field['lat'],
                        field[name],
                        interval,
                        lon_min=-180.0,
                        lat_bounds=(-90.0, 90.0),
                    )
                    ax.plot(0.0, 45.0, 'k*', markersize=8)
                    ax.set_xticks(np.arange(-120.0, 121.0, 60.0))
                    ax.set_yticks(np.arange(-60.0, 61.0, 30.0))
                    ax.text(
                        0.03,
                        0.06,
                        f'{time:g} hours',
                        transform=ax.transAxes,
                    )
                    if row == 0:
                        ax.set_title(title)
                    if row == nrows - 1:
                        ax.set_xlabel('Longitude (degrees)')
                    if col == 0:
                        ax.set_ylabel('Latitude (degrees)')
            fig.suptitle(f'{mesh_name}: adjustment, negative contours dashed')
            fig.savefig(self.work_path(f'adjustment_{mesh_name}.png'))

    def table_row(self, fields):
        """
        The divergence and height statistics to compare with Table 1
        """
        return {
            'l2(div) (1/s)': float(global_l2(fields['div'], fields['area'])),
            'max(div) (1/s)': float(fields['div'].max()),
            'min(div) (1/s)': float(fields['div'].min()),
            'max(h) (m)': float(fields['h'].max()),
            'min(h) (m)': float(fields['h'].min()),
        }

    def table1(self):
        """
        The reference values at 4 h from Table 1 of Galewsky et al. (2004)
        """
        return dict(TABLE1_ADJUSTMENT)


class UnstableAnalysis(ComparisonAnalysis):
    """
    A step comparing the vorticity of the perturbed, diffusive jet with
    Fig. 6 of Galewsky et al. (2006), Fig. 8 and Table 1 of Galewsky et al.
    (2004)

    Attributes
    ----------
    vorticity : dict
        The vorticity fields at each resolution, kept for the figure with all
        resolutions
    """

    def __init__(self, component, subdir, resolutions):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step resides in

        resolutions : dict
            A dictionary with mesh names as keys and dicts with ``init`` and
            ``forward`` steps as values
        """
        super().__init__(
            component=component,
            subdir=subdir,
            task_name='unstable',
            resolutions=resolutions,
        )
        self.vorticity = {}

    def setup(self):
        """
        Add input files and the figure with all resolutions
        """
        super().setup()
        self.add_output_file('unstable_all_resolutions.png')

    def compute_fields(self, mesh_name, times):
        """
        Compute the relative vorticity at the given times
        """
        ds_mesh, ds_out, _, indices = self.open_resolution(mesh_name, times)
        fields = {}
        for time, index in indices.items():
            ds = ds_out.isel(Time=index)
            normal_velocity = ds.normalVelocity.isel(nVertLevels=0).values
            fields[time] = dict(
                vort=relative_vorticity(ds_mesh, normal_velocity),
                lon=np.rad2deg(ds_mesh.lonVertex.values),
                lat=np.rad2deg(ds_mesh.latVertex.values),
                area=ds_mesh.areaTriangle.values,
            )
        self.vorticity[mesh_name] = fields
        return fields

    def plot_resolution(self, mesh_name, fields, plot_times):
        """
        Plot the vorticity as in Fig. 6 of Galewsky et al. (2006)
        """
        panels = [
            (fields[time], f'{time:g} hours', None) for time in plot_times
        ]
        self._plot_panels(
            panels,
            title=f'{mesh_name}: relative vorticity',
            filename=f'unstable_{mesh_name}.png',
        )

    def plot_all_resolutions(self, time):
        """
        Plot the vorticity at every resolution at one time, as in Fig. 8 of
        Galewsky et al. (2004)
        """
        panels = [
            (fields[time], None, mesh_name)
            for mesh_name, fields in self.vorticity.items()
        ]
        self._plot_panels(
            panels,
            title=f'Relative vorticity at {time:g} hours',
            filename='unstable_all_resolutions.png',
        )

    def table_row(self, fields):
        """
        The vorticity statistics to compare with Table 1
        """
        return {
            'l2(vort) (1/s)': float(global_l2(fields['vort'], fields['area'])),
            'max(vort) (1/s)': float(fields['vort'].max()),
            'min(vort) (1/s)': float(fields['vort'].min()),
        }

    def table1(self):
        """
        The reference values at 144 h from Table 1 of Galewsky et al. (2004)
        """
        return dict(TABLE1_UNSTABLE)

    def _plot_panels(self, panels, title, filename):
        """
        Plot vorticity contours in one column of panels on the longitude and
        latitude window of Fig. 6 of Galewsky et al. (2006)
        """
        interval = self.config.getfloat(
            'galewsky_jet_unstable', 'vort_contour_interval'
        )
        lon_ticks = np.arange(90.0, 441.0, 50.0)
        nrows = len(panels)
        with mplstyle_context():
            fig = Figure(figsize=(9.0, 2.4 * nrows), constrained_layout=True)
            axes = fig.subplots(nrows, 1, squeeze=False)[:, 0]
            for ax, (field, left_label, right_label) in zip(
                axes, panels, strict=True
            ):
                contour_lon_lat(
                    ax,
                    field['lon'],
                    field['lat'],
                    field['vort'],
                    interval,
                    lon_min=90.0,
                    lat_bounds=(10.0, 80.0),
                )
                ax.set_xticks(lon_ticks)
                ax.set_xticklabels(
                    [f'{np.mod(tick, 360.0):g}' for tick in lon_ticks]
                )
                ax.set_ylabel('Latitude (degrees)')
                for label, x, align in [
                    (left_label, 0.02, 'left'),
                    (right_label, 0.98, 'right'),
                ]:
                    if label is not None:
                        ax.text(
                            x,
                            0.88,
                            label,
                            transform=ax.transAxes,
                            horizontalalignment=align,
                        )
            axes[-1].set_xlabel('Longitude (degrees)')
            fig.suptitle(
                f'{title} (interval {interval:g} 1/s, negative dashed)'
            )
            fig.savefig(self.work_path(filename))
