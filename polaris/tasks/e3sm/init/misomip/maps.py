import os

from polaris.e3sm.init.glc_ocean_maps import GlcOceanMapStep
from polaris.tasks.e3sm.init.misomip.names import get_grid_names

#: The maps between the ocean and MALI that E3SM's coupler reads, with the
#: source and destination grids of each.  The suffix of each name is the one
#: E3SM's map files carry.  The conservative maps carry fluxes, and the
#: smoothed map carries MALI's geometry to the ocean.
MAPS = {
    'landice_to_ocean_aave': ('landice', 'ocean'),
    'landice_to_ocean_smoothed': ('landice', 'ocean'),
    'ocean_to_landice_aave': ('ocean', 'landice'),
}

#: The map of MALI's geometry to the ocean, whose ocean cells are inflated
#: so that the map smooths the geometry
SMOOTHED_MAP = 'landice_to_ocean_smoothed'


class MapStep(GlcOceanMapStep):
    """
    A step for making a map between the ocean and MALI
    """

    def __init__(
        self, component, subdir, map_name, mesh_steps, expand_distance
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        map_name : str
            One of the maps in :py:data:`MAPS`

        mesh_steps : dict of str to polaris.Step
            The steps that write the ``ocean`` and ``landice`` meshes and
            SCRIP files

        expand_distance : float
            The distance in m by which :py:data:`SMOOTHED_MAP` inflates each
            ocean cell
        """
        src_grid, _ = MAPS[map_name]
        smoothed = map_name == SMOOTHED_MAP
        super().__init__(
            component=component,
            name=f'map_{map_name}',
            subdir=subdir,
            to_ocean=src_grid == 'landice',
            smoothed=smoothed,
            expand_distance=expand_distance if smoothed else None,
        )
        self.add_input_file(
            filename='glc_scrip.nc',
            work_dir_target=os.path.join(
                mesh_steps['landice'].path, 'landice_scrip.nc'
            ),
        )
        if smoothed:
            self.add_input_file(
                filename='ocn_mesh.nc',
                work_dir_target=os.path.join(
                    mesh_steps['ocean'].path, 'ocean_mesh.nc'
                ),
            )
        else:
            self.add_input_file(
                filename='ocn_scrip.nc',
                work_dir_target=os.path.join(
                    mesh_steps['ocean'].path, 'ocean_scrip.nc'
                ),
            )

    def runtime_setup(self):
        """
        Set the names of the grids, then the grids
        """
        grids = get_grid_names(self.config)
        self.glc_mesh_name = grids['landice']
        self.ocn_mesh_name = grids['ocean']
        super().runtime_setup()
