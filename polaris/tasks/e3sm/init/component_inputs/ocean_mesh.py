import os

import numpy as np
import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.ocean.vertical import compute_zint_zmid_from_layer_thickness
from polaris.tasks.e3sm.init.component_inputs.models import check_ocean_model

#: The vertical-coordinate fields the staged mesh carries, all of which the
#: initial-state step already writes.
VERT_COORD_VARS = [
    'refBottomDepth',
    'refTopDepth',
    'refZMid',
    'vertCoordMovementWeights',
    'bottomDepth',
    'minLevelCell',
    'maxLevelCell',
    'cellMask',
    'layerThickness',
    'restingThickness',
    'ssh',
]


class OceanMeshStep(Step):
    """
    A step for staging the MPAS-Ocean mesh file.

    The horizontal mesh comes from the initial-state step's ``mesh.nc`` -- the
    culled ocean mesh plus Coriolis, which is exactly what MPAS-Ocean reads in
    its mesh stream -- and the vertical coordinate from its ``init.nc``.  All
    of :py:data:`VERT_COORD_VARS` is already written there, so unlike the
    Compass step this replaces, nothing is recomputed but ``zMid``.

    ``zMid`` is derived from the ``layerThickness`` and ``bottomDepth`` in
    this same file rather than taken from the initial state's ``GeomZMid``,
    which is the same quantity arrived at through the p-star iteration.  The
    two agree, but deriving it here is what makes the staged file internally
    consistent, which is the property MPAS-Ocean depends on.

    No land-ice fields and no cavity gating: the unified meshes are culled
    under the ``calving_front`` convention and run with
    ``config_land_ice_flux_mode = off``, so the ``landIcePressurePKG``
    variables are never allocated.  Writing them as zeros "to be safe" would
    be the safer-looking choice that is harder to debug later.

    Attributes
    ----------
    init_step : polaris.Step
        The initial-state step that wrote the mesh and vertical coordinate.
    """

    def __init__(self, component, subdir, init_step, name='ocean_mesh'):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        init_step : polaris.Step
            The initial-state step that wrote ``mesh.nc`` and ``init.nc``.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.init_step = init_step

        for filename in ['mesh.nc', 'init.nc']:
            self.add_input_file(
                filename=filename,
                work_dir_target=os.path.join(init_step.path, filename),
            )
        self.add_output_file(filename='ocean_mesh.nc')

    def setup(self):
        """
        Refuse a model whose packaging is not supported, before anything runs.
        """
        super().setup()
        check_ocean_model(self.config)

    def run(self):
        """
        Combine the horizontal mesh and the vertical coordinate.
        """
        super().run()
        check_ocean_model(self.config)

        with xr.open_dataset('mesh.nc') as ds_mesh:
            ds_out = ds_mesh.load()
        with xr.open_dataset('init.nc') as ds_init:
            ds_vert = ds_init[VERT_COORD_VARS].load()

        ds_out = ds_out.merge(ds_vert)
        ds_out = _add_ref_layer_thickness(ds_out)
        ds_out = _add_zmid(ds_out)

        # config options belong to the run that produced the file, not to the
        # mesh, and staging them would carry this workflow's settings into
        # every run that reads it
        for attr in list(ds_out.attrs):
            if attr.startswith('config_'):
                ds_out.attrs.pop(attr)

        write_netcdf(ds_out, 'ocean_mesh.nc')


def _add_ref_layer_thickness(ds):
    """
    The reference layer thicknesses, which the initial state does not write.
    """
    interfaces = np.append([0.0], ds.refBottomDepth.values)
    ds['refLayerThickness'] = ('nVertLevels', interfaces[1:] - interfaces[:-1])
    ds.refLayerThickness.attrs['units'] = 'm'
    ds.refLayerThickness.attrs['long_name'] = (
        'Reference layer thickness of ocean for each vertical level.'
    )
    return ds


def _add_zmid(ds):
    """
    The elevation of each layer's midpoint, from this file's own thicknesses.
    """
    layer_thickness = ds.layerThickness
    if 'Time' in layer_thickness.dims:
        layer_thickness = layer_thickness.isel(Time=0)

    _, z_mid = compute_zint_zmid_from_layer_thickness(
        layer_thickness=layer_thickness,
        bottom_depth=ds.bottomDepth,
        # the stored indices are one-based, the helper wants zero-based
        min_level_cell=ds.minLevelCell - 1,
        max_level_cell=ds.maxLevelCell - 1,
    )
    ds['zMid'] = z_mid.expand_dims(dim='Time', axis=0)
    ds.zMid.attrs['units'] = 'm'
    ds.zMid.attrs['long_name'] = 'z-coordinate of the mid-depth of the layer'
    return ds
