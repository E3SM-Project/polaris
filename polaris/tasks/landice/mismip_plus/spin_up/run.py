import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.tasks.landice.mismip_plus.model import MismipPlusModelStep

# the intervals in years between restarts and between snapshots in
# output.nc in the spin-up
RESTART_INTERVAL_YEARS = 250
OUTPUT_INTERVAL_YEARS = 50

# how far in m a starting state's cell centers may be from the mesh's
COORDINATE_TOLERANCE = 1.0


class SpinUpRun(MismipPlusModelStep):
    """
    A step for running MALI from a starting state toward the MISMIP+ steady
    state.  When it is rerun, for example after a job reaches its wall-clock
    limit, it continues from its latest restart.
    """

    def __init__(self, component, init, mesh_step, subdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        init : polaris.tasks.landice.mismip_plus.init.Init
            The shared step with the initial condition

        mesh_step : polaris.tasks.mesh.planar.mismip_plus.MismipPlusMesh
            The shared step that makes the mesh

        subdir : str
            The subdirectory for the step
        """
        output_interval = f'{OUTPUT_INTERVAL_YEARS:04d}-00-00_00:00:00'
        super().__init__(
            component=component,
            name='run',
            subdir=subdir,
            restart_interval=f'{RESTART_INTERVAL_YEARS:04d}-00-00_00:00:00',
            output_interval=output_interval,
            # a continued run adds to output.nc
            output_clobber_mode='overwrite',
        )
        self.add_input_file(
            filename='init.nc',
            work_dir_target=f'{init.path}/landice_grid.nc',
        )
        self.add_input_file(
            filename='graph.info',
            work_dir_target=f'{mesh_step.path}/graph.info',
        )
        # time steps land on the snapshots, and so on the restarts
        self.add_model_config_options(
            options={
                'config_adaptive_timestep_force_interval': output_interval
            }
        )
        self.add_output_file(filename='output.nc')

    def runtime_setup(self):
        """
        Write the starting state if the run has not started yet, then set up
        MALI's namelist and partition the mesh
        """
        if get_restart_year(self.work_dir) is None:
            self._write_starting_state()
        super().runtime_setup()

    def dynamic_model_config(self, at_setup):
        """
        Start from the starting state or continue from the latest restart,
        and stop after the spin-up's length

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup)
        run_years = self.config.getint('mismip_plus_spin_up', 'run_years')
        if run_years % RESTART_INTERVAL_YEARS != 0:
            raise ValueError(
                f'run_years must be a multiple of {RESTART_INTERVAL_YEARS}'
            )

        restart_year = None
        if not at_setup:
            restart_year = get_restart_year(self.work_dir)
        if restart_year is None:
            options = {
                'config_do_restart': False,
                'config_start_time': '0000-01-01_00:00:00',
            }
        else:
            options = {
                'config_do_restart': True,
                'config_start_time': 'file',
            }
        options['config_stop_time'] = f'{run_years:04d}-01-01_00:00:00'
        self.add_model_config_options(options=options)

    def _write_starting_state(self):
        """
        Write the initial condition, with the thickness of the starting state
        if it is not the slab
        """
        logger = self.logger
        initial_state = self.config.get('mismip_plus_spin_up', 'initial_state')
        ds = xr.open_dataset('init.nc').load()
        if initial_state != 'slab':
            logger.info(f'Starting from the thickness in {initial_state}')
            ds_start = xr.open_dataset(initial_state)
            _check_coordinates(ds, ds_start, initial_state)
            thickness = ds_start.thickness
            if 'Time' in thickness.dims:
                thickness = thickness.isel(Time=-1)
            ds['thickness'][0, :] = thickness.values
        write_netcdf(ds, 'landice_grid.nc')


def get_restart_year(work_dir):
    """
    Get the year of the latest restart MALI wrote in a directory

    Parameters
    ----------
    work_dir : str
        The directory MALI ran in

    Returns
    -------
    year : int or None
        The year of the latest restart, or ``None`` if there is none
    """
    filename = os.path.join(work_dir, 'restart_timestamp')
    if not os.path.exists(filename):
        return None
    with open(filename) as timestamp_file:
        timestamp = timestamp_file.read().strip()
    return int(timestamp.split('-')[0])


def _check_coordinates(ds_mesh, ds_start, filename):
    """
    Make sure a starting state is on the same mesh
    """
    if ds_start.sizes['nCells'] != ds_mesh.sizes['nCells']:
        raise ValueError(
            f'{filename} has {ds_start.sizes["nCells"]} cells, but the mesh '
            f'has {ds_mesh.sizes["nCells"]}'
        )
    distance = np.sqrt(
        (ds_start.xCell.values - ds_mesh.xCell.values) ** 2
        + (ds_start.yCell.values - ds_mesh.yCell.values) ** 2
    )
    if distance.max() > COORDINATE_TOLERANCE:
        raise ValueError(
            f'The cell centers in {filename} are up to {distance.max():g} m '
            f'from those of the mesh'
        )
