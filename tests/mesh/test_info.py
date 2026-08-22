import pytest
import xarray as xr

from polaris.mesh.info import is_planar, is_spherical


def _mesh(on_a_sphere=None):
    attrs = {} if on_a_sphere is None else dict(on_a_sphere=on_a_sphere)
    return xr.Dataset(attrs=attrs)


@pytest.mark.parametrize(
    'on_a_sphere,spherical',
    [('YES', True), ('NO', False)],
)
def test_is_spherical(on_a_sphere, spherical):
    ds = _mesh(on_a_sphere)
    assert is_spherical(ds) == spherical
    assert is_planar(ds) == (not spherical)


def test_is_spherical_raises_without_attribute():
    """A mesh dataset without the attribute is invalid, and guessing either
    way leads to silently wrong results."""
    with pytest.raises(ValueError, match='on_a_sphere'):
        is_spherical(_mesh())
    with pytest.raises(ValueError, match='on_a_sphere'):
        is_planar(_mesh())


@pytest.mark.parametrize('default', [True, False])
def test_is_spherical_default_without_attribute(default):
    """A caller that knows a missing attribute is not an error, such as a
    step assembling a dataset, can say what to assume."""
    assert is_spherical(_mesh(), default=default) == default
    assert is_planar(_mesh(), default=default) == default


@pytest.mark.parametrize('on_a_sphere', ['yes', 'NO ', '', 'MAYBE'])
def test_is_spherical_raises_on_unexpected_value(on_a_sphere):
    """MPAS meshes always give 'YES' or 'NO', so anything else means the
    file is garbled rather than planar."""
    with pytest.raises(ValueError, match='Unexpected on_a_sphere'):
        is_spherical(_mesh(on_a_sphere))
    with pytest.raises(ValueError, match='Unexpected on_a_sphere'):
        is_planar(_mesh(on_a_sphere))


@pytest.mark.parametrize('default', [True, False])
def test_is_spherical_default_ignored_when_attribute_present(default):
    """The default only applies to a missing attribute, never to one that
    is present."""
    assert is_spherical(_mesh('YES'), default=default)
    assert is_planar(_mesh('NO'), default=default)
