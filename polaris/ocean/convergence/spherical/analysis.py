import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from polaris import Step
from polaris.mpas import area_for_field, time_index_from_xtime
from polaris.ocean.resolution import resolution_to_subdir
from polaris.viz import use_mplstyle


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

    convergence_vars: list of dict
        The attributes for each variable for which to analyze the convergence
        rate. Each dict must contain the following keys:

            name : str
                The name of the variable as given in the output netcdf file

            title : str
                The name of the variable to use in the plot title

            zidx : int
                The z-index to use for variables that have an nVertLevels
                dimension, which should be None for variables that don't
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

        convergence_vars: list of dict
            The convergence attributes for each variable. Each dict must
            contain the following keys:

                name : str
                    The name of the variable as given in the output netcdf file

                title : str
                    The name of the variable to use in the plot title

                zidx : int
                    The z-index to use for variables that have an nVertLevels
                    dimension, which should be None for variables that don't
        """
        super().__init__(component=component, name='analysis', subdir=subdir)
        self.resolutions = resolutions
        self.icosahedral = icosahedral
        self.dependencies_dict = dependencies
        self.convergence_vars = convergence_vars

        for var in convergence_vars:
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
        for var in convergence_vars:
            self.plot_convergence(
                variable_name=var["name"],
                title=var["title"],
                zidx=var["zidx"])

    def plot_convergence(self, variable_name, title, zidx):
        """
        Compute the error norm for each resolution and produce a convergence
        plot

        Parameters
        ----------
        variable_name : str
            The name of the variable as given in the output netcdf file

        title : str
            The name of the variable to use in the plot title

        zidx : int
            The z-index to use for variables that have an nVertLevels
            dimension, which should be None for variables that don't
        """
        resolutions = self.resolutions
        logger = self.logger
        conv_thresh, error_type = self.convergence_parameters(
            field_name=variable_name)

        error = []
        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            error_res = self.compute_error(
                mesh_name=mesh_name,
                variable_name=variable_name,
                zidx=zidx,
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

        use_mplstyle()
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
        ax.set_ylabel(f'{error_title}')
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

        error_type: {'l2', 'inf'}, optional
            The type of error to compute

        Returns
        -------
        error : float
            The error of the variable given by variable_name
        """
        norm_type = {'l2': None, 'inf': np.inf}
        ds_mesh = xr.open_dataset(f'{mesh_name}_mesh.nc')
        config = self.config
        section = config['spherical_convergence']
        eval_time = section.getfloat('convergence_eval_time')
        s_per_day = 86400.0

        field_exact = self.exact_solution(mesh_name, variable_name,
                                          time=eval_time * s_per_day,
                                          zidx=zidx)
        field_mpas = self.get_output_field(mesh_name, variable_name,
                                           time=eval_time * s_per_day,
                                           zidx=zidx)
        diff = field_exact - field_mpas

        if error_type == 'l2':
            area = area_for_field(ds_mesh, diff)
            diff = diff * area

        error = np.linalg.norm(diff, ord=norm_type[error_type])

        if error_type == 'l2':
            field_exact = field_exact * area
            den_l2 = np.linalg.norm(field_exact, ord=norm_type[error_type])
            error = np.divide(error, den_l2)

        return error

    def exact_solution(self, mesh_name, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        mesh_name : str
            The mesh name which is the prefix for the initial condition file

        field_name : str
            The name of the variable of which we evaluate convergence
            For the default method, we use the same convergence rate for all
            fields

        time : float
            The time at which to evaluate the exact solution in seconds.
            For the default method, we always use the initial state.

        zidx : int, optional
            The z-index for the vertical level at which to evaluate the exact
            solution

        Returns
        -------
        solution : xarray.DataArray
            The exact solution as derived from the initial condition
        """

        ds_init = xr.open_dataset(f'{mesh_name}_init.nc')
        ds_init = ds_init.isel(Time=0)
        if zidx is not None:
            ds_init = ds_init.isel(nVertLevels=zidx)

        return ds_init[field_name]

    def get_output_field(self, mesh_name, field_name, time, zidx=None):
        """
        Get the model output field at the given time and z index

        Parameters
        ----------
        mesh_name : str
            The mesh name which is the prefix for the output file

        field_name : str
            The name of the variable of which we evaluate convergence

        time : float
            The time at which to evaluate the exact solution in seconds

        zidx : int, optional
            The z-index for the vertical level to take the field from

        Returns
        -------
        field_mpas : xarray.DataArray
            model output field
        """
        ds_out = xr.open_dataset(f'{mesh_name}_output.nc')

        tidx = time_index_from_xtime(ds_out.xtime.values, time)
        ds_out = ds_out.isel(Time=tidx)

        field_mpas = ds_out[field_name]
        if zidx is not None:
            field_mpas = field_mpas.isel(nVertLevels=zidx)
        return field_mpas

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
        conv_thresh : float
            The minimum convergence rate

        error_type : {'l2', 'inf'}, str
            The error norm to compute
        """
        config = self.config
        section = config['spherical_convergence']
        conv_thresh = section.getfloat('convergence_thresh')
        error_type = section.get('error_type')
        return conv_thresh, error_type
