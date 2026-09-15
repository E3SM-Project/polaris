"""
Unit tests for the mass per unit area each model's thickness implies.

What matters here is that the two models are read from the variables they
actually write, that neither is silently accepted in place of the other, and
that the constant multiplying them is the reference density the models
themselves used.
"""

import numpy as np
import pytest
import xarray as xr

from polaris.config import PolarisConfigParser
from polaris.constants import get_constant
from polaris.ocean.model.layer_mass import get_layer_mass

THICKNESS = [[10.0, 20.0, 30.0], [5.0, 15.0, 25.0]]


def config_for(model):
    """A config with nothing in it but the model that wrote the file"""
    config = PolarisConfigParser()
    config.add_section('ocean')
    config.set('ocean', 'model', model)
    return config


def dataset_with(variable):
    """A data set holding one mass-like thickness under a given name"""
    return xr.Dataset(
        {variable: (('nCells', 'nVertLevels'), np.array(THICKNESS))}
    )


@pytest.mark.parametrize(
    'model, variable',
    [('omega', 'PseudoThickness'), ('mpas-ocean', 'layerThickness')],
)
def test_the_layer_mass_is_the_reference_density_times_the_thickness(
    model, variable
):
    layer_mass = get_layer_mass(dataset_with(variable), config_for(model))
    rho_sw = get_constant('seawater_density_reference')
    expected = rho_sw * np.array(THICKNESS)
    np.testing.assert_allclose(layer_mass.values, expected)


def test_the_layer_mass_is_labeled_as_a_mass_per_unit_area():
    layer_mass = get_layer_mass(
        dataset_with('PseudoThickness'), config_for('omega')
    )
    assert layer_mass.attrs['units'] == 'kg m-2'
    assert layer_mass.name == 'layerMass'


def test_one_models_thickness_is_not_read_for_the_other():
    """A file of Omega output analyzed as MPAS-Ocean is an error, not a
    silent fallback to whichever thickness happens to be there."""
    with pytest.raises(ValueError, match='has no layerThickness'):
        get_layer_mass(
            dataset_with('PseudoThickness'), config_for('mpas-ocean')
        )


def test_a_missing_thickness_is_reported():
    with pytest.raises(ValueError, match='has no PseudoThickness'):
        get_layer_mass(xr.Dataset(), config_for('omega'))


def test_an_unknown_model_is_reported():
    with pytest.raises(ValueError, match='Unsupported ocean model'):
        get_layer_mass(
            dataset_with('PseudoThickness'), config_for('some-other-model')
        )
