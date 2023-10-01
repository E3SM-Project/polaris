import datetime
import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from polaris import Step
from polaris.ocean.resolution import resolution_to_subdir


class SphericalConvergenceAnalysis(Step):
    """
    A step for analyzing the output from the geostrophic convergence test

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW
        meshes

    dependencies_dict : dict of dict of polaris.Steps
        The dependencies of this step must be given as separate keys in the
        dict:
            mesh : dict of polaris.Steps
                Keys of the dict correspond to `resolutions`
                Values of the dict are polaris.Steps, which must have the
                attribute `path`, the path to `base_mesh.nc` of that
                resolution
            init : dict of polaris.Steps
                Keys of the dict correspond to `resolutions`
                Values of the dict are polaris.Steps, which must have the
                attribute `path`, the path to `initial_state.nc` of that
                resolution
            forward : dict of polaris.Steps
                Keys of the dict correspond to `resolutions`
                Values of the dict are polaris.Steps, which must have the
                attribute `path`, the path to `forward.nc` of that
                resolution
    """
    def __init__(self, component, resolutions, icosahedral, subdir,
                 dependencies, convergence_vars):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step must be given as separate keys in the
            dict:
                mesh : dict of polaris.Steps
                    Keys of the dict correspond to `resolutions`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `base_mesh.nc` of that
                    resolution
                init : dict of polaris.Steps
                    Keys of the dict correspond to `resolutions`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `initial_state.nc` of that
                    resolution
                forward : dict of polaris.Steps
                    Keys of the dict correspond to `resolutions`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `forward.nc` of that
                    resolution
        """
        super().__init__(component=component, name='analysis', subdir=subdir)
        self.resolutions = resolutions
        self.icosahedral = icosahedral
        self.dependencies_dict = dependencies
        self.convergence_vars = convergence_vars

        for _, var in convergence_vars.items():
            self.add_output_file(f'convergence_{var["name"]}.png')

    def setup(self):
        """
        Add input files based on resolutions, which may have been changed by
        user config options
        """
        dependencies = self.dependencies_dict

        for resolution in self.resolutions:
            mesh_name = resolution_to_subdir(resolution)
            base_mesh = dependencies['mesh'][resolution]
            init = dependencies['init'][resolution]
            forward = dependencies['forward'][resolution]
            self.add_input_file(
                filename=f'{mesh_name}_mesh.nc',
                work_dir_target=f'{base_mesh.path}/base_mesh.nc')
            self.add_input_file(
                filename=f'{mesh_name}_init.nc',
                work_dir_target=f'{init.path}/initial_state.nc')
            self.add_input_file(
                filename=f'{mesh_name}_output.nc',
                work_dir_target=f'{forward.path}/output.nc')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        convergence_vars = self.convergence_vars
        for _, var in convergence_vars.items():
            self.plot_convergence(var)

    def plot_convergence(self, convergence_field):
        """
        Create a convergence plot

        Parameters
        ----------
        convergence_field: dict
            Dict containing attributes of the field of which to evaluate
            convergence
        """
        resolutions = self.resolutions
        logger = self.logger
        variable_name = convergence_field["name"]
        title = convergence_field["title"]
        units = convergence_field["units"]
        conv_thresh, conv_max, error_type = self.convergence_parameters(
            field_name=variable_name)

        error = []
        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            error_res = self.compute_error(
                mesh_name=mesh_name,
                variable_name=variable_name,
                zidx=convergence_field["zidx"],
                error_type=error_type)
            error.append(error_res)

        res_array = np.array(resolutions)
        error_array = np.array(error)
        filename = f'convergence_{variable_name}.csv'
        data = np.stack((res_array, error_array), axis=1)
        df = pd.DataFrame(data, columns=['resolution', error_type])
        df.to_csv(f'convergence_{variable_name}.csv', index=False)

        convergence_failed = False
        poly = np.polyfit(np.log10(res_array), np.log10(error_array), 1)
        convergence = poly[0]
        conv_round = np.round(convergence, 3)

        fit = res_array ** poly[0] * 10 ** poly[1]

        order1 = 0.5 * error_array[-1] * (res_array / res_array[-1])
        order2 = 0.5 * error_array[-1] * (res_array / res_array[-1])**2

        fig = plt.figure()

        error_dict = {'l2': 'L2 norm', 'inf': 'L-infinity norm'}
        error_title = error_dict[error_type]

        ax = fig.add_subplot(111)
        ax.loglog(resolutions, order1, '--k', label='first order',
                  alpha=0.3)
        ax.loglog(resolutions, order2, 'k', label='second order',
                  alpha=0.3)
        ax.loglog(res_array, fit, 'k',
                  label=f'linear fit (order={conv_round})')
        ax.loglog(res_array, error_array, 'o', label='numerical')

        if self.baseline_dir is not None:
            baseline_filename = os.path.join(self.baseline_dir, filename)
            if os.path.exists(baseline_filename):
                data = pd.read_csv(baseline_filename)
                if error_type not in data.keys():
                    raise ValueError(
                        f'{error_type} not available for baseline')
                else:
                    res_array = data.resolution.to_numpy()
                    error_array = data[error_type].to_numpy()
                    poly = np.polyfit(
                        np.log10(res_array), np.log10(error_array), 1)
                    base_convergence = poly[0]
                    conv_round = np.round(base_convergence, 3)

                    fit = res_array ** poly[0] * 10 ** poly[1]
                    ax.loglog(res_array, error_array, 'o', color='#ff7f0e',
                              label='baseline')
                    ax.loglog(res_array, fit, color='#ff7f0e',
                              label=f'linear fit, baseline '
                                    f'(order={conv_round})')
        ax.set_xlabel('resolution (km)')
        ax.set_ylabel(f'{error_title} ({units})')
        ax.set_title(f'Error Convergence of {title}')
        ax.legend(loc='lower left')
        ax.invert_xaxis()
        fig.savefig(f'convergence_{variable_name}.png',
                    bbox_inches='tight', pad_inches=0.1)
        plt.close()

        logger.info(f'Order of convergence for {title}: '
                    f'{conv_round}')

        if convergence < conv_thresh:
            logger.error(f'Error: order of convergence for {title}\n'
                         f'  {conv_round} < min tolerance '
                         f'{conv_thresh}')
            convergence_failed = True

        if convergence > conv_max:
            logger.warn(f'Warning: order of convergence for {title}\n'
                        f'   {conv_round} > max tolerance '
                        f'{conv_max}')

        if convergence_failed:
            raise ValueError('Convergence rate below minimum tolerance.')

    def compute_error(self, mesh_name, variable_name, zidx=None,
                      error_type='l2'):
        """
        Compute the error for a given resolution

        Parameters
        ----------
        mesh_name : str
            The name of the mesh

        variable_name : str
            The variable name of which to evaluate error with respect to the
            exact solution

        zidx : int, optional
            The z index to use to slice the field given by variable name

        error_type: str, optional
            The type of error to compute. One of 'l2' or 'inf'.

        Returns
        -------
        error : float
            The error of the variable given by variable_name
        """
        ds_mesh = xr.open_dataset(f'{mesh_name}_mesh.nc')
        ds_out = xr.open_dataset(f'{mesh_name}_output.nc')
        config = self.config
        section = config['spherical_convergence']
        eval_time = section.getfloat('convergence_eval_time')
        s_per_day = 86400.0
        tidx = _time_index_from_xtime(ds_out.xtime.values,
                                      eval_time * s_per_day)
        ds_out = ds_out.isel(Time=tidx)

        if zidx is not None:
            ds_out = ds_out.isel(nVertLevels=zidx)
        field_exact = self.exact_solution(mesh_name, variable_name,
                                          time=eval_time * s_per_day,
                                          zidx=zidx)
        field_mpas = ds_out[variable_name].values
        diff = field_exact - field_mpas

        if error_type == 'l2':
            area_cell = ds_mesh.areaCell.values
            total_area = np.sum(area_cell)
            den_l2 = np.sum(field_exact**2 * area_cell) / total_area
            num_l2 = np.sum(diff**2 * area_cell) / total_area
            error = np.sqrt(num_l2) / np.sqrt(den_l2)
        elif error_type == 'inf':
            error = np.amax(diff) / np.amax(np.abs(field_exact))
        else:
            raise ValueError(f'Unsupported error type {error_type}')

        return error

    def exact_solution(self, mesh_name, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        field_name : str
            The name of the variable of which we evaluate convergence
            For the default method, we use the same convergence rate for all
            fields

        time : float
            The time at which to evaluate the exact solution in seconds.
            For the default method, we always use the initial state.

        Returns
        -------
        solution: np.ndarray of type float
            The minimum convergence rate
        """

        ds_init = xr.open_dataset(f'{mesh_name}_init.nc')
        ds_init = ds_init.isel(Time=0)
        if zidx is not None:
            ds_init = ds_init.isel(nVertLevels=zidx)

        return ds_init[field_name]

    def convergence_parameters(self, field_name=None):
        """
        Get convergence parameters

        Parameters
        ----------
        field_name : str
            The name of the variable of which we evaluate convergence
            For the default method, we use the same convergence rate for all
            fields

        Returns
        -------
        conv_thresh: float
            The minimum convergence rate

        conv_thresh: float
            The maximum convergence rate
        """
        config = self.config
        section = config['spherical_convergence']
        conv_thresh = section.getfloat('convergence_thresh')
        conv_max = section.getfloat('convergence_max')
        error_type = section.get('error_type')
        return conv_thresh, conv_max, error_type


def _time_index_from_xtime(xtime, dt_target):
    """
    Determine the time index at which to evaluate convergence

    Parameters
    ----------
    xtime: list of str
        Times in the dataset
    dt_target: float
        Time in seconds at which to evaluate convergence

    Returns
    -------
    tidx: int
        Index in xtime that is closest to dt_target
    """
    t0 = datetime.datetime.strptime(xtime[0].decode(),
                                    '%Y-%m-%d_%H:%M:%S')
    dt = np.zeros((len(xtime)))
    for idx, xt in enumerate(xtime):
        t = datetime.datetime.strptime(xt.decode(),
                                       '%Y-%m-%d_%H:%M:%S')
        dt[idx] = (t - t0).total_seconds()
    return np.argmin(np.abs(np.subtract(dt, dt_target)))
