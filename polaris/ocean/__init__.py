from polaris import Component
from polaris.ocean.tasks.baroclinic_channel import add_baroclinic_channel_tasks
from polaris.ocean.tasks.cosine_bell import add_cosine_bell_tasks
from polaris.ocean.tasks.geostrophic import add_geostrophic_tasks
from polaris.ocean.tasks.ice_shelf_2d import add_ice_shelf_2d_tasks
from polaris.ocean.tasks.inertial_gravity_wave import (
    add_inertial_gravity_wave_tasks,
)
from polaris.ocean.tasks.internal_wave import add_internal_wave_tasks
from polaris.ocean.tasks.isomip_plus import add_isomip_plus_tasks
from polaris.ocean.tasks.manufactured_solution import (
    add_manufactured_solution_tasks,
)
from polaris.ocean.tasks.single_column import add_single_column_tasks
from polaris.ocean.tasks.sphere_transport import add_sphere_transport_tasks


class Ocean(Component):
    """
    The collection of all test case for the MPAS-Ocean core
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Ocean test cases
        """
        super().__init__(name='ocean')

        # planar: please keep these in alphabetical order
        add_baroclinic_channel_tasks(component=self)
        add_ice_shelf_2d_tasks(component=self)
        add_inertial_gravity_wave_tasks(component=self)
        add_internal_wave_tasks(component=self)
        add_isomip_plus_tasks(component=self, mesh_type='planar')
        add_manufactured_solution_tasks(component=self)

        # single column
        add_single_column_tasks(component=self)

        # spherical: please keep these in alphabetical order
        add_cosine_bell_tasks(component=self)
        add_geostrophic_tasks(component=self)
        add_isomip_plus_tasks(component=self, mesh_type='spherical')
        add_sphere_transport_tasks(component=self)

    def configure(self, config):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            config options to modify
        """
        section = config['ocean']
        model = section.get('model')
        configs = {'mpas-ocean': 'mpas_ocean.cfg',
                   'omega': 'omega.cfg'}
        if model not in configs:
            raise ValueError(f'Unknown ocean model {model} in config options')

        config.add_from_package('polaris.ocean', configs[model])
