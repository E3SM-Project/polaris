from geometric_features.aggregation import get_aggregator_by_name

from polaris.tasks.e3sm.init.component_inputs import names
from polaris.tasks.e3sm.init.component_inputs.models import check_ocean_model
from polaris.tasks.mesh.spherical.feature_masks.compute import (
    ComputeFeatureMasksStep,
)
from polaris.tasks.mesh.spherical.feature_masks.moc import (
    MOC_MASK_GROUP,
    add_moc_transects,
    moc_masks_filename,
)

#: The culled mesh the masks are computed on: the full ocean domain, matching
#: what the ocean initial condition is built from.
MESH_FILENAME = 'culled_ocean_mesh.nc'


class MocMasksStep(ComputeFeatureMasksStep):
    """
    A step for the MOC basin masks and southern-boundary transects that
    MPAS-Ocean reads at run time.

    E3SM points two streams at this one file, ``regionalMasksInput`` and
    ``transectMasksInput``, and two analysis members that are on by default
    read them: ``mocStreamfunction``, which E3SM enables per mesh and has
    enabled for every mesh since ``EC30to60E2r2``, and
    ``meridionalHeatTransport``, which is enabled for every mesh.  Without the
    file neither aborts -- ``nRegions`` and ``nRegionGroups`` fall back to 1
    and the MOC member logs that its region group was not found and carries on
    -- so the failure is output computed against a meaningless region, with
    nothing to notice in a run.  That is why this is a component input and not
    one of the analysis products in the follow-up work.

    The masks come from the mesh component's feature-mask step; the MOC
    filename and the southern-boundary transects come from
    :py:mod:`polaris.tasks.mesh.spherical.feature_masks.moc`, which the ocean
    feature-mask step uses too.  Nothing here reaches for an ocean component,
    so an ``e3sm/init`` step can build these masks without an ``[ocean]``
    config section.

    Attributes
    ----------
    features_date : str
        The date stamp of the ``geometric_features`` aggregation the masks
        were built from, which is not the date the file was created.
    """

    def __init__(
        self,
        component,
        subdir,
        cull_mesh_step,
        mesh_name,
        name='moc_masks',
    ):
        """
        Create a new step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to.

        subdir : str
            The subdirectory for the step.

        cull_mesh_step : polaris.tasks.e3sm.init.topo.cull.cull.CullMeshStep
            The step that produces the culled ocean mesh.

        mesh_name : str
            The name of the base mesh, used in this step's own output
            filename.  The staged filename is built from the mesh's E3SM
            short name instead, by
            :py:func:`~polaris.tasks.e3sm.init.component_inputs.names.ocean_moc_masks_path`.

        name : str, optional
            The name of the step.
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            mesh_step=cull_mesh_step,
            mesh_filename=MESH_FILENAME,
            mesh_name=mesh_name,
            mask_group=MOC_MASK_GROUP,
        )
        _, _, self.features_date = get_aggregator_by_name(MOC_MASK_GROUP)
        # the assembly step reads the filename while it is being constructed,
        # which is before setup() would set it; this is the same pure call
        # setup() makes, so the two cannot disagree
        self._set_output_filenames(mesh_name, MOC_MASK_GROUP)

    def setup(self):
        """
        Set up the step, failing early for a model that cannot be packaged.
        """
        super().setup()
        check_ocean_model(self.config)

    def run(self):
        """
        Compute the masks, failing early for a model that cannot be packaged.
        """
        check_ocean_model(self.config)
        super().run()

    def _set_output_filenames(self, mesh_name, mask_group):
        """
        Name the output with the convention E3SM's inputdata already uses.
        """
        super()._set_output_filenames(mesh_name, mask_group)
        self.output_filename = moc_masks_filename(
            mesh_name=mesh_name, date=self.features_date
        )

    def _post_process_masks(self, ds_masks, ds_mesh, mask_group):
        """
        Append the southern-boundary transects the MOC member needs.
        """
        return add_moc_transects(ds_masks, ds_mesh, logger=self.logger)

    def _write_mask_dataset(self, ds_masks, filename):
        """
        Record where the masks came from, then write them.

        Both dates are recorded because either can change on its own: the
        aggregation is upstream data shared by every mesh, while the creation
        date belongs to this mesh's staged file.
        """
        ds_masks = ds_masks.copy()
        ds_masks.attrs['mask_features_date'] = self.features_date
        ds_masks.attrs['mask_features_source'] = (
            f'geometric_features aggregation {MOC_MASK_GROUP!r}'
        )
        ds_masks.attrs['creation_date'] = names.get_creation_date(self.config)
        super()._write_mask_dataset(ds_masks, filename)
