from geometric_features.aggregation import get_aggregator_by_name
from mpas_tools.ocean.moc import add_moc_southern_boundary_transects

from polaris.ocean.model.ocean_io_step import OceanIOStep
from polaris.tasks.mesh.spherical.feature_masks.compute import (
    ComputeFeatureMasksStep,
    get_feature_masks_filename,
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
        if mask_group == 'MOC Basins':
            _, _, date = get_aggregator_by_name(mask_group)
            self.output_filename = get_feature_masks_filename(
                mesh_name=mesh_name,
                prefix='mocBasinsAndTransects',
                date=date,
            )
            # geojson_filename stays as mocBasins{date}.geojson (set by super)

    def _post_process_masks(self, ds_masks, ds_mesh, mask_group):
        """
        For 'MOC Basins', append southern-boundary transects to the mask
        dataset and drop string variables that are incompatible with CDF5.
        """
        if mask_group != 'MOC Basins':
            return ds_masks
        ds_masks = add_moc_southern_boundary_transects(
            ds_masks, ds_mesh, logger=self.logger
        )
        to_drop = [v for v in ['history', 'constituents'] if v in ds_masks]
        if to_drop:
            ds_masks = ds_masks.drop_vars(to_drop)
        return ds_masks
