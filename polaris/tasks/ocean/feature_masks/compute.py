from polaris.ocean.model.ocean_io_step import OceanIOStep
from polaris.tasks.mesh.spherical.feature_masks.compute import (
    ComputeFeatureMasksStep,
)


class ComputeOceanFeatureMasksStep(ComputeFeatureMasksStep, OceanIOStep):
    """
    A feature-mask step for MPAS-Ocean or Omega mesh files.

    Omega-specific input translation belongs in the ocean framework.  The
    output remains in standard MPAS mask conventions.
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
