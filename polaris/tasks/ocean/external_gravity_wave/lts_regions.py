import math
import os

import netCDF4 as nc
import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf
from mpas_tools.viz.paraview_extractor import extract_vtk
from shapely import distance
from shapely.geometry import Point

from polaris.step import Step

# from shapely.geometry.polygon import Polygon


class LTSRegions(Step):
    """
    A step for adding LTS regions to a global MPAS-Ocean mesh

    Attributes
    ----------
    initial_state_step :
        polaris.ocean.tasks.external_gravity_wave.init.Init
        The initial step containing input files to this step
    """

    def __init__(self, component, init_step, name, subdir):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The test case this step belongs to

        init_step :
            compass.ocean.tests.dam_break.initial_state.InitialState
            The initial state step containing input files to this step

        name : str, optional
            the name of the step

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``
        """
        super().__init__(component, name=name, subdir=subdir)

        for file in ['graph.info', 'initial_state.nc']:
            self.add_output_file(filename=file)

        self.init_step = init_step

    def setup(self):
        """
        Set up the test case in the work directory, including downloading any
        dependencies.
        """
        super().setup()

        init_path = self.init_step.path
        tgt1 = os.path.join(init_path, 'initial_state.nc')
        self.add_input_file(filename='init.nc', work_dir_target=tgt1)

        tgt2 = os.path.join(init_path, 'graph.info')
        self.add_input_file(
            filename='pre_lts_graph.info', work_dir_target=tgt2
        )

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config

        section = config['external_gravity_wave']
        lat_center = section.getfloat('lat_center')
        lon_center = section.getfloat('lon_center')

        use_progress_bar = self.log_filename is None
        label_mesh(
            mesh='init.nc',
            graph_info='pre_lts_graph.info',
            num_interface=2,
            num_interface_adjacent=10,
            lat_center=lat_center,
            lon_center=lon_center,
            fine_region_radius=np.pi / 4,
            logger=self.logger,
            use_progress_bar=use_progress_bar,
        )


def label_mesh(
    mesh,
    graph_info,
    num_interface,  # noqa: C901
    num_interface_adjacent,
    lat_center,
    lon_center,
    fine_region_radius,
    logger,
    use_progress_bar,
):
    # read in mesh data
    ds = xr.open_dataset(mesh)
    n_cells = ds['nCells'].size
    n_edges = ds['nEdges'].size
    area_cell = ds['areaCell'].values
    cells_on_edge = ds['cellsOnEdge'].values
    edges_on_cell = ds['edgesOnCell'].values
    lat_cell = ds['latCell']
    lon_cell = ds['lonCell']

    lts_rgn = label_fine_region(
        n_cells,
        lat_cell,
        lon_cell,
        lat_center,
        lon_center,
        fine_region_radius,
        logger,
    )
    lts_rgn = label_interface_regions(
        lts_rgn,
        n_edges,
        num_interface,
        num_interface_adjacent,
        cells_on_edge,
        edges_on_cell,
        logger,
    )

    # create lts_mesh.nc

    logger.info('Creating lts_mesh...')

    # open mesh nc file to be copied

    ds_msh = xr.open_dataset(mesh)
    ds_ltsmsh = ds_msh.copy(deep=True)
    ltsmsh_name = 'initial_state.nc'
    write_netcdf(ds_ltsmsh, ltsmsh_name)
    mshnc = nc.Dataset(ltsmsh_name, 'a', format='NETCDF4_64BIT_OFFSET')

    try:
        # try to get LTSRegion and assign new value
        lts_rgn_NC = mshnc.variables['LTSRegion']
        lts_rgn_NC[:] = lts_rgn[:]
    except KeyError:
        # create new variable
        ncells_NC = mshnc.dimensions['nCells'].name
        lts_rgns_NC = mshnc.createVariable('LTSRegion', np.int32, (ncells_NC,))

        # set new variable
        lts_rgns_NC[:] = lts_rgn[:]

    mshnc.close()

    extract_vtk(
        ignore_time=True,
        lonlat=0,
        dimension_list=['maxEdges=', 'nVertLevels='],
        variable_list=['allOnCells'],
        filename_pattern=ltsmsh_name,
        out_dir='lts_mesh_vtk',
        use_progress_bar=use_progress_bar,
    )

    # label cells in graph.info

    logger.info('Weighting ' + graph_info + '...')

    fine_cells = 0
    coarse_cells = 0

    newf = ''
    with open(graph_info, 'r') as f:
        lines = f.readlines()
        # this is to have fine, coarse and interface be separate for METIS
        # newf += lines[0].strip() + " 010 3 \n"

        # this is to have fine, and interface be together for METIS
        newf += lines[0].strip() + ' 010 2 \n'
        for icell in range(1, len(lines)):
            if lts_rgn[icell - 1] == 1 or lts_rgn[icell - 1] == 5:  # fine
                # newf+= "0 1 0 " + lines[icell].strip() + "\n"
                newf += '0 1 ' + lines[icell].strip() + '\n'
                fine_cells = fine_cells + 1

            elif lts_rgn[icell - 1] == 2:  # coarse
                # newf+= "1 0 0 " + lines[icell].strip() + "\n"
                newf += '1 0 ' + lines[icell].strip() + '\n'
                coarse_cells = coarse_cells + 1

            else:  # interface 1 and 2
                # newf+= "0 0 1 " + lines[icell].strip() + "\n"
                newf += '0 1 ' + lines[icell].strip() + '\n'
                coarse_cells = coarse_cells + 1

    with open('graph.info', 'w') as f:
        f.write(newf)

    max_area = max(area_cell)
    min_area = min(area_cell)
    max_width = 2 * np.sqrt(max_area / math.pi) / 1000
    min_width = 2 * np.sqrt(min_area / math.pi) / 1000
    area_ratio = max_area / min_area
    width_ratio = max_width / min_width
    number_ratio = coarse_cells / fine_cells

    txt = f'number of fine cells = {fine_cells}\n'
    txt += f'number of coarse cells = {coarse_cells}\n'
    txt += f'ratio of coarse to fine cells = {number_ratio}\n'
    txt += f'ratio of largest to smallest cell area = {area_ratio}\n'
    txt += f'ratio of largest to smallest cell width = {width_ratio}\n'
    txt += f'number of interface layers = {num_interface}\n'

    logger.info(txt)

    with open('lts_mesh_info.txt', 'w') as f:
        f.write(txt)


def label_fine_region(
    n_cells,
    lat_cell,
    lon_cell,  # noqa: C901
    lat_center,
    lon_center,
    fine_region_radius,
    logger,
):
    # start by setting all cells to coarse
    lts_rgn = [2] * n_cells

    # check each cell, if in the fine region, label as fine
    logger.info('Labeling fine cells...')
    center_pt = Point(lat_center, lon_center)
    for icell in range(0, n_cells):
        cell_pt = Point(lat_cell[icell], lon_cell[icell])
        if distance(cell_pt, center_pt) < fine_region_radius:
            lts_rgn[icell] = 1

    return lts_rgn


def label_interface_regions(  # noqa: C901
    lts_rgn,
    n_edges,
    num_interface,
    num_interface_adjacent,
    cells_on_edge,
    edges_on_cell,
    logger,
):
    # first layer of cells with label 5
    logger.info('Labeling interface-adjacent fine cells...')
    changed_cells = [[], []]  # type: ignore [var-annotated]
    for iedge in range(0, n_edges):
        cell1 = cells_on_edge[iedge, 0] - 1
        cell2 = cells_on_edge[iedge, 1] - 1

        if cell1 != -1 and cell2 != -1:
            if lts_rgn[cell1] == 1 and lts_rgn[cell2] == 2:
                lts_rgn[cell1] = 5
                changed_cells[0].append(cell1)

            elif lts_rgn[cell1] == 2 and lts_rgn[cell2] == 1:
                lts_rgn[cell2] = 5
                changed_cells[0].append(cell2)

    border_cells = changed_cells[0]

    # num_interface_adjacent - 1 layers of cells with label 5
    # only looping over cells changed during loop for previous layer
    for i in range(0, num_interface_adjacent - 1):
        changed_cells[(i + 1) % 2] = []

        for icell in changed_cells[i % 2]:
            edges = edges_on_cell[icell]
            for iedge in edges:
                if iedge != 0:
                    cell1 = cells_on_edge[iedge - 1, 0] - 1
                    cell2 = cells_on_edge[iedge - 1, 1] - 1

                    if cell1 != -1 and cell2 != -1:
                        if lts_rgn[cell1] == 5 and lts_rgn[cell2] == 1:
                            lts_rgn[cell2] = 5
                            changed_cells[(i + 1) % 2].append(cell2)

                        elif lts_rgn[cell1] == 1 and lts_rgn[cell2] == 5:
                            lts_rgn[cell1] = 5
                            changed_cells[(i + 1) % 2].append(cell1)

    changed_cells[0] = border_cells

    # num_interface layers of interface region with label 4
    logger.info('Labeling interface cells...')
    for i in range(0, num_interface):
        changed_cells[(i + 1) % 2] = []

        for icell in changed_cells[i % 2]:
            edges = edges_on_cell[icell]
            for iedge in edges:
                if iedge != 0:
                    cell1 = cells_on_edge[iedge - 1, 0] - 1
                    cell2 = cells_on_edge[iedge - 1, 1] - 1

                    if cell1 != -1 and cell2 != -1:
                        # for the first layer, need to check neighbors are
                        # 5 and 2
                        # for further layers, need to check neighbors are
                        # 3 and 2
                        if i == 0:
                            if lts_rgn[cell1] == 5 and lts_rgn[cell2] == 2:
                                lts_rgn[cell2] = 3
                                changed_cells[(i + 1) % 2].append(cell2)

                            elif lts_rgn[cell1] == 2 and lts_rgn[cell2] == 5:
                                lts_rgn[cell1] = 3
                                changed_cells[(i + 1) % 2].append(cell1)

                        else:
                            if lts_rgn[cell1] == 3 and lts_rgn[cell2] == 2:
                                lts_rgn[cell2] = 3
                                changed_cells[(i + 1) % 2].append(cell2)

                            elif lts_rgn[cell1] == 2 and lts_rgn[cell2] == 3:
                                lts_rgn[cell1] = 3
                                changed_cells[(i + 1) % 2].append(cell1)

    changed_cells[0] = changed_cells[num_interface % 2]

    # num_interface layers of interface region with label 3
    for i in range(0, num_interface):
        changed_cells[(i + 1) % 2] = []

        for icell in changed_cells[i % 2]:
            edges = edges_on_cell[icell]
            for iedge in edges:
                if iedge != 0:
                    cell1 = cells_on_edge[iedge - 1, 0] - 1
                    cell2 = cells_on_edge[iedge - 1, 1] - 1

                    if cell1 != -1 and cell2 != -1:
                        # for the first layer, need to check neighbors are
                        # 3 and 2
                        # for further layers, need to check neighbors are
                        # 4 and 2
                        if i == 0:
                            if lts_rgn[cell1] == 3 and lts_rgn[cell2] == 2:
                                lts_rgn[cell2] = 4
                                changed_cells[(i + 1) % 2].append(cell2)

                            elif lts_rgn[cell1] == 2 and lts_rgn[cell2] == 3:
                                lts_rgn[cell1] = 4
                                changed_cells[(i + 1) % 2].append(cell1)
                        else:
                            if lts_rgn[cell1] == 4 and lts_rgn[cell2] == 2:
                                lts_rgn[cell2] = 4
                                changed_cells[(i + 1) % 2].append(cell2)

                            elif lts_rgn[cell1] == 2 and lts_rgn[cell2] == 4:
                                lts_rgn[cell1] = 4
                                changed_cells[(i + 1) % 2].append(cell1)

    return lts_rgn
