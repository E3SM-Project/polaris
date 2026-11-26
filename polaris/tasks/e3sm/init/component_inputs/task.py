import os

from polaris import Task
from polaris.e3sm.init.inputdata import set_creation_date
from polaris.tasks.e3sm.init.component_inputs.models import check_ocean_model
from polaris.tasks.e3sm.init.component_inputs.steps import (
    CONFIG_FILENAME,
    component_inputs_subdir,
    get_component_inputs_config,
    get_component_inputs_steps,
)


class ComponentInputsTask(Task):
    """
    A task for staging the E3SM component input files for one mesh.

    Per mesh, there is a task for the sea-ice products, and a task for the
    ocean products and one for both for each ocean model.  They share most of
    their steps, which is why the tasks live under ``component_inputs/tasks/``
    -- a task subdirectory could otherwise collide with a step subdirectory of
    the same name.

    A task for an ocean model is set up with that model, like an E3SM
    configuration, and keeps its task directory apart from the other model's,
    so both can be set up in one work directory.

    Attributes
    ----------
    mesh_name : str
        The name of the base mesh.

    target : {'ocean', 'seaice', 'all'}
        Which products this task stages.

    model : {'mpas-ocean', 'omega'} or None
        The ocean model whose products this task stages, or ``None`` for the
        sea-ice products alone.
    """

    def __init__(self, component, mesh_name, target, model=None):
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

        model : {'mpas-ocean', 'omega'}, optional
            The ocean model whose products to stage, for the ``ocean`` and
            ``all`` targets.
        """
        base_subdir = component_inputs_subdir(mesh_name)
        if model is None:
            name = f'{mesh_name}_component_inputs_{target}'
            subdir = os.path.join(base_subdir, 'tasks', target)
        else:
            name = f'{mesh_name}_component_inputs_{model}_{target}'
            subdir = os.path.join(base_subdir, 'tasks', model, target)
        super().__init__(component=component, name=name, subdir=subdir)
        self.mesh_name = mesh_name
        self.target = target
        self.model = model

        steps, config = get_component_inputs_steps(
            mesh_name=mesh_name, target=target, model=model
        )
        self.set_shared_config(config, link=CONFIG_FILENAME)

        # the factory built only what this target needs, so everything it
        # returned belongs here
        for symlink, step in steps.items():
            self.add_step(step, symlink=symlink)

    def configure(self):
        """
        Check the ocean model and fill in the creation dates, so they land in
        the work directory's config files.

        Doing this at setup rather than at run time is what keeps a re-run
        from renaming every staged file to today's date.  The mesh's date is
        recorded in the config file of the model-neutral steps, which every
        task's setup writes, so a task for the other model picks it up rather
        than stamping the shared products with a second date.
        """
        super().configure()
        neutral_config = get_component_inputs_config(self.mesh_name)
        mesh_date = set_creation_date(
            self.config,
            'component_inputs',
            recorded_in=neutral_config.filepath,
        )
        if self.model is None:
            return

        check_ocean_model(self.model)
        neutral_config.set('component_inputs', 'creation_date', mesh_date)
        set_creation_date(
            self.config, 'component_inputs', option='ocean_creation_date'
        )
