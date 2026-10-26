import ast
import operator
import os
import warnings
from collections.abc import Callable
from importlib.resources import open_text

from ruamel.yaml import YAML

# the arithmetic that a PCD ``formula`` may use, as in the PCD's own
# ``tools/generate_source.py``
_BINARY_OPERATORS: dict[type, Callable[[float, float], float]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
}

_UNARY_OPERATORS: dict[type, Callable[[float], float]] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def get_constant(name):
    """
    Get a constant from the Physical Constants Dictionary (PCD).

    Parameters
    ----------
    name : str
        The name of the constant to retrieve.

    Returns
    -------
    value: float or None
        The value of the constant or None if not found.
    """
    return PCD_CONSTANTS.get(name, None)


def get_pcd_version():
    """
    Get the PCD version from Polaris' packaged ``pcd.yaml``.

    Returns
    -------
    version : str
        The PCD version.
    """
    return str(
        _get_version_from_pcd_dict(PCD_FULL, 'polaris.constants/pcd.yaml')
    )


def get_pcd_version_from_file(filename):
    """
    Get the PCD version from a ``pcd.yaml`` file.

    Parameters
    ----------
    filename : str
        The path to the PCD YAML file.

    Returns
    -------
    version : str
        The PCD version.
    """
    with open(filename, encoding='utf-8') as f:
        yaml_data = YAML(typ='rt')
        pcd_full = yaml_data.load(f.read())

    return str(_get_version_from_pcd_dict(pcd_full, filename))


def check_pcd_version_matches_branch(branch, model):
    """
    Check that the PCD version in Polaris matches the version in a branch.

    Parameters
    ----------
    branch : str
        The path to the base of an E3SM or Omega branch containing
        ``share/pcd.yaml``.

    model : str
        The model being set up (e.g. ``'mpas-ocean'`` or ``'omega'``).

    Raises
    ------
    ValueError
        If the PCD version in Polaris and the branch are not identical.
    """
    branch = os.path.abspath(branch)
    branch_pcd_path = os.path.join(branch, 'share', 'pcd.yaml')
    if not os.path.exists(branch_pcd_path):
        warnings.warn(
            f'Could not check PCD version for model {model} because '
            f'`share/pcd.yaml` was not found at {branch_pcd_path}. '
            f'Skipping PCD version check for this branch.',
            stacklevel=2,
        )
        return

    polaris_version = get_pcd_version()
    branch_version = get_pcd_version_from_file(branch_pcd_path)

    if polaris_version != branch_version:
        raise ValueError(
            f'PCD version mismatch for model {model}: Polaris has '
            f'{polaris_version} but branch {branch} has {branch_version}. '
            f'Please use matching PCD versions.'
        )


def _parse_pcd():
    """Parse constants from the Physical Constants Dictonary (PCD) yaml file"""

    with open_text('polaris.constants', 'pcd.yaml') as f:
        yaml_data = YAML(typ='rt')
        pcd_full = yaml_data.load(f.read())

    entries = {}
    # constants are within the physical_constants_dictionary and set sections
    sets = pcd_full['physical_constants_dictionary']['set']
    # they may be within any of the available subsections
    for set_dict in sets:
        for entry in next(iter(set_dict.values()))['entries']:
            entries[entry['name']] = entry

    return pcd_full, _evaluate_constants(entries)


def _evaluate_constants(entries):
    """
    Get the value of each PCD constant, evaluating any that are defined by a
    ``formula`` rather than a ``value``

    Parameters
    ----------
    entries : dict
        PCD entries, keyed by constant name

    Returns
    -------
    pcd_constants : dict
        The value of each constant, keyed by name
    """
    pcd_constants: dict = {}
    for name in entries:
        _evaluate_constant(name, entries, pcd_constants, stack=[])
    return pcd_constants


def _evaluate_constant(name, entries, pcd_constants, stack):
    """
    Get the value of a PCD constant, first evaluating any constants its
    formula references
    """
    if name in pcd_constants:
        return pcd_constants[name]

    if name in stack:
        cycle = ' -> '.join(stack + [name])
        raise ValueError(f'Circular dependency between PCD formulas: {cycle}')

    entry = entries[name]
    if 'formula' in entry:
        formula = str(entry['formula'])
        tree = ast.parse(formula, mode='eval')
        value = _evaluate_node(
            tree.body, entries, pcd_constants, stack=stack + [name]
        )
    else:
        value = entry['value']

    pcd_constants[name] = value
    return value


def _evaluate_node(node, entries, pcd_constants, stack):
    """
    Evaluate a node of a PCD formula in double precision, allowing only
    arithmetic on numbers and other PCD constants
    """
    name = stack[-1]
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate_node(node.left, entries, pcd_constants, stack)
        right = _evaluate_node(node.right, entries, pcd_constants, stack)
        return _BINARY_OPERATORS[type(node.op)](left, right)

    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        operand = _evaluate_node(node.operand, entries, pcd_constants, stack)
        return _UNARY_OPERATORS[type(node.op)](operand)

    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return float(node.value)

    if isinstance(node, ast.Name):
        if node.id not in entries:
            raise ValueError(
                f'The PCD formula for {name} references unknown constant '
                f'{node.id}.'
            )
        value = _evaluate_constant(node.id, entries, pcd_constants, stack)
        return float(value)

    raise ValueError(
        f'The PCD formula for {name} uses unsupported syntax: '
        f'{ast.unparse(node)}'
    )


def _get_version_from_pcd_dict(pcd_full, source):
    """Get ``physical_constants_dictionary/version_number`` from YAML data."""
    if not isinstance(pcd_full, dict):
        raise ValueError(f'Invalid PCD format in {source}: expected a map.')

    if 'physical_constants_dictionary' not in pcd_full:
        raise ValueError(
            f'Invalid PCD format in {source}: missing '
            f'"physical_constants_dictionary".'
        )

    pcd_dict = pcd_full['physical_constants_dictionary']
    if not isinstance(pcd_dict, dict) or 'version_number' not in pcd_dict:
        raise ValueError(
            f'Invalid PCD format in {source}: missing '
            f'"physical_constants_dictionary/version_number".'
        )

    return pcd_dict['version_number']


# parsed full dictionary and constants for quick lookup
PCD_FULL, PCD_CONSTANTS = _parse_pcd()
