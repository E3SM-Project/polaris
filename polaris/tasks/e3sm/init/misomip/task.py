import os

from polaris import Task
from polaris.e3sm.init.inputdata import set_creation_date
from polaris.tasks.e3sm.init.misomip.names import (
    INPUTS_SECTION,
    get_grid_names,
)
from polaris.tasks.e3sm.init.misomip.steps import (
    CONFIG_FILENAME,
    NOT_RUN_BY_DEFAULT,
    get_misomip_experiment_steps,
)


class MisomipTask(Task):
    """
    A task for making E3SM's inputs for one MISOMIP experiment on a pair of
    meshes

    Attributes
    ----------
    mesh_name : str
        The name of the pair of meshes

    experiment : str
        The experiment
    """

    def __init__(self, component, mesh_name, experiment):
        """
        Create the task

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to

        mesh_name : str
            The name of the pair of meshes

        experiment : str
            The experiment
        """
        super().__init__(
            component=component,
            name=f'{mesh_name}_misomip_{experiment}',
            subdir=os.path.join(mesh_name, 'misomip', experiment),
        )
        self.mesh_name = mesh_name
        self.experiment = experiment

        steps, config = get_misomip_experiment_steps(mesh_name, experiment)
        self.set_shared_config(config, link=CONFIG_FILENAME)
        for symlink, step in steps.items():
            if step.subdir.startswith(f'{self.subdir}/'):
                # the experiment's own steps are in the task's directory
                self.add_step(step)
            else:
                self.add_step(
                    step,
                    symlink=symlink,
                    run_by_default=symlink not in NOT_RUN_BY_DEFAULT,
                )

    def configure(self):
        """
        Check that the grids have E3SM names, so setup fails without them,
        and fill in the creation date so it lands in the work directory's
        config, so a re-run keeps the staged files' names
        """
        super().configure()
        get_grid_names(self.config)
        set_creation_date(self.config, INPUTS_SECTION)
