from polaris import Task
from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.ocean.tasks.overflow.forward import Forward as Forward
from polaris.ocean.tasks.overflow.init import Init as Init
from polaris.ocean.tasks.overflow.viz import Viz as Viz


def add_overflow_tasks(component):
    """
    Add a task TODO

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    basedir = 'planar/overflow'
    config_filename = 'overflow.cfg'
    filepath = f'{basedir}/{config_filename}'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.ocean.tasks.overflow', config_filename)
    component.add_task(Overflow(component=component, config=config))


class Overflow(Task):
    """
    The overflow test case TODO
    """

    def __init__(self, component, config):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.ocean.Ocean
            The ocean component that this task belongs to

        config : polaris.config.PolarisConfigParser
            A shared config parser
        """
        test_name = 'default'
        basedir = 'planar/overflow'
        indir = f'{basedir}/{test_name}'
        name = f'overflow_{test_name}'
        config_filename = 'overflow.cfg'

        super().__init__(component=component, name=name, subdir=indir)
        self.set_shared_config(config, link=config_filename)
        subdir = f'{basedir}/init'
        symlink = 'init'
        if subdir in component.steps:
            init_step = component.steps[subdir]
        else:
            init_step = Init(component=component, name='init', subdir=subdir)
            init_step.set_shared_config(self.config, link=config_filename)
        self.add_step(init_step, symlink=symlink)
        forward_step = Forward(
            component=component, init=init_step, name='forward', indir=indir
        )
        self.add_step(forward_step)
        self.add_step(Viz(component=component, indir=indir))
