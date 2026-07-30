import os

from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.seamount.default import Default as Default
from polaris.tasks.ocean.seamount.init import Init as Init


def add_seamount_tasks(component):
    """
    Add tasks following the seamount test case

    Variants combine the equation of state (linear or nonlinear) with the
    vertical coordinate used for the initial condition, ``sigma``
    (terrain-following) or ``zstar``.  Both coordinates are geometric, so
    both are supported by MPAS-Ocean and by Omega, which reads them as
    pseudo-thickness.

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    for eos_type in ['linear', 'nonlinear']:
        for coord_type in ['sigma', 'zstar']:
            _add_seamount_variant_tasks(component, eos_type, coord_type)


def _add_seamount_variant_tasks(component, eos_type, coord_type):
    """
    Add the seamount tasks for one combination of equation of state
    (``'linear'`` or ``'nonlinear'``) and vertical coordinate for the
    initial condition (``'sigma'`` or ``'zstar'``).
    """
    taskdir = f'planar/seamount/{eos_type}/{coord_type}'
    config_filename = 'seamount.cfg'
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, taskdir, config_filename)
    )
    if eos_type == 'linear':
        eos_cfg = 'linear.cfg'
    else:
        eos_cfg = 'teos10.cfg'
    config.add_from_package('polaris.ocean.eos', eos_cfg)
    config.add_from_package('polaris.tasks.ocean.seamount', config_filename)
    if eos_type == 'linear':
        # the linear equation of state needs coefficients that reproduce the
        # Beckmann and Haidvogel profile; the nonlinear trees take everything
        # they need from teos10.cfg
        config.add_from_package(
            'polaris.tasks.ocean.seamount', 'seamount_linear.cfg'
        )
    config.add_from_package(
        'polaris.tasks.ocean.seamount', f'seamount_{coord_type}.cfg'
    )

    init_step = Init(component=component, name='init', indir=taskdir)
    init_step.set_shared_config(config, link=config_filename)

    default = Default(component=component, indir=taskdir, init=init_step)
    default.set_shared_config(config, link=config_filename)
    component.add_task(default)
