import os

from polaris import Task
from polaris.tasks.ocean.mesh_review.viz_mesh_review import (
    MeshReviewStep as MeshReviewStep,
)


def add_mesh_review_tasks(component):
    """
    Add a task for reviewing an existing mesh

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the task belongs to
    """
    component.add_task(MeshReviewTask(component=component))


class MeshReviewTask(Task):
    """
    A task for reviewing an existing mesh, whose files are given in the
    ``mesh_review`` config section
    """

    def __init__(self, component):
        """
        Create the task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to
        """
        subdir = 'mesh_review'
        super().__init__(
            component=component, name='mesh_review', subdir=subdir
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.mesh_review', 'mesh_review.cfg'
        )
        self.add_step(
            MeshReviewStep(
                component=component,
                subdir=os.path.join(subdir, 'viz_mesh_review'),
            )
        )
