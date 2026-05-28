from polaris.tasks.ocean.feature_masks.task import OceanFeatureMasksTask


def add_feature_mask_tasks(component):
    """
    Add configurable ocean feature-mask tasks to the ocean component.

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component that the tasks will be added to
    """
    component.add_task(OceanFeatureMasksTask(component=component))
