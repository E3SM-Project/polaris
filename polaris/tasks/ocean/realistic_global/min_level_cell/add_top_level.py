import os
from typing import TYPE_CHECKING, Dict

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris.io import symlink
from polaris.ocean.model import OceanIOStep
from polaris.tasks.ocean.realistic_global.forward import InitialCondition

if TYPE_CHECKING:
    from polaris.ocean.model import OceanModelFilesMixin

#: The mesh with the added level, relative to the step's work directory
MESH_FILENAME = 'top_level_mesh.nc'

#: The initial state with the added level
INIT_FILENAME = 'top_level_init.nc'

#: The graph file, linked from wherever the source's comes from
GRAPH_FILENAME = 'graph.info'

#: The vertical dimensions an added level is prepended to
VERTICAL_DIMS = ['nVertLevels', 'nVertLevelsP1']

#: The 1-based level indices of the top and bottom active levels, which the
#: added level moves down by one.  Only the cell indices are in an MPAS-Ocean
#: initial condition; the model computes the edge and vertex ones from them,
#: but they are shifted too if a file has them.
LEVEL_INDEX_VARS = [
    'minLevelCell',
    'maxLevelCell',
    'minLevelEdgeTop',
    'minLevelEdgeBot',
    'maxLevelEdgeTop',
    'maxLevelEdgeBot',
    'minLevelVertexTop',
    'minLevelVertexBot',
    'maxLevelVertexTop',
    'maxLevelVertexBot',
]


def add_top_level(ds: xr.Dataset) -> xr.Dataset:
    """
    Add an inactive level above every column of an MPAS-Ocean dataset.

    Every variable with a vertical dimension gets a new first level holding
    zeros, and the level indices move down by one, so the active levels keep
    their values at an index one higher.  A dataset without ``minLevelCell``
    has every column starting at the top level, which is what MPAS-Ocean
    assumes, and gets ``minLevelCell = 2`` everywhere.

    Zero is the right value for the reference coordinate: a reference layer of
    zero thickness at the surface leaves every active level at the reference
    depth it had before, so ``refBottomDepth`` and ``refZMid`` are unchanged
    for the active levels.  It is also what E3SM initial conditions hold in
    inactive levels below the bottom, and MPAS-Ocean overwrites the tracers
    and velocity in inactive levels with fill values at startup anyway.

    Parameters
    ----------
    ds : xarray.Dataset
        An MPAS-Ocean mesh or initial condition

    Returns
    -------
    xarray.Dataset
        The same dataset with an inactive level above every column
    """
    var_order = list(ds.data_vars)
    vertical = [
        var
        for var in var_order
        if any(dim in ds[var].dims for dim in VERTICAL_DIMS)
    ]
    padded = {var: _pad_top(ds[var]) for var in vertical}
    # all at once, since a dataset cannot hold a dimension at two sizes
    ds = ds.drop_vars(vertical).assign(padded)[var_order]

    if 'maxLevelCell' in ds and 'minLevelCell' not in ds:
        ds['minLevelCell'] = xr.ones_like(ds.maxLevelCell)

    for var in LEVEL_INDEX_VARS:
        if var in ds:
            # zero marks a land cell, edge or vertex with no active level
            index = ds[var]
            ds[var] = xr.where(index > 0, index + 1, index).astype(index.dtype)
            ds[var].attrs = index.attrs

    return ds


class AddTopLevel(OceanIOStep):
    """
    A step that writes a copy of an initial condition with an inactive level
    above every column, so that ``minLevelCell`` is 2 everywhere and
    ``maxLevelCell`` is one more than before.

    The step reads whatever files its source initial condition gives a forward
    run, and writes the mesh and initial state again with the added level.  A
    source that gives them in one file, as a cached initial condition does, is
    read once and its copy written once.  The graph file, and the forcing file
    of a source with one of its own, have no vertical dimension and are passed
    on as they are, through this step's links to them.

    Attributes
    ----------
    init_condition : InitialCondition
        The source of the files without the added level
    """

    def __init__(self, component, indir, init_condition: InitialCondition):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        indir : str
            The directory the step is in, to which ``name`` is appended

        init_condition : InitialCondition
            The source of the files without the added level
        """
        super().__init__(
            component=component, name='add_top_level', indir=indir
        )
        self.init_condition = init_condition
        for filename in [MESH_FILENAME, INIT_FILENAME]:
            self.add_output_file(filename=filename)

    def setup(self):
        """
        Add the source's files as inputs, along with its graph file if it
        names one rather than adding it itself
        """
        super().setup()
        self.init_condition.add_input_files(self)
        graph_target = self.init_condition.graph_target
        if graph_target is not None:
            self.add_input_file(
                filename=GRAPH_FILENAME, work_dir_target=graph_target
            )

    def run(self):
        """
        Write the mesh and initial state with the added level
        """
        written: Dict[str, str] = dict()
        for in_filename, out_filename in [
            (self.get_horiz_mesh_filename(), MESH_FILENAME),
            (self.get_init_filename(), INIT_FILENAME),
        ]:
            source = os.path.realpath(in_filename)
            if source in written:
                symlink(written[source], out_filename)
                continue
            with xr.open_dataset(in_filename, decode_times=False) as ds:
                ds = add_top_level(ds)
                write_netcdf(ds, out_filename)
            written[source] = out_filename
            self.logger.info(
                f'Wrote {out_filename} from {in_filename} with an inactive '
                f'level added at the top'
            )


class TopLevelInitialCondition(InitialCondition):
    """
    The files an :py:class:`AddTopLevel` step writes, given to a forward run
    in place of the ones its source would give.

    Attributes
    ----------
    source : InitialCondition
        The initial condition without the added level

    add_top_level : AddTopLevel
        The step that writes the files with the added level
    """

    def __init__(self, add_top_level: AddTopLevel):
        """
        Create the source

        Parameters
        ----------
        add_top_level : AddTopLevel
            The step that writes the files with the added level
        """
        self.add_top_level = add_top_level
        self.source = add_top_level.init_condition
        self.min_res = self.source.min_res
        self.approx_cell_count = self.source.approx_cell_count
        self.graph_target = f'{add_top_level.path}/{GRAPH_FILENAME}'

    def add_input_files(self, step: 'OceanModelFilesMixin') -> None:
        """
        Link the mesh and initial state with the added level, and the forcing
        file if the source has one of its own
        """
        path = self.add_top_level.path
        step.add_horiz_mesh_input_file(
            work_dir_target=f'{path}/{MESH_FILENAME}'
        )
        step.add_init_input_file(work_dir_target=f'{path}/{INIT_FILENAME}')
        forcing_filename = self.get_forcing_filename(step)
        if forcing_filename != step.get_init_filename():
            step.add_forcing_input_file(
                work_dir_target=f'{path}/{forcing_filename}'
            )

    def get_forcing_filename(self, step: 'OceanModelFilesMixin') -> str:
        """
        The source's forcing file, which has no vertical dimension.  A source
        that carries the wind stress in its initial state names the initial
        state, which then means the one with the added level.
        """
        return self.source.get_forcing_filename(step)


def _pad_top(da: xr.DataArray) -> xr.DataArray:
    """A zero level above the top of each vertical dimension of ``da``"""
    padded = da
    for dim in VERTICAL_DIMS:
        if dim in da.dims:
            padded = padded.pad({dim: (1, 0)}, constant_values=0)
    padded.attrs = da.attrs
    return padded
