from geometric_features.aggregation import get_aggregator_by_name

from polaris.ocean.model.ocean_io_step import OceanIOStep
from polaris.tasks.mesh.spherical.feature_masks.compute import (
    ComputeFeatureMasksStep,
)
from polaris.tasks.mesh.spherical.feature_masks.moc import (
    MOC_MASK_GROUP,
    add_moc_transects,
    moc_masks_filename,
)


class ComputeOceanFeatureMasksStep(ComputeFeatureMasksStep, OceanIOStep):
    """
    A feature-mask step for MPAS-Ocean or Omega mesh files.

    Omega-specific input translation belongs in the ocean framework.  The
    output remains in standard MPAS mask conventions, except for the
    'MOC Basins' group, which produces a combined basin-mask and
    southern-boundary transect file named
    ``{mesh_name}_mocBasinsAndTransects{date}.nc``.
    """

    def _open_mesh_dataset(self, filename):
        """
        Open a native ocean mesh and map it to standard MPAS names.
        """
        return self.component.open_model_dataset(
            filename,
            config=self.config,
            decode_cf=False,
            decode_times=False,
        )

    def _write_mask_dataset(self, ds_masks, filename):
        """
        Map a mask dataset to native ocean names and write it.
        """
        ds_masks = self.map_to_native_model_vars(ds_masks)
        super()._write_mask_dataset(ds_masks, filename)

    def _set_output_filenames(self, mesh_name, mask_group):
        """
        Set output filenames, using the mocBasinsAndTransects convention
        for the 'MOC Basins' group.
        """
        super()._set_output_filenames(mesh_name, mask_group)
        if mask_group == MOC_MASK_GROUP:
            _, _, date = get_aggregator_by_name(mask_group)
            self.output_filename = moc_masks_filename(mesh_name, date)
            # geojson_filename stays as mocBasins{date}.geojson (set by super)

    def _post_process_masks(self, ds_masks, ds_mesh, mask_group):
        """
        For 'MOC Basins', append southern-boundary transects to the mask
        dataset and drop string variables that are incompatible with CDF5.
        """
        if mask_group != MOC_MASK_GROUP:
            return ds_masks
        return add_moc_transects(ds_masks, ds_mesh, logger=self.logger)
