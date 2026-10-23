"""
Render a CF ``units`` attribute for a plot label

CF units follow udunits: factors separated by spaces, each a symbol with an
optional integer exponent, as in ``kg m-2 s-1``.  Matplotlib renders an
exponent only as mathtext, so this turns each exponent into a superscript and
a few symbols into the characters a reader expects, and leaves anything it
does not recognize as it is rather than guessing.

Omega does not yet write one spelling of an exponent (E3SM-Project/Omega#544),
so ``m-2``, ``m^-2``, ``m**-2`` and ``m^{-2}`` are all read, as is ``m/s``.
"""

import re

#: Symbols rendered as something other than themselves.  A dimensionless
#: quantity has no units worth printing, and a degree is a sign rather than
#: a word.
_SYMBOLS = {
    '1': '',
    'dimensionless': '',
    'degC': r'$^\circ$C',
    'degree_C': r'$^\circ$C',
    'degrees_C': r'$^\circ$C',
    'degree_Celsius': r'$^\circ$C',
    'degrees_Celsius': r'$^\circ$C',
    'degree': r'$^\circ$',
    'degrees': r'$^\circ$',
    'degree_north': r'$^\circ$N',
    'degrees_north': r'$^\circ$N',
    'degree_east': r'$^\circ$E',
    'degrees_east': r'$^\circ$E',
}

# a factor is a symbol, or a number such as the 1e6 of a sverdrup, followed
# by an optional integer exponent written any of the ways Omega writes one
_FACTOR = re.compile(
    r'^(?P<symbol>[A-Za-z_%]+|[0-9][0-9.eE+-]*)'
    r'(?:(?:\^|\*\*)?(?P<exponent>\{[+-]?\d+\}|[+-]?\d+))?$'
)


def units_to_mathtext(units):
    """
    Render a CF units string as matplotlib text

    Parameters
    ----------
    units : str
        The ``units`` attribute of a field, e.g. ``kg m-2 s-1``, ``m/s`` or
        ``degree_C``.  A string that is already mathtext, with ``$`` in it,
        is returned as it is.

    Returns
    -------
    text : str
        The units with each exponent as a superscript, e.g.
        ``kg m$^{-2}$ s$^{-1}$``, and a dimensionless quantity as an empty
        string.  A factor that is not recognized is left as it was.
    """
    units = str(units).strip()
    if not units or '$' in units:
        return units

    rendered = []
    # what follows a slash is divided by, so its exponents change sign
    for sign, part in zip(_signs(units), units.split('/'), strict=True):
        for factor in part.strip('()').split():
            rendered.append(_render_factor(factor, sign))
    return ' '.join(text for text in rendered if text)


def _signs(units):
    """The sign of the exponents in each part of a units string split on
    its slashes: the first part is multiplied, every other one divided by"""
    return [1] + [-1] * units.count('/')


def _render_factor(factor, sign):
    """Render one factor, a symbol with an optional integer exponent"""
    match = _FACTOR.match(factor)
    if match is None:
        return factor
    text = _SYMBOLS.get(match.group('symbol'), match.group('symbol'))
    exponent = match.group('exponent')
    if exponent is None:
        power = sign
    else:
        power = sign * int(exponent.strip('{}'))
    if power == 1 or not text:
        return text
    return f'{text}$^{{{power}}}$'
