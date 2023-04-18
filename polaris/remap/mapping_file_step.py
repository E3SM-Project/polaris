import os.path

import pyproj
import xarray as xr
from pyremap import (
    LatLon2DGridDescriptor,
    LatLonGridDescriptor,
    MpasEdgeMeshDescriptor,
    MpasMeshDescriptor,
    PointCollectionDescriptor,
    ProjectionGridDescriptor,
    Remapper,
    get_lat_lon_descriptor,
)

from polaris import Step


class MappingFileStep(Step):
    """
    A step for creating a mapping file between grids

    Attributes
    ----------
    src_grid_info : dict
        Information about the source grid

    dst_grid_info : dict
        Information about the destination grid

    method : {'bilinear', 'neareststod', 'conserve'}
        The method of interpolation used

    map_filename : str or None
        The name of the output mapping file
    """

    def __init__(self, test_case, name, subdir=None, ntasks=None,
                 min_tasks=None, map_filename=None, method='bilinear'):
        """
        Create a new step

        Parameters
        ----------
        test_case : compass.TestCase
            The test case this step belongs to

        name : str
            the name of the step

        subdir : str, optional
            the subdirectory for the step.  The default is ``name``

        ntasks : int, optional
            the target number of MPI tasks the step would ideally use

        min_tasks : int, optional
            the number of MPI tasks the step requires

        map_filename : str, optional
            The name of the output mapping file,
            ``map_{source_type}_{dest_type}_{method}.nc`` by default

        method : {'bilinear', 'neareststod', 'conserve'}, optional
            The method of interpolation used
        """
        super().__init__(test_case, name=name, subdir=subdir,
                         ntasks=ntasks, min_tasks=min_tasks)
        self.src_grid_info = dict()
        self.dst_grid_info = dict()
        self.map_filename = map_filename
        self.method = method

    def src_from_mpas(self, filename, mesh_name, mesh_type='cell'):
        """
        Set the source grid from an MPAS mesh file

        Parameters
        ----------
        filename : str
            A file containing the MPAS mesh

        mesh_name : str
            The name of the MPAS mesh

        mesh_type : {'cell', 'edge', 'vertex'}, optional
            Which type of MPAS mesh
        """
        src = dict()
        src['type'] = 'mpas'
        src['filename'] = filename
        src['name'] = mesh_name
        src['mpas_mesh_type'] = mesh_type
        self.src_grid_info = src

    def dst_from_mpas(self, filename, mesh_name, mesh_type='cell'):
        """
        Set the destination grid from an MPAS mesh file

        Parameters
        ----------
        filename : str
            A file containing the MPAS mesh

        mesh_name : str
            The name of the MPAS mesh

        mesh_type : {'cell', 'edge', 'vertex'}, optional
            Which type of MPAS mesh
        """
        dst = dict()
        dst['type'] = 'mpas'
        dst['filename'] = filename
        dst['name'] = mesh_name
        dst['mpas_mesh_type'] = mesh_type
        self.dst_grid_info = dst

    def src_from_lon_lat(self, filename, mesh_name=None, lon_var='lon',
                         lat_var='lat'):
        """
        Set the source grid from a file with a longitude-latitude grid.  The
        latitude and longitude variables can be 1D or 2D.

        Parameters
        ----------
        filename : str
            A file containing the latitude-longitude grid

        mesh_name : str, optional
            The name of the lon-lat grid (defaults to resolution and units,
            something like "0.5x0.5degree")

        lon_var : str, optional
            The name of the longitude coordinate in the file

        lat_var : str, optional
            The name of the latitude coordinate in the file
        """
        src = dict()
        src['type'] = 'lon-lat'
        src['filename'] = filename
        src['lon'] = lon_var
        src['lat'] = lat_var
        if mesh_name is not None:
            src['name'] = mesh_name
        self.src_grid_info = src

    def dst_from_lon_lat(self, filename, mesh_name=None, lon_var='lon',
                         lat_var='lat'):
        """
        Set the destination grid from a file with a longitude-latitude grid.
        The latitude and longitude variables can be 1D or 2D.

        Parameters
        ----------
        filename : str
            A file containing the latitude-longitude grid

        mesh_name : str, optional
            The name of the lon-lat grid (defaults to resolution and units,
            something like "0.5x0.5degree")

        lon_var : str, optional
            The name of the longitude coordinate in the file

        lat_var : str, optional
            The name of the latitude coordinate in the file
        """
        dst = dict()
        dst['type'] = 'lon-lat'
        dst['filename'] = filename
        dst['lon'] = lon_var
        dst['lat'] = lat_var
        if mesh_name is not None:
            dst['name'] = mesh_name
        self.dst_grid_info = dst

    def dst_global_lon_lat(self, dlon, dlat, mesh_name=None):
        """
        Set the destination grid from a file with a longitude-latitude grid.
        The latitude and longitude variables can be 1D or 2D.

        Parameters
        ----------
        dlon : float
            The longitude resolution in degrees

        dlat : float
            The latitude resolution in degrees

        mesh_name : str, optional
            The name of the lon-lat grid (defaults to resolution and units,
            something like "0.5x0.5degree")
        """

        dst = dict()
        dst['type'] = 'lon-lat'
        dst['dlon'] = dlon
        dst['dlat'] = dlat
        if mesh_name is not None:
            dst['name'] = mesh_name
        self.dst_grid_info = dst

    def src_from_proj(self, filename, mesh_name, x_var='x', y_var='y',
                      proj_attr=None, proj_str=None):
        """
        Set the source grid from a file with a projection grid.

        Parameters
        ----------
        filename : str
            A file containing the projection grid

        mesh_name : str
            The name of the projection grid

        x_var : str, optional
            The name of the x coordinate in the file

        y_var : str, optional
            The name of the y coordinate in the file

        proj_attr : str, optional
            The name of a global attribute in the file containing the proj
            string for the projection

        proj_str : str, optional
            A proj string defining the projection, ignored if ``proj_attr``
            is provided
        """
        src = dict()
        src['type'] = 'proj'
        src['filename'] = filename
        src['name'] = mesh_name
        src['x'] = x_var
        src['y'] = y_var
        if proj_attr is not None:
            src['proj_attr'] = proj_attr
        elif proj_str is not None:
            src['proj_str'] = proj_str
        else:
            raise ValueError('Must provide one of "proj_attr" or "proj_str".')
        self.src_grid_info = src

    def dst_from_proj(self, filename, mesh_name, x_var='x', y_var='y',
                      proj_attr=None, proj_str=None):
        """
        Set the destination grid from a file with a projection grid.

        Parameters
        ----------
        filename : str
            A file containing the projection grid

        mesh_name : str
            The name of the projection grid

        x_var : str, optional
            The name of the x coordinate in the file

        y_var : str, optional
            The name of the y coordinate in the file

        proj_attr : str, optional
            The name of a global attribute in the file containing the proj
            string for the projection

        proj_str : str, optional
            A proj string defining the projection, ignored if ``proj_attr``
            is provided
        """
        dst = dict()
        dst['type'] = 'proj'
        dst['filename'] = filename
        dst['name'] = mesh_name
        dst['x'] = x_var
        dst['y'] = y_var
        if proj_attr is not None:
            dst['proj_attr'] = proj_attr
        elif proj_str is not None:
            dst['proj_str'] = proj_str
        else:
            raise ValueError('Must provide one of "proj_attr" or "proj_str".')
        self.dst_grid_info = dst

    def dst_from_points(self, filename, mesh_name, lon_var='lon',
                        lat_var='lat'):
        """
        Set the destination grid from a file with a collection of points.

        Parameters
        ----------
        filename : str
            A file containing the latitude-longitude grid

        mesh_name : str
            The name of the point collection

        lon_var : str, optional
            The name of the longitude coordinate in the file

        lat_var : str, optional
            The name of the latitude coordinate in the file
        """
        dst = dict()
        dst['type'] = 'points'
        dst['filename'] = filename
        dst['name'] = mesh_name
        dst['lon'] = lon_var
        dst['lat'] = lat_var
        self.dst_grid_info = dst

    def get_remapper(self):
        """
        Get the remapper for this step.  After the step has been run, it can
        be used to remap data between the source and destination grids by
        calling its ``remap_file()`` or ``remap()`` methods.

        Returns
        -------
        remapper : pyremap.Remapper
            The remapper between the source and destination grids
        """
        src = self.src_grid_info
        dst = self.dst_grid_info

        if 'type' not in src:
            raise ValueError('None of the "src_from_*()" methods were called')

        if 'type' not in dst:
            raise ValueError('None of the "dst_from_*()" methods were called')

        # to absolute paths for when the remapper is used in another step
        for info in [src, dst]:
            if 'filename' in info:
                info['filename'] = os.path.abspath(os.path.join(
                    self.work_dir, info['filename']))

        in_descriptor = _get_descriptor(src)
        out_descriptor = _get_descriptor(dst)

        if self.map_filename is None:
            self.map_filename = \
                f'map_{in_descriptor.meshName}_to_{out_descriptor.meshName}' \
                f'_{self.method}.nc'

        self.map_filename = os.path.abspath(os.path.join(
            self.work_dir, self.map_filename))

        remapper = Remapper(in_descriptor, out_descriptor, self.map_filename)
        return remapper

    def run(self):
        """
        Run this step of the test case
        """
        config = self.config
        logger = self.logger
        method = self.method

        parallel_executable = config.get('parallel', 'parallel_executable')

        remapper = self.get_remapper()

        try:
            os.remove(remapper.mappingFileName)
        except FileNotFoundError:
            pass
        remapper.build_mapping_file(method=method, mpiTasks=self.ntasks,
                                    tempdir='.', logger=logger,
                                    esmf_parallel_exec=parallel_executable)


def _get_descriptor(info):
    """ Get a mesh descriptor from the mesh info """
    grid_type = info['type']
    if grid_type == 'mpas':
        descriptor = _get_mpas_descriptor(info)
    elif grid_type == 'lon-lat':
        descriptor = _get_lon_lat_descriptor(info)
    elif grid_type == 'proj':
        descriptor = _get_proj_descriptor(info)
    elif grid_type == 'points':
        descriptor = _get_points_descriptor(info)
    else:
        raise ValueError(f'Unexpected grid type {grid_type}')
    return descriptor


def _get_mpas_descriptor(info):
    """ Get an MpasMeshDescriptor from the given info """
    mesh_type = info['mpas_mesh_type']
    filename = info['filename']
    mesh_name = info['name']

    if mesh_type == 'cell':
        descriptor = MpasMeshDescriptor(fileName=filename, meshName=mesh_name,
                                        vertices=False)
    elif mesh_type == 'vertex':
        descriptor = MpasMeshDescriptor(fileName=filename, meshName=mesh_name,
                                        vertices=True)
    elif mesh_type == 'edge':
        descriptor = MpasEdgeMeshDescriptor(fileName=filename,
                                            meshName=mesh_name)
    else:
        raise ValueError(f'Unexpected MPAS mesh type {mesh_type}')

    return descriptor


def _get_lon_lat_descriptor(info):
    """ Get a lon-lat descriptor from the given info """

    if 'dlat' in info and 'dlon' in info:
        descriptor = get_lat_lon_descriptor(dLon=info['dlon'],
                                            dLat=info['dlat'])
    else:
        filename = info['filename']
        lon = info['lon_var']
        lat = info['lat_var']
        with xr.open_dataset(filename) as ds:
            lon_lat_1d = len(ds[lon].dims) == 1 and len(ds[lat].dims) == 1
            lon_lat_2d = len(ds[lon].dims) == 2 and len(ds[lat].dims) == 2
            if not lon_lat_1d and not lon_lat_2d:
                raise ValueError(f'longitude and latitude coordinates {lon} '
                                 f'and {lat} have unexpected sizes '
                                 f'{len(ds[lon].dims)} and '
                                 f'{len(ds[lat].dims)}.')

        if lon_lat_1d:
            descriptor = LatLonGridDescriptor.read(fileName=filename,
                                                   lonVarName=lon,
                                                   latVarName=lat)
        else:
            descriptor = LatLon2DGridDescriptor.read(fileName=filename,
                                                     lonVarName=lon,
                                                     latVarName=lat)

    if 'name' in info:
        descriptor.meshName = info['name']

    return descriptor


def _get_proj_descriptor(info):
    """ Get a ProjectionGridDescriptor from the given info """
    filename = info['filename']
    grid_name = info['names']
    x = info['x_var']
    y = info['y_var']
    if 'proj_attr' in info:
        with xr.open_dataset(filename) as ds:
            proj_str = ds.attrs[info['proj_attr']]
    else:
        proj_str = info['proj_str']

    proj = pyproj.Proj(proj_str)

    descriptor = ProjectionGridDescriptor.read(projection=proj,
                                               fileName=filename,
                                               meshName=grid_name,
                                               xVarName=x,
                                               yVarName=y)

    return descriptor


def _get_points_descriptor(info):
    """ Get a PointCollectionDescriptor from the given info """
    filename = info['filename']
    collection_name = info['names']
    lon_var = info['lon_var']
    lat_var = info['lat_var']
    with xr.open_dataset(filename) as ds:
        lon = ds[lon_var].value
        lat = ds[lat_var].values
        unit_attr = lon.attrs['units'].lower()
        if 'deg' in unit_attr:
            units = 'degrees'
        elif 'rad' in unit_attr:
            units = 'radians'
        else:
            raise ValueError(f'Unexpected longitude unit unit {unit_attr}')

    descriptor = PointCollectionDescriptor(lons=lon, lats=lat,
                                           collectionName=collection_name,
                                           units=units)

    return descriptor
