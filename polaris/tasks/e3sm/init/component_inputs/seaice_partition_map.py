import os

from polaris.remap import MappingFileStep
from polaris.tasks.e3sm.init.component_inputs.models import check_seaice_model
from polaris.tasks.e3sm.init.component_inputs.names import get_mesh_short_name

#: The QU60km sea-ice climatology the partitioning weights cells by.  The
#: mask of where ice is present in it is read by the partitioning step
#: rather than here, since it plays no part in building the weights.
CLIMATOLOGY_FILENAME = 'seaice_QU60km_polar.nc'


class SeaicePartitionMapStep(MappingFileStep):
    """
    A step for building the bilinear mapping file from the QU60km sea-ice
    climatology to the sea-ice mesh.

    This is the MPI half of the sea-ice partitioning workflow;
    :py:class:`~polaris.tasks.e3sm.init.component_inputs.seaice_graph_partition.SeaiceGraphPartitionStep`
    applies the resulting weights.  Splitting the two follows the same
    division as the WOA23 and JRA55-do remapping in ``realistic_global``:
    building weights is an MPI job sized for the mapping tool, and using them
    is not.

    Attributes
    ----------
    seaice_mesh_step : polaris.Step
        The step that wrote ``seaice_mesh.nc``, the mesh the weights map onto.

    mesh_short_name : str or None
        The E3SM short name of the mesh, used to label the mapping file.  It
        is not known until ``setup()`` reads it from config.
    """

    def __init__(
        self,
        component,
        subdir,
        seaice_mesh_step,
        name='seaice_partition_map',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        seaice_mesh_step : polaris.Step
            The step that wrote ``seaice_mesh.nc``.

        name : str, optional
            The name of the step.
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            # pyremap partitions the SCRIP files with "mbpart <ntasks>", which
            # rejects a request for a single partition, so the floor is 2
            ntasks=36,
            min_tasks=2,
            method='bilinear',
        )
        self.seaice_mesh_step = seaice_mesh_step
        self.mesh_short_name = None

        self.add_input_file(
            filename=CLIMATOLOGY_FILENAME,
            target=CLIMATOLOGY_FILENAME,
            database='partition',
            database_component='seaice',
        )
        self.add_input_file(
            filename='seaice_mesh.nc',
            work_dir_target=os.path.join(
                seaice_mesh_step.path, 'seaice_mesh.nc'
            ),
        )

    def setup(self):
        """
        Resolve what the mapping file is named after, before anything runs.
        """
        super().setup()
        check_seaice_model(self.config)
        self.mesh_short_name = get_mesh_short_name(self.config)

    def run(self):
        """
        Build the QU60km-to-mesh mapping file.
        """
        check_seaice_model(self.config)
        short_name = get_mesh_short_name(self.config)

        self.remapper.src_from_mpas(
            filename=CLIMATOLOGY_FILENAME, mesh_name='QU60km'
        )
        self.remapper.dst_from_mpas(
            filename='seaice_mesh.nc', mesh_name=short_name
        )
        super().run()
