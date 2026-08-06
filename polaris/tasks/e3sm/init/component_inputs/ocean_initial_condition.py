import os

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.tasks.e3sm.init.component_inputs.models import check_ocean_model


class OceanInitialConditionStep(Step):
    """
    A step for staging the MPAS-Ocean initial condition.

    The state E3SM should start from is the one the dynamic adjustment
    finished with, not the one it started from: the adjustment exists to
    dissipate the fast waves that an interpolated initial condition sets off,
    and staging ``initial_state``'s ``init.nc`` would hand every E3SM run that
    transient back.

    So the source is the final adjustment stage's restart.  Which stage that
    is, and what its restart is called, depend on the schedule, which is why
    :py:func:`~polaris.tasks.ocean.realistic_global.dynamic_adjustment.steps.get_realistic_dynamic_adjustment_steps`
    hands back the stages along with the steps.

    Attributes
    ----------
    forward_step : polaris.Step
        The final dynamic-adjustment stage.

    restart_filename : str
        The restart that stage writes, relative to its parent directory.
    """

    def __init__(
        self,
        component,
        subdir,
        forward_step,
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

        forward_step : polaris.Step
            The final dynamic-adjustment stage.

        restart_filename : str
            The restart that stage writes, relative to its parent directory
            (the stages share one ``restarts`` directory).

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.forward_step = forward_step
        self.restart_filename = restart_filename

        self.add_input_file(
            filename='restart.nc',
            work_dir_target=os.path.join(
                os.path.dirname(forward_step.path), restart_filename
            ),
        )
        # the restart is named from the schedule rather than from the step, so
        # the ordering cannot be inferred from the filename alone
        self.add_dependency(forward_step, forward_step.name)
        self.add_output_file(filename='ocean_initial_condition.nc')

    def setup(self):
        """
        Refuse a model whose packaging is not supported, before anything runs.
        """
        super().setup()
        check_ocean_model(self.config)

    def run(self):
        """
        Stage the adjusted restart as the initial condition.
        """
        super().run()
        check_ocean_model(self.config)

        with xr.open_dataset('restart.nc') as ds_in:
            ds_out = ds_in.load()

        # the restart's timestamp is where the adjustment ended, which says
        # nothing about when an E3SM run using it should start
        if 'xtime' in ds_out:
            ds_out = ds_out.drop_vars('xtime')

        write_netcdf(ds_out, 'ocean_initial_condition.nc')
