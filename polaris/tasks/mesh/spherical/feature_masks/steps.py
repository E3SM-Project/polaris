import os

from geometric_features.aggregation import get_aggregator_by_name

from polaris.config import PolarisConfigParser
from polaris.tasks.mesh.spherical.feature_masks.compute import (
    ComputeFeatureMasksStep,
)


def get_feature_mask_steps(
    mesh_name,
    mask_group,
    mesh_step=None,
    mesh_filename=None,
    component=None,
):
    """
    Get shared feature-mask steps for one mesh and mask group.

    Parameters
    ----------
    mesh_name : str
        The name of the mesh for output filenames and metadata

    mask_group : str
        A group name supported by ``get_aggregator_by_name()``

    mesh_step : polaris.Step, optional
        An upstream step that produces the mesh

    mesh_filename : str, optional
        The mesh filename from ``mesh_step`` or configurable task config

    component : polaris.Component, optional
        The component that owns the shared step. Defaults to ``mesh``.

    Returns
    -------
    steps : dict of str to polaris.Step
        The feature-mask step keyed by suggested symlink

    config : polaris.config.PolarisConfigParser
        The shared feature-mask config
    """
    if component is None:
        from polaris.tasks.mesh import mesh as component

    _, prefix, date = get_aggregator_by_name(mask_group)
    config_filename = 'feature_masks.cfg'
    filepath = os.path.join(
        component.name,
        'spherical',
        'feature_masks',
        mesh_name,
        f'{prefix}{date}',
        config_filename,
    )
    config = _get_feature_masks_config(component=component, filepath=filepath)
    config.set('feature_masks', 'mesh_name', mesh_name)
    config.set('feature_masks', 'mask_group', mask_group)
    if mesh_filename is not None:
        config.set('feature_masks', 'mesh_filename', mesh_filename)

    subdir = os.path.join(
        'spherical',
        'feature_masks',
        mesh_name,
        f'{prefix}{date}',
        'compute',
    )
    step = component.get_or_create_shared_step(
        step_cls=ComputeFeatureMasksStep,
        subdir=subdir,
        config=config,
        config_filename=config_filename,
        mesh_step=mesh_step,
        mesh_filename=mesh_filename,
        mesh_name=mesh_name,
        mask_group=mask_group,
    )
    return {'feature_masks': step}, config


def _get_feature_masks_config(component, filepath):
    if filepath in component.configs:
        return component.configs[filepath]

    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package(
        'polaris.tasks.mesh.spherical.feature_masks',
        'feature_masks.cfg',
    )
    return config
