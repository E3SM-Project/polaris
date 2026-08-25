import xarray as xr


def is_spherical(ds: xr.Dataset, default: bool | None = None) -> bool:
    """
    Whether an MPAS mesh is on a sphere, based on the ``on_a_sphere`` global
    attribute of ``ds``

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with the ``on_a_sphere`` attribute, which MPAS meshes
        always give as ``'YES'`` or ``'NO'``

    default : bool, optional
        The value to return if ``ds`` has no ``on_a_sphere`` attribute.  By
        default, a missing attribute is an error, since a mesh dataset
        without it is invalid and guessing either way leads to silently
        wrong results.  A step assembling a dataset that has not picked up
        the attribute yet may pass an explicit default.

    Returns
    -------
    spherical : bool
        Whether the mesh is on a sphere

    Raises
    ------
    ValueError
        If ``ds`` has no ``on_a_sphere`` attribute and no ``default`` was
        given, or if the attribute is neither ``'YES'`` nor ``'NO'``
    """
    on_a_sphere = ds.attrs.get('on_a_sphere')
    if on_a_sphere is None:
        if default is None:
            raise ValueError(
                'The dataset has no on_a_sphere attribute, so whether the '
                'mesh is on a sphere is unknown.'
            )
        return default
    if on_a_sphere == 'YES':
        return True
    if on_a_sphere == 'NO':
        return False
    raise ValueError(
        f'Unexpected on_a_sphere attribute {on_a_sphere!r}; MPAS meshes use '
        f"'YES' or 'NO'."
    )


def is_planar(ds: xr.Dataset, default: bool | None = None) -> bool:
    """
    Whether an MPAS mesh is planar, based on the ``on_a_sphere`` global
    attribute of ``ds``

    Parameters
    ----------
    ds : xarray.Dataset
        A dataset with the ``on_a_sphere`` attribute, which MPAS meshes
        always give as ``'YES'`` or ``'NO'``

    default : bool, optional
        The value to return if ``ds`` has no ``on_a_sphere`` attribute.  By
        default, a missing attribute is an error; see
        :py:func:`polaris.mesh.info.is_spherical()`.

    Returns
    -------
    planar : bool
        Whether the mesh is planar

    Raises
    ------
    ValueError
        If ``ds`` has no ``on_a_sphere`` attribute and no ``default`` was
        given, or if the attribute is neither ``'YES'`` nor ``'NO'``
    """
    if default is not None:
        default = not default
    return not is_spherical(ds, default=default)
