"""
Masks of the ocean basins the regional overturning is computed over.

Omega cannot yet read region masks, so the overturning of a basin is computed
offline, over the cells of the basin's mask on the simulation's own mesh.  The
masks are the ``MOC Basins`` aggregation of ``geometric_features``, the same
ones E3SM stages for MPAS-Ocean, computed here by the ocean feature-mask step
rather than read from a file that would have to exist for every mesh.
"""

from geometric_features.aggregation import get_aggregator_by_name

from polaris.tasks.mesh.spherical.feature_masks.moc import (
    MOC_MASK_GROUP,
    moc_masks_filename,
)
from polaris.tasks.ocean.analysis.sim_files import SimulationFiles
from polaris.tasks.ocean.feature_masks import ComputeOceanFeatureMasksStep

# The mesh name the mask file is named for.  The simulation's mesh has no name
# the analysis can rely on, and the file is only ever read by the steps of this
# work directory, so a fixed name is all it needs.
MASKS_MESH_NAME = 'simulation'


def get_moc_masks_filename():
    """
    Get the name of the file the basin masks are written to

    Returns
    -------
    filename : str
        The local name of the mask file in the mask step's work directory
    """
    _, _, date = get_aggregator_by_name(MOC_MASK_GROUP)
    return moc_masks_filename(MASKS_MESH_NAME, date)


class MocBasinMasks(ComputeOceanFeatureMasksStep):
    """
    A step that computes the ``MOC Basins`` region masks on the mesh of the
    simulation being analyzed

    The mesh is the one the simulation's Omega configuration names, which is
    only known once the user's config has been read, so it is resolved at
    setup rather than given to the constructor.
    """

    # the masks are an input to the moc step, not a product, and the
    # publish step asks every step of the analysis tasks whether it makes any
    makes_products = False

    def __init__(self, component, subdir):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step
        """
        super().__init__(
            component=component,
            name='moc_basin_masks',
            subdir=subdir,
            mesh_name=MASKS_MESH_NAME,
            mask_group=MOC_MASK_GROUP,
        )

    def setup(self):
        """
        Resolve the simulation's mesh and link it, then set up the step
        """
        sim_files = SimulationFiles(self.config)
        self.mesh_filename = sim_files.mesh_filename()
        super().setup()
