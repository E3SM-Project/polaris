import datetime

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from polaris import Step
from polaris.ocean.resolution import resolution_to_subdir


class FilamentAnalysis(Step):
    """
    A step for analyzing the output from sphere transport test cases

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW
        meshes

    case_name : str
        The name of the test case
    """
    def __init__(self, component, resolutions, icosahedral, subdir,
                 case_name, dependencies):
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

        case_name: str
            The name of the test case

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        super().__init__(component=component, name='filament_analysis',
                         subdir=subdir)
        self.resolutions = resolutions
        self.case_name = case_name

        for resolution in resolutions:
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
        self.add_output_file('filament.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        resolutions = self.resolutions
        config = self.config
        section = config[self.case_name]
        eval_time = section.getfloat('filament_evaluation_time')
        s_per_day = 86400.0
        zidx = 1
        variable_name = 'tracer2'
        num_tau = 21
        filament_tau = np.linspace(0, 1, num_tau)
        filament_norm = np.zeros((len(resolutions), num_tau))
        fig, ax = plt.subplots()
        for i, resolution in enumerate(resolutions):
            mesh_name = resolution_to_subdir(resolution)
            ds = xr.open_dataset(f'{mesh_name}_output.nc')
            tidx = _time_index_from_xtime(ds.xtime.values,
                                          eval_time * s_per_day)
            tracer = ds[variable_name]
            area_cell = ds["areaCell"]
            for j, tau in enumerate(filament_tau):
                cells_above_tau = tracer[tidx, :, zidx] >= tau
                cells_above_tau0 = tracer[0, :, zidx] >= tau
                if np.sum(cells_above_tau0 * area_cell) == 0.:
                    filament_norm[i, j] = np.nan
                else:
                    filament_norm[i, j] = np.divide(
                        np.sum(area_cell * cells_above_tau),
                        np.sum(cells_above_tau0 * area_cell))
            plt.plot(filament_tau, filament_norm[i, :], '.-', label=mesh_name)
        plt.plot([filament_tau[0], filament_tau[-1]], [1., 1.], 'k--')
        ax.set_xlim([filament_tau[0], filament_tau[-1]])
        ax.set_xlabel(r'$\tau$')
        ax.set_ylabel(r'$l_f$')
        plt.title(f'Filament preservation diagnostic for {variable_name}')
        plt.legend()
        fig.savefig('filament.png', bbox_inches='tight')

        res_array = np.array(resolutions, dtype=float)
        data = np.column_stack((res_array, filament_norm))
        col_headers = ['resolution']
        for tau in filament_tau:
            col_headers.append(f'{tau:g}')
        df = pd.DataFrame(data, columns=col_headers)
        df.to_csv('filament.csv', index=False)


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
