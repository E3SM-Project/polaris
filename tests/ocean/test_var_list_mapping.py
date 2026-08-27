import pytest

from polaris.tasks.ocean import Ocean


@pytest.fixture
def component():
    """An ocean component set up to read Omega output."""
    component = Ocean()
    component.model = 'omega'
    component._read_var_map()
    return component


def test_mapping_from_native_names_is_the_inverse_of_mapping_to_them(
    component,
):
    """The two directions have to agree, or a round trip loses variables."""
    mpaso = ['temperature', 'salinity', 'ssh', 'kineticEnergyCell']
    omega = component.map_var_list_to_native_model(mpaso)
    assert omega == ['Temperature', 'Salinity', 'SshCell', 'KineticEnergyCell']
    assert component.map_var_list_from_native_model(omega) == mpaso


def test_an_omega_only_field_keeps_its_name(component):
    """PseudoThickness is deliberately unmapped, so it survives unchanged."""
    omega = ['Temperature', 'PseudoThickness', 'SurfacePressure']
    assert component.map_var_list_from_native_model(omega) == [
        'temperature',
        'PseudoThickness',
        'SurfacePressure',
    ]


def test_the_order_asked_for_is_the_order_returned(component):
    omega = ['SshCell', 'Temperature', 'Salinity']
    assert component.map_var_list_from_native_model(omega) == [
        'ssh',
        'temperature',
        'salinity',
    ]


def test_mpas_ocean_names_are_left_alone():
    component = Ocean()
    component.model = 'mpas-ocean'
    names = ['temperature', 'layerThickness']
    assert component.map_var_list_from_native_model(names) == names
