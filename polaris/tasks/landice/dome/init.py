import numpy as np
from mpas_tools.io import open_dataset, write_netcdf
from mpas_tools.mesh.conversion import convert, cull
from mpas_tools.planar_hex import make_planar_hex_mesh

from polaris import Step
from polaris.landice.mesh import make_mali_mesh


class Init(Step):
    """
    A step for creating the mesh and initial condition for dome tasks

    Attributes
    ----------
    resolution : float
        The resolution of the mesh in km
    """

    def __init__(self, component, resolution, indir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : float
            The resolution of the mesh in km

        indir : str
            the directory the step is in, to which ``name`` will be appended
        """
        super().__init__(component=component, name='init', indir=indir)
        self.resolution = resolution

        for filename in ['landice_grid.nc', 'graph.info']:
            self.add_output_file(filename=filename)

    def run(self):
        """
        Run this step of the task
        """
        logger = self.logger
        section = self.config['dome']

        ds_mesh = make_planar_hex_mesh(
            nx=section.getint('nx'),
            ny=section.getint('ny'),
            dc=1e3 * self.resolution,
            nonperiodic_x=True,
            nonperiodic_y=True,
        )
        write_netcdf(ds_mesh, 'base_mesh.nc')

        ds_mesh = cull(ds_mesh, logger=logger)
        ds_mesh = convert(ds_mesh, logger=logger)
        write_netcdf(ds_mesh, 'culled_mesh.nc')

        make_mali_mesh(
            in_filename='culled_mesh.nc',
            out_filename='mali_mesh.nc',
            levels=section.getint('levels'),
            logger=logger,
            graph_filename='graph.info',
        )

        ds = open_dataset('mali_mesh.nc').load()
        _add_dome_initial_condition(ds, self.config)
        write_netcdf(ds, 'landice_grid.nc')


def _add_dome_initial_condition(ds, config):
    """
    Add the dome's thickness, a flat bed and zero surface mass balance to a
    MALI mesh
    """
    section = config['dome']
    dome_type = section.get('dome_type')
    put_origin_on_a_cell = section.getboolean('put_origin_on_a_cell')
    shelf = section.getboolean('shelf')

    x_cell = ds.xCell.values
    y_cell = ds.yCell.values

    # find the center of the domain and the distance of each cell from it
    x0 = x_cell.min() + 0.5 * (x_cell.max() - x_cell.min())
    y0 = y_cell.min() + 0.5 * (y_cell.max() - y_cell.min())
    r = np.sqrt((x_cell - x0) ** 2 + (y_cell - y0) ** 2)

    if put_origin_on_a_cell:
        # center the dome in the center of the cell that is closest to the
        # center of the domain
        center_cell = np.abs(r).argmin()
        x_shift = -x_cell[center_cell]
        y_shift = -y_cell[center_cell]
        for prefix in ['Cell', 'Edge', 'Vertex']:
            ds[f'x{prefix}'][:] = ds[f'x{prefix}'].values + x_shift
            ds[f'y{prefix}'][:] = ds[f'y{prefix}'].values + y_shift
        x_cell = ds.xCell.values
        y_cell = ds.yCell.values
        r = np.sqrt(x_cell**2 + y_cell**2)

    # the dome's radius and maximum thickness in m
    r0 = 60000.0 * np.sqrt(0.125)
    h0 = 2000.0 * np.sqrt(0.125)

    thickness = np.zeros(ds.sizes['nCells'])
    mask = r < r0
    if dome_type == 'cism':
        thickness[mask] = h0 * np.sqrt(1.0 - (r[mask] / r0) ** 2)
    elif dome_type == 'halfar':
        thickness[mask] = h0 * (1.0 - (r[mask] / r0) ** (4.0 / 3.0)) ** (
            3.0 / 7.0
        )
    else:
        raise ValueError(f'Unexpected dome_type: {dome_type}')
    ds['thickness'][0, :] = thickness

    # a flat bed at sea level
    bed_topography = np.zeros(ds.sizes['nCells'])
    if shelf:
        # a small shelf
        bed_topography[x_cell < -10000.0] = -2000.0
    ds['bedTopography'][0, :] = bed_topography

    n_vert_levels = ds.sizes['nVertLevels']
    ds['layerThicknessFractions'][:] = 1.0 / n_vert_levels

    ds['sfcMassBal'][:] = 0.0
