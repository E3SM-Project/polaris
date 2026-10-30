import os

from mpas_tools.io import open_dataset, write_netcdf

from polaris.step import Step


class OceanInitialConditionStep(Step):
    """
    A step for making the MPAS-Ocean initial condition E3SM reads: the mesh
    and the state the SSH adjustment finished with, in one file

    Standalone MPAS-Ocean reads the mesh through a stream of its own, so the
    SSH adjustment's output holds only the state.  E3SM's MPAS-Ocean reads
    both from its initial condition.
    """

    def __init__(self, component, subdir, init_step, ssh_adjust_step):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        init_step : polaris.tasks.ocean.misomip.MisomipInit
            The step that wrote the ocean's mesh

        ssh_adjust_step : polaris.ocean.ice_shelf.ssh_adjustment.SshAdjustment
            The final iteration of the SSH adjustment
        """
        super().__init__(
            component=component, name='ocean_initial_condition', subdir=subdir
        )
        self.add_input_file(
            filename='mesh.nc',
            work_dir_target=os.path.join(init_step.path, 'mesh.nc'),
        )
        self.add_input_file(
            filename='state.nc',
            work_dir_target=os.path.join(ssh_adjust_step.path, 'output.nc'),
        )
        self.add_output_file(filename='ocean_initial_condition.nc')

    def run(self):
        """
        Run this step
        """
        ds = open_dataset('mesh.nc')
        ds_state = open_dataset('state.nc')
        for name in ds_state.data_vars:
            ds[name] = ds_state[name]
        # the time the adjustment ended says nothing about when an E3SM run
        # using it should start
        if 'xtime' in ds:
            ds = ds.drop_vars('xtime')
        write_netcdf(ds, 'ocean_initial_condition.nc')
