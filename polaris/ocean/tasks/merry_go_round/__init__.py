from polaris import Step, Task
from polaris.config import PolarisConfigParser
from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.merry_go_round.default import Default
from polaris.ocean.tasks.merry_go_round.init import Init


def add_merry_go_round_tasks(component):
    resolution = 5
    resdir = resolution_to_subdir(resolution)
    resdir = f'planar/merry_go_round/{resdir}'

    package_path = 'polaris.ocean.tasks.merry_go_round'
    config_filename = 'merry_go_round.cfg'
    config = PolarisConfigParser(filepath=f'{resdir}/{config_filename}')
    config.add_from_package(package_path, config_filename)

    init = Init(component=component, resolution=resolution, indir=resdir)
    init.set_shared_config(config, link=config_filename)

    default = Default(component=component, resolution=resolution,
                      indir=resdir, init=init)
    default.set_shared_config(config, link=config_filename)
    component.add_task(default)


'''
class MerryGoRound(Task):
    """
    A test group for tracer advection test cases "merry-go-round"
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
        pass
'''
