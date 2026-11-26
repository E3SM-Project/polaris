import os

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.tasks.ocean.realistic_global.init.remap_shortwave_extinction import (  # noqa: E501
    OMEGA_VAR_NAMES,
    SHORTWAVE_EXTINCTION_COEFFS_FILENAME,
)

#: The fields Omega reads from its initial state at startup: its ``State``
#: group (``NormalVelocity`` and ``PseudoThickness`` from the ocean state,
#: ``SurfacePressure`` from the vertical coordinate) and its ``Base`` tracers.
#: These are taken from the adjusted restart.
STATE_VARS = [
    'NormalVelocity',
    'PseudoThickness',
    'SurfacePressure',
    'Temperature',
    'Salinity',
]

#: The shortwave extinction coefficients Omega's ``ShortwaveExtinctionIn``
#: stream reads, which E3SM points at the initial condition like its other
#: input streams
EXTINCTION_VARS = list(OMEGA_VAR_NAMES.values())


class OmegaInitialConditionStep(Step):
    """
    A step for building the Omega initial condition from the adjusted state.

    As for MPAS-Ocean, the state comes from the final dynamic-adjustment
    stage's restart rather than from the initial state, which would hand
    every E3SM run the transient the adjustment exists to dissipate.  Unlike
    MPAS-Ocean's, Omega's restart holds only the state, so the horizontal
    mesh and the vertical coordinate come from the files Omega's
    ``initial_state`` step wrote, which Polaris' own Omega runs read through
    the same streams.  The shortwave extinction coefficients come from the
    realistic-global init step that remaps them to the mesh, so that E3SM
    reads all four of its input streams from one file.

    The initial state's diagnostic fields, such as ``SshCell`` and
    ``Density``, are left out: they describe the state before the adjustment.

    Attributes
    ----------
    init_step : polaris.Step
        Omega's initial-state step.

    forward_step : polaris.Step
        The final dynamic-adjustment stage.

    check_step : polaris.Step
        The check of the final stage.

    extinction_step : polaris.Step
        The step that remaps the shortwave extinction coefficients.
    """

    def __init__(
        self,
        component,
        subdir,
        init_step,
        forward_step,
        check_step,
        extinction_step,
        restart_filename,
        name='ocean_initial_condition',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        init_step : polaris.Step
            Omega's initial-state step, which wrote ``mesh.nc`` and
            ``vert_coord.nc``.

        forward_step : polaris.Step
            The final dynamic-adjustment stage.

        check_step : polaris.Step
            The check of the final stage, which has to pass before the
            restart is staged.

        extinction_step : polaris.Step
            The step that wrote the shortwave extinction coefficients on the
            mesh.

        restart_filename : str
            The restart Omega writes at the end of that stage, relative to
            the stage's work directory.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.init_step = init_step
        self.forward_step = forward_step
        self.check_step = check_step
        self.extinction_step = extinction_step

        for filename in ['mesh.nc', 'vert_coord.nc']:
            self.add_input_file(
                filename=filename,
                work_dir_target=os.path.join(init_step.path, filename),
            )
        self.add_input_file(
            filename=SHORTWAVE_EXTINCTION_COEFFS_FILENAME,
            work_dir_target=os.path.join(
                extinction_step.path, SHORTWAVE_EXTINCTION_COEFFS_FILENAME
            ),
        )
        self.add_input_file(
            filename='restart.nc',
            work_dir_target=os.path.normpath(
                os.path.join(forward_step.path, restart_filename)
            ),
        )
        # the restart is named from the schedule rather than from the step,
        # and a failed check has to stop the staging
        self.add_dependency(forward_step, forward_step.name)
        self.add_dependency(check_step, check_step.name)
        self.add_output_file(filename='ocean_initial_condition.nc')

    def run(self):
        """
        Merge the mesh, the vertical coordinate, the adjusted state and the
        shortwave extinction coefficients.
        """
        super().run()
        with xr.open_dataset('mesh.nc') as ds_mesh:
            ds_out = ds_mesh.load()
        with xr.open_dataset('vert_coord.nc') as ds_vert:
            ds_out = ds_out.merge(ds_vert.load())
        with xr.open_dataset('restart.nc') as ds_restart:
            missing = [var for var in STATE_VARS if var not in ds_restart]
            if missing:
                raise ValueError(
                    f'The adjusted restart has no {", ".join(missing)}.'
                )
            ds_state = ds_restart[STATE_VARS].load()

        # the restart's time is where the adjustment ended, which says
        # nothing about when an E3SM run using it should start; the fields
        # keep their time dimension, as in any Omega initial state
        ds_state = ds_state.drop_vars('time', errors='ignore')
        ds_out = ds_out.merge(ds_state)

        with xr.open_dataset(SHORTWAVE_EXTINCTION_COEFFS_FILENAME) as ds_ext:
            missing = [var for var in EXTINCTION_VARS if var not in ds_ext]
            if missing:
                raise ValueError(
                    f'{SHORTWAVE_EXTINCTION_COEFFS_FILENAME} has no '
                    f'{", ".join(missing)}.'
                )
            ds_out = ds_out.merge(ds_ext[EXTINCTION_VARS].load())

        # config options belong to the run that produced the file, and the
        # simulation time to the restart
        for attr in list(ds_out.attrs):
            if attr.startswith('config_') or attr == 'SimulationTime':
                ds_out.attrs.pop(attr)

        write_netcdf(ds_out, 'ocean_initial_condition.nc')
