import os

from polaris.config import PolarisConfigParser as PolarisConfigParser
from polaris.tasks.ocean.overflow.init import Init
from polaris.tasks.ocean.overflow.pstar_init import PStarInit
from polaris.tasks.ocean.overflow.rpe import Rpe
from polaris.tasks.ocean.overflow.smoke_test import SmokeTest


def add_overflow_tasks(component):
    """
    Add tasks following the overflow test case of Petersen et al. (2015)
    doi:10.1016/j.ocemod.2014.12.004

    Variants combine the equation of state (linear or nonlinear) with the
    vertical coordinate used for the initial condition (z-star or p-star).

    component : polaris.ocean.Ocean
        the ocean component that the task will be added to
    """
    for eos_type, coord_type in [
        ('linear', 'zstar'),
        ('linear', 'pstar'),
    ]:
        _add_overflow_variant_tasks(component, eos_type, coord_type)


def _add_overflow_variant_tasks(component, eos_type, coord_type):
    """
    Add the overflow tasks (smoke tests and RPE) for one combination of
    equation of state (``'linear'`` or ``'nonlinear'``) and vertical
    coordinate for the initial condition (``'zstar'`` or ``'pstar'``).
    """
    taskdir = f'planar/overflow/{eos_type}/{coord_type}'
    config_filename = 'overflow.cfg'
    config = PolarisConfigParser(
        filepath=os.path.join(component.name, taskdir, config_filename)
    )
    if eos_type == 'linear':
        eos_cfg = 'linear.cfg'
    else:
        eos_cfg = 'teos10.cfg'
    config.add_from_package('polaris.ocean.eos', eos_cfg)
    config.add_from_package('polaris.tasks.ocean.overflow', config_filename)

    init_step: Init | PStarInit
    if coord_type == 'pstar':
        config.add_from_package(
            'polaris.tasks.ocean.overflow', 'overflow_pstar.cfg'
        )
        init_step = PStarInit(component=component, name='init', indir=taskdir)
    else:
        init_step = Init(component=component, name='init', indir=taskdir)
    init_step.set_shared_config(config, link=config_filename)

    for horiz_adv_order in [2, 3, 4]:
        smoke_test = SmokeTest(
            component=component,
            indir=taskdir,
            init=init_step,
            horiz_adv_order=horiz_adv_order,
        )
        smoke_test.set_shared_config(config, link=config_filename)
        component.add_task(smoke_test)

        smoke_test = SmokeTest(
            component=component,
            indir=taskdir,
            init=init_step,
            horiz_adv_order=horiz_adv_order,
            use_mom_del4=True,
        )
        smoke_test.set_shared_config(config, link=config_filename)
        component.add_task(smoke_test)

    component.add_task(
        Rpe(
            component=component,
            indir=taskdir,
            init=init_step,
            config=config,
        )
    )
