import os

import xarray as xr

from polaris.mesh import QuasiUniformSphericalMeshStep


class UnifiedCellWidthMeshStep(QuasiUniformSphericalMeshStep):
    """
    A spherical mesh step that consumes an upstream unified sizing field.
    """

    def __init__(
        self,
        component,
        sizing_field_step=None,
        name='unified_base_mesh',
        subdir=None,
        mesh_name='mesh',
    ):
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            cell_width=None,
            mesh_name=mesh_name,
        )
        self.sizing_field_step = sizing_field_step
        self.sizing_field_filename = 'sizing_field.nc'

    def setup(self):
        """
        Link an upstream sizing field if one has been provided.
        """
        if self.sizing_field_step is not None:
            self.add_input_file(
                filename=self.sizing_field_filename,
                work_dir_target=os.path.join(
                    self.sizing_field_step.path,
                    self.sizing_field_step.sizing_field_filename,
                ),
            )
        super().setup()

    def build_cell_width_lat_lon(self):
        """
        Read the cell width, lon, and lat directly from sizing_field.nc.
        """
        with xr.open_dataset(self.sizing_field_filename) as ds_sizing:
            if 'cellWidth' not in ds_sizing:
                raise ValueError(
                    'Expected variable "cellWidth" in sizing_field.nc.'
                )
            if 'lat' not in ds_sizing.coords or 'lon' not in ds_sizing.coords:
                raise ValueError(
                    'Expected lat/lon coordinates in sizing_field.nc.'
                )
            cell_width = ds_sizing.cellWidth.values
            lon = ds_sizing.lon.values
            lat = ds_sizing.lat.values
        return cell_width, lon, lat
