from polaris.ocean.model import OceanModelStep

PHYSICS = ('e3sm', 'com')


def get_physics_replacements(config, resolution):
    """
    Get the template replacements for ``physics.yaml``: the horizontal
    viscosities, scaled with resolution as in E3SM's FRISwISC meshes

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options of the task

    resolution : float
        The horizontal resolution (km) of the mesh

    Returns
    -------
    replacements : dict
        The del2 and del4 viscosities
    """
    section = config['isomip_plus']
    mom_del2 = section.getfloat('mom_del2_1km') * resolution
    mom_del4 = section.getfloat('mom_del4_1km') * resolution**3
    return dict(mom_del2=mom_del2, mom_del4=mom_del4)


def add_com_physics_yaml(step: OceanModelStep):
    """
    Add ``com.yaml`` to a model step if its task uses the COM physics, after
    ``physics.yaml``

    Parameters
    ----------
    step : polaris.ocean.model.OceanModelStep
        The model step
    """
    physics = step.config.get('isomip_plus', 'physics')
    if physics not in PHYSICS:
        raise ValueError(
            f'Unexpected ISOMIP+ physics {physics}, expected one of {PHYSICS}'
        )
    if physics == 'com':
        step.add_yaml_file('polaris.tasks.ocean.isomip_plus', 'com.yaml')
