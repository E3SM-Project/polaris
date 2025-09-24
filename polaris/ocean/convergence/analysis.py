import os

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from polaris.mpas import area_for_field, time_since_start
from polaris.ocean.convergence import (
    get_resolution_for_task,
    get_timestep_for_task,
)
from polaris.ocean.model import OceanIOStep
from polaris.viz import use_mplstyle


class ConvergenceAnalysis(OceanIOStep):
    """
    A step for analyzing the output from convergence tests

    Attributes
    ----------
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

    refinement : str
        Refinement type. One of 'space', 'time' or 'both' indicating both
        space and time

    mesh_filename : str
        The name of the mesh file to use for calculating mesh metrics
        (i.e. cell area) needed for computing the error
    """

    def __init__(
        self,
        component,
        subdir,
        dependencies,
        convergence_vars,
        refinement='both',
        mesh_filename='base_mesh.nc',
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory that the step resides in

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step must be given as separate keys in the
            dict:

                mesh : dict of polaris.Steps
                    Keys of the dict correspond to `refinement_factors`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `base_mesh.nc` of that
                    resolution
                init : dict of polaris.Steps
                    Keys of the dict correspond to `refinement_factors`
                    Values of the dict are polaris.Steps, which must have the
                    attribute `path`, the path to `initial_state.nc` of that
                    resolution
                forward : dict of polaris.Steps
                    Keys of the dict correspond to `refinement_factors`
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

        refinement : str, optional
            Refinement type. One of 'space', 'time' or 'both' indicating both
            space and time

        mesh_filename : str
            The name of the mesh file to use for calculating mesh metrics
            (i.e. cell area) needed for computing the error
        """
        super().__init__(component=component, name='analysis', subdir=subdir)

        self.dependencies_dict = dependencies
        self.convergence_vars = convergence_vars
        self.refinement = refinement
        self.mesh_filename = mesh_filename

        for var in convergence_vars:
            self.add_output_file(f'convergence_{var["name"]}.png')

    def setup(self):
        """
        Add input files based on resolutions, which may have been changed by
        user config options
        """
        super().setup()
        config = self.config
        dependencies = self.dependencies_dict
        if self.refinement == 'time':
            option = 'refinement_factors_time'
        else:
            option = 'refinement_factors_space'
        refinement_factors = config.getlist('convergence', option, dtype=float)
        for refinement_factor in refinement_factors:
            mesh = dependencies['mesh'][refinement_factor]
            init = dependencies['init'][refinement_factor]
            forward = dependencies['forward'][refinement_factor]
            self.add_input_file(
                filename=f'mesh_r{refinement_factor:02g}.nc',
                work_dir_target=f'{mesh.path}/{self.mesh_filename}',
            )
            self.add_input_file(
                filename=f'init_r{refinement_factor:02g}.nc',
                work_dir_target=f'{init.path}/initial_state.nc',
            )
            self.add_input_file(
                filename=f'output_r{refinement_factor:02g}.nc',
                work_dir_target=f'{forward.path}/output.nc',
            )

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        convergence_vars = self.convergence_vars
        variables_failed = []
        for var in convergence_vars:
            convergence_failed = self.plot_convergence(
                variable_name=var['name'], title=var['title'], zidx=var['zidx']
            )
            if convergence_failed:
                variables_failed.append(var['name'])
        if len(variables_failed) >= 1:
            raise ValueError(
                'Convergence rate below minimum tolerance for '
                f'variables {", ".join(variables_failed)}.'
            )

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
        config = self.config
        logger = self.logger
        conv_thresh, error_type = self.convergence_parameters(
            field_name=variable_name
        )

        error = []
        if self.refinement == 'time':
            option = 'refinement_factors_time'
            header = 'time step'
        else:
            option = 'refinement_factors_space'
            header = 'resolution'
        refinement_factors = config.getlist('convergence', option, dtype=float)
        resolutions = list()
        timesteps = list()
        for refinement_factor in refinement_factors:
            timestep, _ = get_timestep_for_task(
                config, refinement_factor, refinement=self.refinement
            )
            timesteps.append(timestep)
            resolution = get_resolution_for_task(
                config, refinement_factor, refinement=self.refinement
            )
            resolutions.append(resolution)
            error_res = self.compute_error(
                refinement_factor=refinement_factor,
                variable_name=variable_name,
                zidx=zidx,
                error_type=error_type,
            )
            error.append(error_res)

        if self.refinement == 'time':
            refinement_array = np.array(timesteps)
            x_label = 'Time (s)'
        else:
            refinement_array = np.array(resolutions)
            x_label = 'Horizontal resolution (km)'
        error_array = np.array(error)
        filename = f'convergence_{variable_name}.csv'
        data = np.stack((refinement_array, error_array), axis=1)
        df = pd.DataFrame(data, columns=[header, error_type])
        df.to_csv(f'convergence_{variable_name}.csv', index=False)

        convergence_failed = False
        poly = np.polyfit(np.log10(refinement_array), np.log10(error_array), 1)
        convergence = poly[0]
        conv_round = convergence

        fit = refinement_array ** poly[0] * 10 ** poly[1]

        order1 = (
            0.5 * error_array[-1] * (refinement_array / refinement_array[-1])
        )
        order2 = (
            0.5
            * error_array[-1]
            * (refinement_array / refinement_array[-1]) ** 2
        )

        use_mplstyle()
        fig = plt.figure()

        error_dict = {'l2': 'L2 norm', 'inf': 'L-infinity norm'}
        error_title = error_dict[error_type]

        ax = fig.add_subplot(111)
        ax.loglog(
            refinement_array, order1, '--k', label='first order', alpha=0.3
        )
        ax.loglog(
            refinement_array, order2, 'k', label='second order', alpha=0.3
        )
        ax.loglog(
            refinement_array,
            fit,
            'k',
            label=f'linear fit (order={convergence:1.3f})',
        )
        ax.loglog(refinement_array, error_array, 'o', label='numerical')

        if self.baseline_dir is not None:
            baseline_filename = os.path.join(self.baseline_dir, filename)
            if os.path.exists(baseline_filename):
                data = pd.read_csv(baseline_filename)
                if error_type not in data.keys():
                    raise ValueError(
                        f'{error_type} not available for baseline'
                    )
                else:
                    refinement_array = data.resolution.to_numpy()
                    error_array = data[error_type].to_numpy()
                    poly = np.polyfit(
                        np.log10(refinement_array), np.log10(error_array), 1
                    )
                    base_convergence = poly[0]
                    conv_round = base_convergence

                    fit = refinement_array ** poly[0] * 10 ** poly[1]
                    ax.loglog(
                        refinement_array,
                        error_array,
                        'o',
                        color='#ff7f0e',
                        label='baseline',
                    )
                    ax.loglog(
                        refinement_array,
                        fit,
                        color='#ff7f0e',
                        label=f'linear fit, baseline '
                        f'(order={base_convergence:1.3f})',
                    )
        ax.set_xlabel(x_label)
        ax.set_ylabel(f'{error_title}')
        ax.set_title(f'Error Convergence of {title}')
        ax.legend(loc='lower left')
        ax.invert_xaxis()
        fig.savefig(
            f'convergence_{variable_name}.png',
            bbox_inches='tight',
            pad_inches=0.1,
        )
        plt.close()

        logger.info(f'Order of convergence for {title}: {conv_round:1.3f}')

        if conv_round < conv_thresh:
            logger.error(
                f'Error: order of convergence for {title}\n'
                f'  {conv_round:1.3f} < min tolerance '
                f'{conv_thresh}'
            )
            convergence_failed = True

        return convergence_failed

    def compute_error(
        self, refinement_factor, variable_name, zidx=None, error_type='l2'
    ):
        """
        Compute the error for a given resolution

        Parameters
        ----------
        refinement_factor : float
            The factor by which step is refined in space, time or both

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
        ds_mesh = self.open_model_dataset(f'mesh_r{refinement_factor:02g}.nc')
        config = self.config
        section = config['convergence']
        eval_time = section.getfloat('convergence_eval_time')
        s_per_hour = 3600.0

        field_exact = self.exact_solution(
            refinement_factor,
            variable_name,
            time=eval_time * s_per_hour,
            zidx=zidx,
        )
        field_mpas = self.get_output_field(
            refinement_factor,
            variable_name,
            time=eval_time * s_per_hour,
            zidx=zidx,
        )
        diff = field_exact - field_mpas
        # We support nans in the fields, used to indicate regions where
        # convergence should not be evaluated
        mask = np.logical_and(field_exact == field_exact,
                              field_mpas == field_mpas)

        diff = field_exact - field_mpas
        # Only the L2 norm is area-weighted
        if error_type == 'l2':
            area = area_for_field(ds_mesh, diff)
            mean_area = area.mean()
            field_exact = field_exact[mask] * area[mask] / mean_area
            diff = diff[mask] * area[mask] / mean_area

        error = np.linalg.norm(diff, ord=norm_type[error_type])

        # Normalize the error norm by the vector norm of the exact solution
        den = np.linalg.norm(field_exact, ord=norm_type[error_type])
        error = np.divide(error, den)

        return error

    def exact_solution(self, refinement_factor, field_name, time, zidx=None):
        """
        Get the exact solution

        Parameters
        ----------
        refinement_factor : float
            The factor by which step is refined in space, time or both

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

        ds_init = self.open_model_dataset(f'init_r{refinement_factor:02g}.nc')
        ds_init = ds_init.isel(Time=0)
        if zidx is not None:
            ds_init = ds_init.isel(nVertLevels=zidx)

        return ds_init[field_name]

    def get_output_field(self, refinement_factor, field_name, time, zidx=None):
        """
        Get the model output field at the given time and z index

        Parameters
        ----------
        e str
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
        config = self.config
        ds_out = self.open_model_dataset(
            f'output_r{refinement_factor:02g}.nc', decode_times=False
        )

        model = config.get('ocean', 'model')
        if model == 'mpas-o':
            dt = time_since_start(ds_out.xtime.values)
        else:
            # time is seconds since the start of the simulation in Omega
            dt = ds_out.Time.values

        tidx = np.argmin(np.abs(dt - time))

        ds_out = ds_out.isel(Time=tidx)
        field_mpas = ds_out[field_name]
        if zidx is not None and 'nVertLevels' in field_mpas.dims:
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
        section = config['convergence']
        conv_thresh = section.getfloat('convergence_thresh')
        error_type = section.get('error_type')
        return conv_thresh, error_type
