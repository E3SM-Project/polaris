from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.realistic_global.analysis_test.forward import Forward


class RealisticGlobalAnalysisTest(Task):
    """
    A one-year Omega run on a realistic global mesh that writes what the
    ocean analysis reads: monthly means of the fields it plots, daily global
    statistics and the monthly overturning streamfunction, along with monthly
    snapshots to compare the means against.

    The run reuses the ``realistic_global`` forward step and its cached
    initial condition.  A year is the shortest run that exercises the whole
    analysis chain, since the climatology needs whole years.

    Attributes
    ----------
    mesh_name : str
        The name of the mesh, e.g. ``'QU.240km'``
    """

    def __init__(self, component, mesh_name):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        mesh_name : str
            The name of the mesh, e.g. ``'QU.240km'``
        """
        base = f'spherical/realistic_global/{mesh_name}/analysis_test'
        super().__init__(
            component=component,
            name='realistic_global_analysis_test',
            subdir=f'{base}/task',
        )
        self.mesh_name = mesh_name

        config_filename = 'realistic_global_analysis_test.cfg'
        config = PolarisConfigParser(
            filepath=f'{component.name}/{base}/{config_filename}'
        )
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global', 'realistic_global.cfg'
        )
        config.add_from_package(
            'polaris.tasks.ocean.realistic_global.analysis_test',
            config_filename,
        )
        self.set_shared_config(config, link=config_filename)

        forward_step = Forward(
            component=component,
            subdir=f'{base}/forward',
            mesh_name=mesh_name,
        )
        forward_step.set_shared_config(config, link=config_filename)
        self.add_step(forward_step)
