from polaris import Task
from polaris.tasks.landice.dome.forward import Forward
from polaris.tasks.landice.dome.validate import (
    EXACT_NORMS,
    FO_NORMS,
    Validate,
)


class Restart(Task):
    """
    A dome task that makes sure MALI gives the same results with one 2-year
    run and with a 1-year run that restarts from the first year of it
    """

    def __init__(self, component, velocity_solver, indir, init):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.landice.Landice
            The landice component that this task belongs to

        velocity_solver : {'sia', 'FO'}
            MALI's velocity solver

        indir : str
            The directory the task is in, to which ``name`` will be appended

        init : polaris.tasks.landice.dome.init.Init
            The shared step that makes the mesh and initial condition
        """
        super().__init__(component=component, name='restart', indir=indir)

        self.add_step(init, symlink='init')

        package = 'polaris.tasks.landice.dome.restart'

        full = Forward(
            component=component,
            init=init,
            velocity_solver=velocity_solver,
            name='full_run',
            indir=self.subdir,
        )
        full.add_model_config_options(
            options={
                'config_start_time': '0000-01-01_00:00:00',
                'config_run_duration': '0002-00-00_00:00:00',
                'config_do_restart': False,
                'config_write_output_on_startup': False,
            }
        )
        full.add_streams_file(package, 'streams.restart')
        full.add_output_file(filename='rst.0001.nc')
        self.add_step(full)

        restart = Forward(
            component=component,
            init=init,
            velocity_solver=velocity_solver,
            name='restart_run',
            indir=self.subdir,
        )
        restart.add_model_config_options(
            options={
                'config_start_time': '0001-01-01_00:00:00',
                'config_run_duration': '0001-00-00_00:00:00',
                'config_do_restart': True,
                'config_write_output_on_startup': False,
            }
        )
        restart.add_streams_file(package, 'streams.restart')
        restart.add_input_file(
            filename='rst.0001.nc', work_dir_target=f'{full.path}/rst.0001.nc'
        )
        restart.add_dependency(full, full.name)
        self.add_step(restart)

        self.add_step(
            Validate(
                component=component,
                step_subdirs=['full_run', 'restart_run'],
                indir=self.subdir,
                norms=EXACT_NORMS,
                # the first-order solver gives slightly different results
                # from one run to the next on GPUs
                gpu_norms=FO_NORMS if velocity_solver == 'FO' else None,
            )
        )
