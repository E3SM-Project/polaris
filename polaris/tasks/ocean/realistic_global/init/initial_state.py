import os

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

    The tracers in ``pstar_init.nc`` are conservative temperature and
    absolute salinity (the TEOS-10 convention).  Converting them to the
    convention the target model expects is the framework's job, done in
    :py:meth:`polaris.ocean.model.OceanIOStep.write_initial_state_dataset`,
    so this step only has to supply the per-cell locations the conversion
    needs (``pstar_init.nc`` carries no horizontal mesh fields).

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

        # the tracer conversion happens on write and needs per-cell locations,
        # which only the horizontal mesh has
        lon = np.rad2deg(ds_mesh['lonCell'].values)
        lat = np.rad2deg(ds_mesh['latCell'].values)

        self.write_vert_coord_dataset(ds, 'vert_coord.nc', config)
        self.write_initial_state_dataset(
            ds, 'init.nc', config, lon=lon, lat=lat
        )
