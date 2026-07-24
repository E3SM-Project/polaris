import os

import gsw
import numpy as np
import xarray as xr

from polaris.ocean.coriolis import add_coriolis_to_dataset
from polaris.ocean.init_state import (
    add_density_from_specvol,
    add_quiescent_normal_velocity,
    layer_thickness_from_geom_interfaces,
)
from polaris.ocean.model import OceanIOStep


class InitialStateStep(OceanIOStep):
    """
    A step that reads ``pstar_init.nc`` and writes model-specific
    ocean initial condition files.

    The target ocean model is read from the ``[ocean] model`` config option
    (resolved to ``'omega'`` or ``'mpas-ocean'`` during component setup).

    For Omega the output is split between ``vert_coord.nc`` (vertical
    coordinate variables) and ``init.nc`` (tracer and dynamical fields).
    For MPAS-Ocean all variables remain in ``init.nc``.

    Tracer conventions differ between the two models:

    * **Omega**: conservative temperature (CT) and absolute salinity (SA)
      are written directly.
    * **MPAS-Ocean**: CT is converted to potential temperature via GSW and
      SA is converted to practical salinity.

    Both models receive the same converged geometric layer thicknesses as
    ``restingThickness`` (and ``layerThickness`` at quiescent
    initialisation).  Wind stress and restoring fields are deferred to a
    separate ``ForcingStep`` (not implemented here).

    Attributes
    ----------
    pstar_init_step : polaris.Step
        Upstream step that produces ``pstar_init.nc``.

    cull_mesh_step : polaris.Step
        Upstream cull-mesh step whose outputs include the MPAS mesh file
        and graph file.
    """

    def __init__(
        self,
        component,
        subdir,
        pstar_init_step,
        cull_mesh_step,
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        pstar_init_step : polaris.Step
            The step that produces ``pstar_init.nc``.

        cull_mesh_step : polaris.Step
            The step that produces ``culled_ocean_mesh.nc``
            and ``culled_ocean_graph.info``.
        """
        super().__init__(
            component=component,
            name='initial_state',
            subdir=subdir,
            ntasks=1,
            min_tasks=1,
        )
        self.pstar_init_step = pstar_init_step
        self.cull_mesh_step = cull_mesh_step

    def setup(self):
        """
        Declare input and output files based on the configured ocean model.
        """
        super().setup()
        self.add_input_file(
            filename='pstar_init.nc',
            work_dir_target=os.path.join(
                self.pstar_init_step.path,
                'pstar_init.nc',
            ),
        )
        self.add_input_file(
            filename='culled_mesh.nc',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_mesh.nc',
            ),
        )
        self.add_input_file(
            filename='culled_graph.info',
            work_dir_target=os.path.join(
                self.cull_mesh_step.path,
                'culled_ocean_graph.info',
            ),
        )
        self.add_output_files_for_ocean_model_input(
            horiz_mesh_filename='mesh.nc',
            vert_coord_filename='vert_coord.nc',
            init_filename='init.nc',
            graph_filename='culled_graph.info',
        )

    def run(self):
        """
        Build model-specific initial condition files from ``pstar_init.nc``.
        """
        config = self.config
        model = config.get('ocean', 'model')

        ds = xr.open_dataset('pstar_init.nc')
        ds_mesh = xr.open_dataset('culled_mesh.nc')

        # Add the Coriolis parameter (fCell/fEdge/fVertex) to the horizontal
        # mesh and write it out; the culled mesh does not include these fields,
        # which the ocean model requires in its mesh stream.
        ds_mesh = add_coriolis_to_dataset(config, ds_mesh)
        self.write_horiz_mesh_dataset(ds_mesh, 'mesh.nc', config)

        ds = layer_thickness_from_geom_interfaces(ds)
        ds = add_quiescent_normal_velocity(ds, ds_mesh)
        ds = add_density_from_specvol(ds)

        if model == 'mpas-ocean':
            ds = _convert_tracers_mpas_ocean(ds, ds_mesh)

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        self.write_initial_state_dataset(ds, 'init.nc', config)


def _convert_tracers_mpas_ocean(ds, ds_mesh):
    """
    Convert conservative temperature and absolute salinity in ``ds`` to the
    MPAS-Ocean tracer conventions (potential temperature and practical
    salinity) using GSW.

    Parameters
    ----------
    ds : xarray.Dataset
        P-star init dataset with ``temperature`` (CT, degC),
        ``salinity`` (SA, g/kg), and ``pressure`` (Pa).

    ds_mesh : xarray.Dataset
        Culled mesh dataset with ``lonCell`` and ``latCell`` (radians).

    Returns
    -------
    xarray.Dataset
        Dataset with ``temperature`` as potential temperature (degC) and
        ``salinity`` as practical salinity (PSU).
    """
    ct = ds['temperature'].values  # (1, nCells, nVertLevels)
    sa = ds['salinity'].values
    p_pa = ds['pressure'].values  # Pa
    p_dbar = p_pa / 1e4  # Pa -> dbar  (1 dbar = 1e4 Pa)

    lon_deg = np.rad2deg(ds_mesh['lonCell'].values)  # (nCells,)
    lat_deg = np.rad2deg(ds_mesh['latCell'].values)

    # Broadcast lon/lat to (1, nCells, nVertLevels) for GSW
    lon_3d = lon_deg[np.newaxis, :, np.newaxis] * np.ones_like(ct)
    lat_3d = lat_deg[np.newaxis, :, np.newaxis] * np.ones_like(ct)

    valid = np.isfinite(ct) & np.isfinite(sa)
    pot_temp = np.full_like(ct, np.nan)
    prac_sal = np.full_like(sa, np.nan)

    pot_temp[valid] = gsw.t_from_CT(sa[valid], ct[valid], p_dbar[valid])
    prac_sal[valid] = gsw.SP_from_SA(
        sa[valid], p_dbar[valid], lon_3d[valid], lat_3d[valid]
    )

    ds['temperature'] = xr.DataArray(
        data=pot_temp,
        dims=ds['temperature'].dims,
        attrs={
            'long_name': 'potential temperature',
            'units': 'degC',
        },
    )
    ds['salinity'] = xr.DataArray(
        data=prac_sal,
        dims=ds['salinity'].dims,
        attrs={
            'long_name': 'practical salinity',
            'units': 'PSU',
        },
    )
    return ds
