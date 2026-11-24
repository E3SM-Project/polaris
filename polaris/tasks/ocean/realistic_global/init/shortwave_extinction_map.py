from polaris.tasks.ocean.realistic_global.forcing.shortwave_extinction.product import (  # noqa: E501
    SHORTWAVE_EXTINCTION_FILENAME,
)

from .lat_lon_map import LatLonMapStep


class ShortwaveExtinctionMapStep(LatLonMapStep):
    """
    A step for building the mapping file from the 1/12-degree shortwave
    extinction product to MPAS cell centers.

    The product is built by
    :py:class:`.ShortwaveExtinctionProductStep`.
    The remapping method is the ``method`` option in the
    ``[shortwave_extinction]`` config section, bilinear by default.
    Conservative remapping is available, but its weights cover a few cells by
    a fraction of a percent more or less than their area.

    The task count is sized from the target mesh as for the other map steps,
    but no lower than the ``ntasks`` and ``min_tasks`` options in
    ``[shortwave_extinction]``: the 9.3 million cell source, not the mesh,
    dominates the cost of building these weights, so even a coarse mesh needs
    many tasks.

    This is the MPI (``mbtempest`` or ESMF) half of the remapping workflow;
    :py:class:`.RemapShortwaveExtinctionStep` applies the resulting weights.
    """

    def __init__(
        self, component, subdir, extinction_step, cull_mesh_step, mesh_name
    ):
        """
        Create the step.

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to.

        subdir : str
            The subdirectory for the step.

        extinction_step : polaris.Step
            The step that produces the shortwave extinction product.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that produces the culled ocean mesh files.

        mesh_name : str
            Name label for the MPAS mesh (used in the remapping weight
            filename).
        """
        super().__init__(
            component=component,
            name='shortwave_extinction_map',
            subdir=subdir,
            source_step=extinction_step,
            source_target=SHORTWAVE_EXTINCTION_FILENAME,
            source_filename=SHORTWAVE_EXTINCTION_FILENAME,
            source_mesh_name='gmis_0.083deg',
            cull_mesh_step=cull_mesh_step,
            mesh_name=mesh_name,
            method='bilinear',
        )

    def runtime_setup(self):
        """
        Take the remapping method from the config before preparing the
        mapping command.
        """
        method = self.config.get('shortwave_extinction', 'method')
        if method not in ['bilinear', 'conserve']:
            raise ValueError(
                f'Unsupported shortwave extinction remapping method: {method}'
            )
        self.remapper.method = method
        super().runtime_setup()

    def _update_ntasks(self):
        """
        Size the task count from the target mesh, but no lower than the
        floors in ``[shortwave_extinction]`` set by the source grid.
        """
        super()._update_ntasks()
        section = self.config['shortwave_extinction']
        self.ntasks = max(self.ntasks, section.getint('ntasks'))
        self.min_tasks = max(self.min_tasks, section.getint('min_tasks'))
