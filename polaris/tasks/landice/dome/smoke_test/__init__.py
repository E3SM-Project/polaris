from polaris import Task
from polaris.tasks.landice.dome.forward import Forward
from polaris.tasks.landice.dome.viz import Viz


class SmokeTest(Task):
    """
    A dome task that runs MALI and plots the results

    Attributes
    ----------
    velocity_solver : {'sia', 'FO'}
        MALI's velocity solver
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
        super().__init__(component=component, name='smoke_test', indir=indir)
        self.velocity_solver = velocity_solver

        self.add_step(init, symlink='init')

        forward = Forward(
            component=component,
            init=init,
            velocity_solver=velocity_solver,
            indir=self.subdir,
        )
        if velocity_solver == 'sia':
            # the shallow-ice solver is cheap, so the dome can evolve further
            forward.add_model_config_options(
                options={'config_run_duration': '0200-00-00_00:00:00'}
            )
        self.add_step(forward)

        self.add_step(Viz(component=component, init=init, indir=self.subdir))
