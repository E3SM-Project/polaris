import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from polaris import Step
from polaris.mpas import time_index_from_xtime
from polaris.ocean.convergence import get_resolution_for_task
from polaris.ocean.resolution import resolution_to_subdir
from polaris.viz import use_mplstyle


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
    def __init__(self, component, refinement_factors, icosahedral, subdir,
                 case_name, dependencies, refinement='both'):
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
        self.refinement_factors = refinement_factors
        self.refinement = refinement
        self.case_name = case_name

        for refinement_factor in refinement_factors:
            base_mesh = dependencies['mesh'][refinement_factor]
            init = dependencies['init'][refinement_factor]
            forward = dependencies['forward'][refinement_factor]
            self.add_input_file(
                filename=f'mesh_r{refinement_factor:02g}.nc',
                work_dir_target=f'{base_mesh.path}/base_mesh.nc')
            self.add_input_file(
                filename=f'init_r{refinement_factor:02g}.nc',
                work_dir_target=f'{init.path}/initial_state.nc')
            self.add_input_file(
                filename=f'output_r{refinement_factor:02g}.nc',
                work_dir_target=f'{forward.path}/output.nc')
        self.add_output_file('filament.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        resolutions = list()
        for refinement_factor in self.refinement_factors:
            resolution = get_resolution_for_task(
                self.config, refinement_factor, self.refinement)
            resolutions.append(resolution)
        config = self.config
        section = config[self.case_name]
        eval_time = section.getfloat('filament_evaluation_time')
        s_per_day = 86400.0
        zidx = 1
        variable_name = 'tracer2'
        num_tau = 21
        filament_tau = np.linspace(0, 1, num_tau)
        filament_norm = np.zeros((len(resolutions), num_tau))
        use_mplstyle()
        fig, ax = plt.subplots()
        for i, refinement_factor in enumerate(self.refinement_factors):
            mesh_name = resolution_to_subdir(resolutions[i])
            ds = xr.open_dataset(f'output_r{refinement_factor:02g}.nc')
            tidx = time_index_from_xtime(ds.xtime.values,
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
