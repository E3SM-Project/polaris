import os

from mpas_tools.logging import check_call

from polaris import Step
from polaris.tasks.e3sm.init.component_inputs.names import (
    SCRIP_REGIONS,
    get_mesh_short_name,
)


class ScripStep(Step):
    """
    A step for staging the SCRIP descriptions of the culled meshes.

    The cull step already writes these, so no grid description is recomputed
    here.  What this step does is restamp the ``mesh_name`` attribute: the cull
    step names the mesh for how it was built (``u.oi30.lr10_ocean``), and a
    file headed for E3SM's inputdata server should identify the released mesh
    (``u02.oi30.lr10_ocean``) instead -- the same argument that decides the
    staged filenames.

    The attribute is edited with ``ncatted`` rather than by reading and
    rewriting the file.  These are NETCDF3_64BIT_DATA files that the cull step
    already found prohibitively slow to write directly, and rewriting the grid
    corners to change one string would be all of that cost for none of the
    benefit.

    Attributes
    ----------
    cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
        The step that wrote the SCRIP files.

    mesh_short_name : str or None
        The E3SM short name, resolved at setup.
    """

    def __init__(self, component, subdir, cull_mesh_step, name='scrip'):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.CullMeshStep
            The step that wrote the SCRIP files.

        name : str, optional
            The name of the step.
        """
        super().__init__(component=component, name=name, subdir=subdir)
        self.cull_mesh_step = cull_mesh_step
        self.mesh_short_name = None

        for region in SCRIP_REGIONS:
            filename = f'culled_{region}_mesh.scrip.nc'
            self.add_input_file(
                filename=filename,
                work_dir_target=os.path.join(cull_mesh_step.path, filename),
            )
            self.add_output_file(filename=self.scrip_filename(region))

    @staticmethod
    def scrip_filename(region):
        """
        The file this step writes for one culled-mesh region.

        Parameters
        ----------
        region : str
            The culled-mesh region.

        Returns
        -------
        str
            The filename, relative to the step's work directory.
        """
        return f'{region}.scrip.nc'

    def setup(self):
        """
        Resolve the E3SM short name, so that a mesh with none assigned fails
        here rather than after the workflow has run.
        """
        super().setup()
        self.mesh_short_name = get_mesh_short_name(self.config)

    def run(self):
        """
        Restamp each SCRIP file with the E3SM mesh name.
        """
        super().run()
        short_name = get_mesh_short_name(self.config)
        for region in SCRIP_REGIONS:
            args = [
                'ncatted',
                '-O',
                '-a',
                f'mesh_name,global,o,c,{short_name}_{region}',
                f'culled_{region}_mesh.scrip.nc',
                self.scrip_filename(region),
            ]
            check_call(args, self.logger)
