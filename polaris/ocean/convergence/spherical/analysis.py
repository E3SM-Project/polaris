import datetime

import matplotlib.pyplot as plt
import numpy as np
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
            The dependencies of this step
        """
        super().__init__(component=component, name='analysis', subdir=subdir)
        self.resolutions = resolutions
        self.convergence_vars = convergence_vars
        self.icosahedral = icosahedral

        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            init = dependencies['init'][resolution]
            forward = dependencies['forward'][resolution]
            self.add_input_file(
                filename=f'{mesh_name}_mesh.nc',
                work_dir_target=f'{init.path}/mesh.nc')
            self.add_input_file(
                filename=f'{mesh_name}_init.nc',
                work_dir_target=f'{init.path}/initial_state.nc')
            self.add_input_file(
                filename=f'{mesh_name}_output.nc',
                work_dir_target=f'{forward.path}/output.nc')

        for _, var in convergence_vars.items():
            self.add_output_file(f'convergence_{var["name"]}.png')

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

        rmse = []
        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            rmse_res = self.compute_rmse(
                mesh_name=mesh_name,
                variable_name=convergence_field["name"],
                zidx=convergence_field["zidx"])
            rmse.append(rmse_res)

        convergence_failed = False
        title = convergence_field["title"]
        units = convergence_field["units"]

        res_array = np.array(resolutions)
        rmse_array = np.array(rmse)

        poly = np.polyfit(np.log10(res_array), np.log10(rmse_array), 1)
        convergence = poly[0]
        conv_round = np.round(convergence, 3)

        fit = res_array ** poly[0] * 10 ** poly[1]

        order1 = 0.5 * rmse_array[-1] * (res_array / res_array[-1])
        order2 = 0.5 * rmse_array[-1] * (res_array / res_array[-1])**2

        fig = plt.figure()
        ax = fig.add_subplot(111)
        ax.loglog(resolutions, order1, '--k', label='first order',
                  alpha=0.3)
        ax.loglog(resolutions, order2, 'k', label='second order',
                  alpha=0.3)
        ax.loglog(res_array, fit, 'k',
                  label=f'linear fit (order={conv_round})')
        ax.loglog(res_array, rmse_array, 'o', label='numerical')

        ax.set_xlabel('resolution (km)')
        ax.set_ylabel(f'RMS error ({units})')
        ax.set_title(f'Error Convergence of {title}')
        ax.legend(loc='lower left')
        ax.invert_xaxis()
        fig.savefig(f'convergence_{convergence_field["name"]}.png',
                    bbox_inches='tight', pad_inches=0.1)
        plt.close()

        logger.info(f'Order of convergence for {title}: '
                    f'{conv_round}')

        conv_thresh = convergence_field["conv_thresh"]
        if conv_thresh is not None:
            if convergence < conv_thresh:
                logger.error(f'Error: order of convergence for {title}\n'
                             f'  {conv_round} < min tolerance '
                             f'{conv_thresh}')
                convergence_failed = True

        conv_max = convergence_field["conv_max"]
        if conv_max is not None:
            if convergence > conv_max:
                logger.warn(f'Warning: order of convergence for {title}\n'
                            f'   {conv_round} > max tolerance '
                            f'{conv_max}')

        if convergence_failed:
            raise ValueError('Convergence rate below minimum tolerance.')

    def compute_rmse(self, mesh_name, variable_name, zidx=None):
        """
        Compute the RMSE for a given resolution

        Parameters
        ----------
        mesh_name : str
            The name of the mesh

        Returns
        -------
        rmse_h : float
            The root-mean-squared error in water-column thickness

        rmse_vel : float
            The root-mean-squared error in normal velocity
        """
        ds_out = xr.open_dataset(f'{mesh_name}_output.nc')
        config = self.config
        section = config['spherical_convergence']
        eval_time = section.getfloat('convergence_eval_time')
        s_per_day = 3600. * 24.
        tidx = _time_index_from_xtime(ds_out.xtime.values,
                                      eval_time * s_per_day)
        ds_out = ds_out.isel(Time=tidx)

        if zidx is not None:
            ds_out = ds_out.isel(nVertLevels=zidx)
        field_exact = self.exact_solution(mesh_name, variable_name)
        field_mpas = ds_out[variable_name].values
        diff = field_exact - field_mpas

        rmse = np.sqrt(np.mean(diff**2))

        return rmse

    def exact_solution(self, mesh_name, field_name):

        ds_init = xr.open_dataset(f'{mesh_name}_init.nc')
        ds_init = ds_init.isel(Time=0)

        return ds_init[field_name]


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
