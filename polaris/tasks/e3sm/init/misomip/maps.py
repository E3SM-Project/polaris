import os

from polaris.remap import MappingFileStep
from polaris.tasks.e3sm.init.misomip.names import get_grid_names

#: The maps between the ocean and MALI that E3SM's coupler reads, with the
#: source and destination grids and the method of each.  The suffix of each
#: name is E3SM's for the method.
MAPS = {
    'landice_to_ocean_aave': ('landice', 'ocean', 'conserve'),
    'ocean_to_landice_aave': ('ocean', 'landice', 'conserve'),
}


class MapStep(MappingFileStep):
    """
    A step for making a map between the ocean and MALI from their SCRIP
    files

    Attributes
    ----------
    src_grid : {'ocean', 'landice'}
        The source grid

    dst_grid : {'ocean', 'landice'}
        The destination grid
    """

    def __init__(self, component, subdir, map_name, mesh_steps):
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
            The steps that write the ``ocean`` and ``landice`` SCRIP files
        """
        src_grid, dst_grid, method = MAPS[map_name]
        super().__init__(
            component=component,
            name=f'map_{map_name}',
            subdir=subdir,
            ntasks=8,
            min_tasks=1,
            map_filename='map.nc',
            method=method,
        )
        self.src_grid = src_grid
        self.dst_grid = dst_grid
        for prefix, grid in [('src', src_grid), ('dst', dst_grid)]:
            self.add_input_file(
                filename=f'{prefix}_scrip.nc',
                work_dir_target=os.path.join(
                    mesh_steps[grid].path, f'{grid}_scrip.nc'
                ),
            )
        self.add_output_file(filename='map.nc')

    def runtime_setup(self):
        """
        Set the source and destination grids from their SCRIP files
        """
        grids = get_grid_names(self.config)
        self.src_from_scrip(
            filename='src_scrip.nc', mesh_name=grids[self.src_grid]
        )
        self.dst_from_scrip(
            filename='dst_scrip.nc', mesh_name=grids[self.dst_grid]
        )
        super().runtime_setup()
