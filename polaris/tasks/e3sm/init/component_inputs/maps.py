"""
Maps from base-mesh elements to the culled meshes derived from them.

The cull step already writes the forward direction -- ``mapCulledToBase*``,
zero-based base indices dimensioned by the culled mesh -- so these are built by
inverting it rather than by recomputing.  The forward maps came from a
nearest-element query far more expensive than a scatter, and inverting
guarantees that the two directions agree.

Like :py:mod:`~polaris.tasks.e3sm.init.component_inputs.names`, this module is
dependency-light: it takes and returns datasets and opens no file, so the
inversion is unit testable without a work directory.
"""

import numpy as np
import xarray as xr

#: The culled-mesh prefix the cull step writes, and the name fragment the
#: corresponding map fields carry.
CULLED_MESH_SUFFIXES = {
    'ocean': 'Ocean',
    'ocean_no_cavities': 'OceanNoCavities',
    'land': 'Land',
}

#: How each culled mesh is described in a map field's ``long_name``.
_MESH_DESCRIPTIONS = {
    'ocean': 'the culled ocean mesh',
    'ocean_no_cavities': 'the culled ocean mesh without ice-shelf cavities',
    'land': 'the culled land mesh',
}

#: The base-mesh dimension and field-name fragment of each element type.
_ELEMENTS = (('nCells', 'Cell'), ('nEdges', 'Edge'), ('nVertices', 'Vertex'))


def base_to_culled_maps(
    ds_maps_culled_to_base: dict[str, xr.Dataset], sizes: dict[str, int]
) -> xr.Dataset:
    """
    All nine base-to-culled index maps, one per culled mesh and element type.

    Parameters
    ----------
    ds_maps_culled_to_base : dict of {str: xarray.Dataset}
        The cull step's forward maps, keyed by culled-mesh prefix.  Must cover
        every prefix in :py:data:`CULLED_MESH_SUFFIXES`.

    sizes : dict of {str: int}
        The ``nCells``, ``nEdges`` and ``nVertices`` of the *base* mesh.

    Returns
    -------
    xarray.Dataset
        The nine ``mapBaseTo{Ocean,OceanNoCavities,Land}{Cell,Edge,Vertex}``
        fields.

    Raises
    ------
    ValueError
        If a prefix is missing, or if a forward map fails the checks described
        in :py:func:`map_base_to_culled`.
    """
    missing = set(CULLED_MESH_SUFFIXES) - set(ds_maps_culled_to_base)
    if missing:
        raise ValueError(
            'No culled-to-base map was given for: '
            f'{", ".join(sorted(missing))}'
        )

    ds_out = xr.Dataset()
    for prefix in CULLED_MESH_SUFFIXES:
        ds_out = ds_out.merge(
            map_base_to_culled(
                ds_map_culled_to_base=ds_maps_culled_to_base[prefix],
                prefix=prefix,
                sizes=sizes,
            )
        )
    return ds_out


def map_base_to_culled(
    ds_map_culled_to_base: xr.Dataset, prefix: str, sizes: dict[str, int]
) -> xr.Dataset:
    """
    Invert one culled mesh's forward map into base-to-culled index fields.

    The result is dimensioned by the *base* mesh and is one-based, with zero
    meaning "this element is not on that culled mesh".  That matches
    ``cellsOnCell`` and the other MPAS index fields, and differs from the
    zero-based upstream ``mapCulledToBase*``, which is why each field's
    ``long_name`` records the convention.

    Two properties of the input are checked rather than trusted: every value
    is a valid base index, and no base index appears twice.  Both hold for a
    map genuinely derived from this base mesh, so a violation means a stale
    file from a different mesh -- which would otherwise scatter into a
    plausible-looking wrong answer instead of failing.

    Parameters
    ----------
    ds_map_culled_to_base : xarray.Dataset
        The cull step's ``{prefix}_map_culled_to_base.nc``, with
        ``mapCulledToBase{Cell,Edge,Vertex}``.

    prefix : str
        The culled-mesh prefix, one of :py:data:`CULLED_MESH_SUFFIXES`.

    sizes : dict of {str: int}
        The ``nCells``, ``nEdges`` and ``nVertices`` of the *base* mesh.

    Returns
    -------
    xarray.Dataset
        The three ``mapBaseTo<Mesh>{Cell,Edge,Vertex}`` fields.

    Raises
    ------
    ValueError
        If ``prefix`` is not a culled mesh, or if a forward map contains an
        index outside the base mesh or maps two culled elements onto the same
        base element.
    """
    if prefix not in CULLED_MESH_SUFFIXES:
        raise ValueError(
            f'{prefix!r} is not a culled mesh.  Expected one of '
            f'{", ".join(CULLED_MESH_SUFFIXES)}.'
        )
    suffix = CULLED_MESH_SUFFIXES[prefix]

    ds_out = xr.Dataset()
    for dim, element in _ELEMENTS:
        forward = ds_map_culled_to_base[f'mapCulledToBase{element}'].values
        inverse = _invert(
            forward=forward,
            size=sizes[dim],
            prefix=prefix,
            element=element,
        )
        field = xr.DataArray(data=inverse, dims=(dim,))
        field.attrs['long_name'] = (
            f'one-based index on {_MESH_DESCRIPTIONS[prefix]} of each '
            f'base-mesh {element.lower()}, or 0 where the {element.lower()} '
            f'is not on that mesh'
        )
        ds_out[f'mapBaseTo{suffix}{element}'] = field

    return ds_out


def _invert(
    forward: np.ndarray, size: int, prefix: str, element: str
) -> np.ndarray:
    """
    Scatter a zero-based forward map into a one-based inverse of ``size``.
    """
    name = f'{prefix}_map_culled_to_base.nc'
    if forward.size > size:
        raise ValueError(
            f'{name} maps {forward.size} culled {element.lower()}s onto a '
            f'base mesh with only {size}.  This map is for a different mesh.'
        )
    if forward.size > 0:
        if forward.min() < 0 or forward.max() >= size:
            raise ValueError(
                f'mapCulledToBase{element} in {name} contains indices outside '
                f'the base mesh, which has {size} {element.lower()}s.  This '
                f'map is for a different mesh.'
            )
        if np.unique(forward).size != forward.size:
            raise ValueError(
                f'mapCulledToBase{element} in {name} maps two culled '
                f'{element.lower()}s onto the same base {element.lower()}.  '
                f'This map is for a different mesh.'
            )

    inverse = np.zeros(size, dtype=np.int32)
    inverse[forward] = np.arange(1, forward.size + 1, dtype=np.int32)
    return inverse
