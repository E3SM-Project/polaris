from polaris.e3sm.init.topo.resolutions import (
    LAT_LON_RESOLUTIONS,
    format_lat_lon_resolution_name,
)


def test_supported_lat_lon_resolutions_and_names():
    expected_resolutions = (1.0, 0.25, 0.125, 0.0625, 0.03125)

    assert LAT_LON_RESOLUTIONS == expected_resolutions
    assert format_lat_lon_resolution_name(1.0) == '1.00000_degree'
    assert format_lat_lon_resolution_name(0.25) == '0.25000_degree'
    assert format_lat_lon_resolution_name(0.125) == '0.12500_degree'
    assert format_lat_lon_resolution_name(0.0625) == '0.06250_degree'
    assert format_lat_lon_resolution_name(0.03125) == '0.03125_degree'
