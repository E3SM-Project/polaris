"""
The mass per unit area of each layer, from the mass-like thickness each model
writes.

This is the one place in Polaris that knows which model wrote a file when the
question is mass.  Omega prognoses pseudo-height and writes
``PseudoThickness``; MPAS-Ocean prognoses geometric thickness and writes
``layerThickness``.  Neither is renamed to the other, because they agree on
the mass per unit area they imply and disagree on the geometry, so a mapping
would hide exactly the distinction that matters.  Analysis therefore never
asks for "the thickness": it asks for a geometry, from ``zInterface``, or for
a mass, from here.
"""

from polaris.constants import get_constant

# The reference density that defines Omega's pseudo-height and is
# MPAS-Ocean's Boussinesq reference density.  It is not a free parameter: it
# is the constant the model itself used, so any other value would make the
# product below something other than a mass per unit area.  Polaris builds
# Omega's p-star vertical coordinate from this same value.
RhoSw = get_constant('seawater_density_reference')

# The mass-like thickness each model writes, under the name it writes it with
MASS_THICKNESS_VARIABLES = {
    'omega': 'PseudoThickness',
    'mpas-ocean': 'layerThickness',
}


def get_layer_mass(ds, config):
    r"""
    Get the mass per unit area of each layer

    For Omega, ``PseudoThickness`` is the layer's extent in pseudo-height
    :math:`\tilde{h}`, and :math:`\rho_0 \tilde{h} = \rho h = \Delta p / g` is
    the layer's mass per unit area exactly, by hydrostatic balance and by the
    definition of pseudo-height.  For MPAS-Ocean, ``layerThickness`` is the
    geometric thickness :math:`h` and the model is Boussinesq, so
    :math:`\rho_0 h` is its mass per unit area.  Neither needs an equation of
    state.

    Parameters
    ----------
    ds : xarray.Dataset
        A data set holding the model's mass-like thickness under the name the
        model writes it with

    config : polaris.config.PolarisConfigParser
        Configuration options, used only for ``[ocean] model``

    Returns
    -------
    layer_mass : xarray.DataArray
        The mass per unit area of each layer, in kg m-2

    Raises
    ------
    ValueError
        If the model is not one Polaris knows, or if the data set does not
        hold that model's mass-like thickness
    """
    model = config.get('ocean', 'model')
    if model not in MASS_THICKNESS_VARIABLES:
        raise ValueError(
            f'Unsupported ocean model: {model}.  The models whose mass-like '
            f'thickness is known are: '
            f'{", ".join(sorted(MASS_THICKNESS_VARIABLES))}.'
        )

    variable = MASS_THICKNESS_VARIABLES[model]
    if variable not in ds:
        raise ValueError(
            f'The data set has no {variable}, which is how {model} writes '
            f'the thickness a mass per unit area is computed from.  A '
            f'mass-weighted integral cannot be formed without it.'
        )

    layer_mass = (RhoSw * ds[variable]).rename('layerMass')
    layer_mass.attrs = dict(
        units='kg m-2',
        long_name='mass per unit area of each layer',
    )
    return layer_mass
