import os

from polaris import Task
from polaris.tasks.e3sm.init.component_inputs.names import set_creation_date
from polaris.tasks.e3sm.init.component_inputs.steps import (
    CONFIG_FILENAME,
    component_inputs_subdir,
    get_component_inputs_steps,
)


class ComponentInputsTask(Task):
    """
    A task for staging the E3SM component input files for one mesh.

    Three of these exist per mesh, for the ocean products, the sea-ice
    products and both.  They share most of their steps, which is why the tasks
    live under ``component_inputs/tasks/`` -- a task subdirectory could
    otherwise collide with a step subdirectory of the same name.

    Attributes
    ----------
    mesh_name : str
        The name of the base mesh.

    target : {'ocean', 'seaice', 'all'}
        Which products this task stages.
    """

    def __init__(self, component, mesh_name, target):
        """
        Create the task.

        Parameters
        ----------
        component : polaris.Component
            The component the task belongs to.

        mesh_name : str
            The name of the base mesh.

        target : {'ocean', 'seaice', 'all'}
            Which products to stage.
        """
        base_subdir = component_inputs_subdir(mesh_name)
        super().__init__(
            component=component,
            name=f'{mesh_name}_component_inputs_{target}',
            subdir=os.path.join(base_subdir, 'tasks', target),
        )
        self.mesh_name = mesh_name
        self.target = target

        steps, config = get_component_inputs_steps(
            mesh_name=mesh_name, target=target
        )
        self.set_shared_config(config, link=CONFIG_FILENAME)

        # the factory built only what this target needs, so everything it
        # returned belongs here
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)

    def configure(self):
        """
        Fill in the creation date so it lands in the work directory's config.

        Doing this at setup rather than at run time is what keeps a re-run
        from renaming every staged file to today's date.
        """
        super().configure()
        set_creation_date(self.config)
