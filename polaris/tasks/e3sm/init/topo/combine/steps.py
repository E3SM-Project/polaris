import os

from polaris.config import PolarisConfigParser
from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.viz import VizCombinedStep


def get_combine_topo_steps(component, include_viz=False, low_res=False):
    """
    Get the shared combine topo step for the given component, adding it if
    it doesn't exist

    Parameters
    ----------
    component : polaris.Component
        The component that the steps will be added to

    include_viz : bool, optional
        Whether to include the visualization step or not
        Default is False.

    low_res : bool, optional
        Whether to use low resolution config options

    Returns
    -------
    steps : list of polaris.Step
        The combine topo step and optional visualization step

    config : polaris.config.PolarisConfigParser
        The shared config options
    """

    subdir = CombineStep.get_subdir(low_res=low_res)

    # add default config options for combining topo -- since these are
    # shared steps, the config options need to be defined separately from any
    # task this may be added to
    config_filename = 'combine_topo.cfg'
    filepath = os.path.join(component.name, subdir, config_filename)
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.e3sm.init.topo.combine', 'combine.cfg'
    )
    if low_res:
        config.add_from_package(
            'polaris.tasks.e3sm.init.topo.combine', 'combine_low_res.cfg'
        )

    steps = []
    if subdir in component.steps:
        combine_step = component.steps[subdir]
    else:
        combine_step = CombineStep(
            component=component, config=config, low_res=low_res
        )
        component.add_step(combine_step)
    steps.append(combine_step)

    if include_viz:
        viz_step = VizCombinedStep(
            component=component, config=config, combine_step=combine_step
        )
        component.add_step(viz_step)
        steps.append(viz_step)

    return steps, config
