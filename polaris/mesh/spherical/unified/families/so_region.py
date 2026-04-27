SO_REGION_FILENAME = 'high_res_region.geojson'
SO_REGION_PACKAGE = 'polaris.mesh.base.so'


class SORegionUnifiedMeshFamily:
    """
    The Southern Ocean unified-mesh family.
    """

    name = 'so_region'

    def setup_sizing_field_step(self, step):
        """
        Link the shared Southern Ocean refinement region.
        """
        step.add_input_file(
            filename=SO_REGION_FILENAME, package=SO_REGION_PACKAGE
        )

    def build_ocean_background(self, ds_coastline, section):
        """
        Build the Southern Ocean background on the shared target grid.
        """
        from polaris.mesh.base.so.background import (
            build_southern_ocean_background,
        )

        return build_southern_ocean_background(
            lat=ds_coastline.lat.values,
            lon=ds_coastline.lon.values,
            high_res_km=section.getfloat('ocean_background_min_km'),
            low_res_km=section.getfloat('ocean_background_max_km'),
            region_filename=SO_REGION_FILENAME,
        )
