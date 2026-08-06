import os

import xarray as xr
from mpas_tools.io import write_netcdf

from polaris import Step
from polaris.tasks.e3sm.init.component_inputs.maps import (
    CULLED_MESH_SUFFIXES,
    base_to_culled_maps,
)


class BaseMeshStep(Step):
    """
    A step for staging the base mesh with maps to the meshes culled from it.

    The base mesh itself is unchanged; what this adds is the nine
    ``mapBaseTo{Ocean,OceanNoCavities,Land}{Cell,Edge,Vertex}`` fields, so that
    a consumer holding the base mesh -- the MOAB coupler, which maps to and
    from it -- can find each element on each culled mesh without a second
    file.

    Attributes
    ----------
    base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
        The step that built the base mesh.

    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
        The step that culled it, and wrote the forward index maps.

    with_maps : bool
        Whether the index maps are added.
    """

    def __init__(
        self,
        component,
        subdir,
        base_mesh_step,
        cull_mesh_step,
        with_maps,
        name='base_mesh',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        base_mesh_step : polaris.mesh.spherical.SphericalBaseStep
            The step that built the base mesh.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
            The step that culled it, and wrote the forward index maps.

        with_maps : bool
            Whether to add the index maps.  Only meshes that are actually
            culled have them to add.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.base_mesh_step = base_mesh_step
        self.cull_mesh_step = cull_mesh_step
        self.with_maps = with_maps

        if with_maps:
            for prefix in CULLED_MESH_SUFFIXES:
                filename = f'{prefix}_map_culled_to_base.nc'
                self.add_input_file(
                    filename=filename,
                    work_dir_target=os.path.join(
                        cull_mesh_step.path, filename
                    ),
                )

        self.add_output_file(filename=self.output_filename)

    @property
    def output_filename(self):
        """
        str : The file this step writes.  Named for what it contains, so that
        a mesh with no culled meshes to map to does not produce a file
        promising maps that are not there.
        """
        return 'base_mesh_with_maps.nc' if self.with_maps else 'base_mesh.nc'

    def setup(self):
        """
        Link the base mesh, whose filename is a config option of the step that
        built it.
        """
        super().setup()
        base_filename = self.base_mesh_step.config.get(
            'spherical_mesh', 'mpas_mesh_filename'
        )
        self.add_input_file(
            filename='base_mesh.nc',
            work_dir_target=os.path.join(
                self.base_mesh_step.path, base_filename
            ),
        )

    def run(self):
        """
        Add the base-to-culled index maps to the base mesh and write it out.
        """
        super().run()
        with xr.open_dataset('base_mesh.nc') as ds_base:
            ds_out = ds_base.load()

        if self.with_maps:
            sizes = {
                dim: ds_out.sizes[dim]
                for dim in ['nCells', 'nEdges', 'nVertices']
            }
            ds_maps = {}
            for prefix in CULLED_MESH_SUFFIXES:
                with xr.open_dataset(
                    f'{prefix}_map_culled_to_base.nc'
                ) as ds_map:
                    ds_maps[prefix] = ds_map.load()
            ds_out = ds_out.merge(
                base_to_culled_maps(
                    ds_maps_culled_to_base=ds_maps, sizes=sizes
                )
            )

        write_netcdf(ds_out, self.output_filename)
