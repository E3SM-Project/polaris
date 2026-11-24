from dataclasses import dataclass
from typing import Any, List, Optional, Union

import netCDF4
import numpy as np

from polaris.e3sm.init.topo import format_lat_lon_resolution_name

# change these to update to the latest datasets
ANTARCTIC = 'bedmap3'
GLOBAL = 'gebco2023'

DATASETS = {
    'bedmachinev3': {
        'filename': 'BedMachineAntarctica-v3.nc',
        'proj4': 'epsg:3031',
        'mesh_name': 'BedMachineAntarcticav3_500m',
    },
    'bedmap3': {
        'filename': 'bedmap3.nc',
        'proj4': 'epsg:3031',
        'mesh_name': 'Bedmap3_500m',
        'url': (
            'https://ramadda.data.bas.ac.uk/repository/entry/get/'
            'bedmap3.nc?entryid=synth%3A2d0e4791-8e20-46a3-80e4-'
            'f5f6716025d2%3AL2JlZG1hcDMubmM%3D'
        ),
    },
    'gebco2023': {
        'filename': 'GEBCO_2023.nc',
        'mesh_name': 'GEBCO_2023',
        'source_filename': 'gebco_2023.zip',
        'url': (
            'https://www.bodc.ac.uk/data/open_download/gebco/gebco_2023/zip/'
        ),
        'archive_member': 'GEBCO_2023.nc',
    },
}


@dataclass
class GlobalTile:
    """
    The files for one tile of the global dataset

    Attributes
    ----------
    lon_tile : int
        The tile's index along longitude

    lat_tile : int
        The tile's index along latitude

    source : str
        The tile of the global dataset

    mapping : str
        The weights for remapping the tile to the target grid

    remapped : str
        The tile remapped to the target grid
    """

    lon_tile: int
    lat_tile: int
    source: str
    mapping: str
    remapped: str


@dataclass
class CombineFiles:
    """
    The names of the files the steps that combine topography make and pass
    to one another, relative to each step's work directory

    Attributes
    ----------
    resolution : int or float
        Cubed-sphere faces or degrees

    resolution_name : str
        Either x.xxxxx_degree or neXXX

    target_scrip : str
        The SCRIP file for the target grid

    exodus : str or None
        The exodus file for a cubed-sphere target grid

    global_extracted : str
        The global dataset as extracted from its archive

    global_modified : str
        The global dataset with bounds and an ocean mask added

    global_remapped : str
        The global dataset remapped to the target grid

    tiles : list of polaris.tasks.e3sm.init.topo.combine.files.GlobalTile
        The tiles the global dataset is remapped in, latitude by latitude

    antarctic_modified : str
        The Antarctic dataset with the fields MPAS-Ocean needs

    antarctic_scrip : str
        The SCRIP file for the Antarctic dataset

    antarctic_mapping : str
        The weights for remapping the Antarctic dataset

    antarctic_remapped : str
        The Antarctic dataset remapped to the target grid

    combined : str
        The combined topography on the target grid
    """

    resolution: Union[int, float]
    resolution_name: str
    target_scrip: str
    exodus: Optional[str]
    global_extracted: str
    global_modified: str
    global_remapped: str
    tiles: List[GlobalTile]
    antarctic_modified: str
    antarctic_scrip: str
    antarctic_mapping: str
    antarctic_remapped: str
    combined: str


def get_combine_files(config):
    """
    Get the names of the files the combine-topography steps make from the
    ``[combine_topo]`` config options

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        Config options with a ``[combine_topo]`` section

    Returns
    -------
    files : polaris.tasks.e3sm.init.topo.combine.files.CombineFiles
        The file names
    """
    section = config['combine_topo']
    target_grid = section.get('target_grid')
    if target_grid == 'cubed_sphere':
        resolution = section.getint('resolution_cubedsphere')
        resolution_name = f'ne{resolution}'
        exodus = f'{resolution_name}.g'
    elif target_grid == 'lat_lon':
        resolution = section.getfloat('resolution_latlon')
        resolution_name = format_lat_lon_resolution_name(resolution)
        exodus = None
    else:
        raise ValueError(
            f'Unrecognized target grid: {target_grid}. '
            'Valid options are cubed_sphere or lat_lon'
        )

    if ANTARCTIC not in DATASETS:
        raise ValueError(f'Unrecognized antarctic dataset: {ANTARCTIC}')
    if GLOBAL not in DATASETS:
        raise ValueError(f'Unrecognized global dataset: {GLOBAL}')

    method = section.get('method')

    global_extracted = DATASETS[GLOBAL]['filename']
    if GLOBAL in ['gebco2023']:
        global_modified = global_extracted.replace('.nc', '_cf.nc')
    else:
        global_modified = global_extracted

    antarctic_modified = DATASETS[ANTARCTIC]['filename'].replace(
        '.nc', '_mod.nc'
    )
    antarctic_mesh_name = DATASETS[ANTARCTIC]['mesh_name']

    tiles = list()
    for lat_tile in range(section.getint('lat_tiles')):
        for lon_tile in range(section.getint('lon_tiles')):
            suffix = f'tile_{lon_tile}_{lat_tile}.nc'
            tiles.append(
                GlobalTile(
                    lon_tile=lon_tile,
                    lat_tile=lat_tile,
                    source=f'tiles/{GLOBAL}_{suffix}',
                    mapping=(
                        f'tiles/map_{GLOBAL}_to_{resolution_name}_{method}_'
                        f'{suffix}'
                    ),
                    remapped=f'tiles/{GLOBAL}_{resolution_name}_{suffix}',
                )
            )

    return CombineFiles(
        resolution=resolution,
        resolution_name=resolution_name,
        target_scrip=f'{resolution_name}.scrip.nc',
        exodus=exodus,
        global_extracted=global_extracted,
        global_modified=global_modified,
        global_remapped=global_modified.replace(
            '.nc', f'_{resolution_name}.nc'
        ),
        tiles=tiles,
        antarctic_modified=antarctic_modified,
        antarctic_scrip=antarctic_modified.replace('.nc', '.scrip.nc'),
        antarctic_mapping=(
            f'map_{antarctic_mesh_name}_to_{resolution_name}_{method}.nc'
        ),
        antarctic_remapped=antarctic_modified.replace(
            '.nc', f'_{resolution_name}.nc'
        ),
        combined=f'{ANTARCTIC}_{GLOBAL}_{resolution_name}.nc',
    )


def write_netcdf_with_fill_values(ds, filename, format='NETCDF4'):
    """Write an xarray Dataset with NetCDF4 fill values where needed"""
    ds = ds.copy()
    fill_values = netCDF4.default_fillvals
    # a value of None means "write no _FillValue attribute for this
    # variable", which xarray accepts alongside the numeric fill values
    encoding: dict[str, dict[str, Any]] = {}
    vars = list(ds.data_vars.keys()) + list(ds.coords.keys())
    for var_name in vars:
        # If there's already a fill value attribute, drop it
        ds[var_name].attrs.pop('_FillValue', None)
        is_numeric = np.issubdtype(ds[var_name].dtype, np.number)
        if is_numeric:
            dtype = ds[var_name].dtype
            for fill_type in fill_values:
                if dtype == np.dtype(fill_type):
                    encoding[var_name] = {'_FillValue': fill_values[fill_type]}
                    break
        else:
            encoding[var_name] = {'_FillValue': None}
    ds.to_netcdf(filename, encoding=encoding, format=format)
