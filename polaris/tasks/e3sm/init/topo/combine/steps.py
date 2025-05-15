from polaris.tasks.e3sm.init.topo.combine.step import CombineStep
from polaris.tasks.e3sm.init.topo.combine.viz import VizCombinedStep


def get_combine_topo_steps(
    component, cached=True, include_viz=False, low_res=False
):
    """
    Get the shared combine topo step for the given component, adding it if
    it doesn't exist

    Parameters
    ----------
    component : polaris.Component
        The component that the step will be added to

    cached : bool, optional
        Whether to use cached data for the step or not

    include_viz : bool, optional
        Whether to include the visualization step or not
        Default is False, ignored if ``cached == True``.

    low_res : bool, optional
        Whether to use low resolution config options

    Returns
    -------
    steps : list of polaris.Step
        The combine topo step and optional visualization step
    """
    steps = []
    subdir = CombineStep.get_subdir(low_res=low_res)
    if subdir in component.steps:
        combine_step = component.steps[subdir]
    else:
        combine_step = CombineStep(component=component, low_res=low_res)
        combine_step.cached = cached
        component.add_step(combine_step)
    steps.append(combine_step)

    if not cached and include_viz:
        viz_step = VizCombinedStep(
            component=component, combine_step=combine_step
        )
        component.add_step(viz_step)
        steps.append(viz_step)

    return steps
