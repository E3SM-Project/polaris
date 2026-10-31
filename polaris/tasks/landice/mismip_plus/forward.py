import shutil

import netCDF4
import numpy as np

from polaris.landice.mismip_plus.geometry import (
    ICE2_MELT_RATE,
    ICE2_MELT_X_MIN,
    ICE_DENSITY,
    SECONDS_PER_YEAR,
)
from polaris.tasks.landice.mismip_plus.model import MismipPlusModelStep

# the latent heat of fusion (J kg^-1) with which a standalone MALI build
# turns a heat flux into a melt rate
MALI_LATENT_HEAT = 335.0e3

# MALI's default config_dynamic_thickness (m), below which ice is not
# dynamic and the smallest thickness threshold for calving it allows
MALI_DYNAMIC_THICKNESS = 10.0


class Forward(MismipPlusModelStep):
    """
    A step for running a MISMIP+ experiment

    Attributes
    ----------
    experiment : polaris.tasks.landice.mismip_plus.experiments.Experiment
        The experiment

    start_year : int
        The year the experiment starts

    end_year : int
        The year the experiment ends
    """

    def __init__(self, component, experiment, indir, spin_up, previous=None):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        experiment : polaris.tasks.landice.mismip_plus.experiments.Experiment
            The experiment

        indir : str
            the directory the step is in, to which ``forward`` will be
            appended

        spin_up : polaris.tasks.landice.mismip_plus.spin_up.SpinUp
            The shared step with the steady state

        previous : polaris.tasks.landice.mismip_plus.forward.Forward, optional
            The step of the experiment this one starts from, if it does not
            start from the steady state
        """
        # the step is named for its experiment, since a task may have the
        # step of the experiment it starts from as well
        super().__init__(
            component=component,
            name=f'{experiment.subdir}_forward',
            subdir=f'{indir}/forward',
            restart_interval='0050-00-00_00:00:00',
            output_interval='0010-00-00_00:00:00',
        )
        self.experiment = experiment

        # MALI partitions its own mesh, the steady state
        self.make_graph = True
        self.mesh_filename = 'landice_grid.nc'

        # runtime_setup() writes the starting state from the steady state
        self.add_input_file(
            filename='steady_state.nc',
            work_dir_target=f'{spin_up.path}/steady_state.nc',
        )

        if previous is None:
            self.start_year = 0
            options = {
                'config_do_restart': False,
                'config_start_time': '0000-01-01_00:00:00',
            }
        else:
            self.start_year = previous.end_year
            restart_filename = previous.end_restart_filename
            self.add_input_file(
                filename=restart_filename,
                work_dir_target=f'{previous.path}/{restart_filename}',
            )
            self.add_dependency(previous, previous.name)
            options = {
                'config_do_restart': True,
                'config_start_time': f'{self.start_year:04d}-01-01_00:00:00',
            }
        self.end_year = self.start_year + experiment.years

        options['config_stop_time'] = f'{self.end_year:04d}-01-01_00:00:00'
        # time steps land on the snapshots in output.nc
        options['config_adaptive_timestep_force_interval'] = (
            '0010-00-00_00:00:00'
        )
        # calve floating ice too thin to be dynamic, which melting leaves
        # behind, and floating ice that melting cuts off from the grounded
        # ice, so the velocity solver does not fail on either
        options['config_calving'] = 'thickness_threshold'
        options['config_calving_thickness'] = MALI_DYNAMIC_THICKNESS
        options['config_remove_icebergs'] = True
        options.update(_get_melt_options(experiment.melt))
        self.add_model_config_options(options=options)

        self.add_output_file(filename='output.nc')
        self.add_output_file(filename=self.end_restart_filename)

    def runtime_setup(self):
        """
        Write the starting state, then set up MALI's namelist and partition
        the mesh
        """
        _write_starting_state(
            'steady_state.nc', 'landice_grid.nc', self.start_year
        )
        super().runtime_setup()

    @property
    def end_restart_filename(self):
        """
        The name of the restart file at the end of the experiment
        """
        return f'restart.{self.end_year:05d}.nc'


def _write_starting_state(in_filename, out_filename, start_year):
    """
    Copy the steady state, a MALI restart, with its time set to the start of
    the experiment, since MALI reads its starting state only at that time
    """
    shutil.copyfile(in_filename, out_filename)
    with netCDF4.Dataset(out_filename, 'a') as ds:
        xtime = ds.variables['xtime']
        xtime.set_auto_chartostring(False)
        # MALI writes times with 5-digit years, padded with null characters
        start = f'{start_year:05d}-01-01_00:00:00'.encode()
        xtime[0, :] = np.frombuffer(
            start.ljust(xtime.shape[-1], b'\0'), dtype='S1'
        )


def _get_melt_options(melt):
    """
    Get MALI's namelist options for the melt rate under floating ice
    """
    if melt == 'none':
        return {'config_basal_mass_bal_float': 'none'}
    if melt == 'mismip':
        # MALI's mismip option is Eq. 17 with the protocol's parameters
        return {'config_basal_mass_bal_float': 'mismip'}
    if melt == 'constant':
        # MALI takes a heat flux, which it divides by the density and latent
        # heat of ice to get the melt rate
        heat_flux = (
            ICE2_MELT_RATE / SECONDS_PER_YEAR * ICE_DENSITY * MALI_LATENT_HEAT
        )
        return {
            'config_basal_mass_bal_float': 'constant',
            'config_bmlt_float_flux': heat_flux,
            'config_bmlt_float_xlimit': ICE2_MELT_X_MIN,
        }
    raise ValueError(f'Unexpected melt option: {melt}')
