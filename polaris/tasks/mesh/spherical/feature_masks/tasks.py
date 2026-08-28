from polaris.tasks.mesh.spherical.feature_masks.task import FeatureMasksTask


def add_feature_mask_tasks(component):
    """
    Add configurable feature-mask tasks to the mesh component.

    Parameters
    ----------
    component : polaris.Component
        The mesh component that the tasks will be added to
    """
    component.add_task(FeatureMasksTask(component=component))
