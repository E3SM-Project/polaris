import numpy as np
import pytest
import xarray as xr

from polaris.tasks.e3sm.init.component_inputs.maps import (
    CULLED_MESH_SUFFIXES,
    base_to_culled_maps,
    map_base_to_culled,
)

# A base mesh with room for elements to be left off a culled mesh, and
# forward maps that keep a scattered subset of it rather than a leading run,
# so that an off-by-one or an unsorted scatter cannot pass by accident.
BASE_SIZES = {'nCells': 6, 'nEdges': 8, 'nVertices': 5}

KEPT = {
    'Cell': [4, 0, 3],
    'Edge': [7, 2, 5, 1],
    'Vertex': [2],
}


def _forward_map(kept=None):
    """A culled-to-base map dataset from the kept base indices."""
    if kept is None:
        kept = KEPT
    return xr.Dataset(
        {
            f'mapCulledToBase{element}': (
                _culled_dim(element),
                np.array(indices, dtype=np.int32),
            )
            for element, indices in kept.items()
        }
    )


def _culled_dim(element):
    return {'Cell': 'nCells', 'Edge': 'nEdges', 'Vertex': 'nVertices'}[element]


def test_present_elements_are_one_based_and_absent_ones_are_zero():
    ds = map_base_to_culled(_forward_map(), 'ocean', BASE_SIZES)

    # base cells 4, 0 and 3 became culled cells 0, 1 and 2, so they carry the
    # one-based 1, 2 and 3; the rest are not on the culled mesh
    assert list(ds.mapBaseToOceanCell.values) == [2, 0, 0, 3, 1, 0]
    assert list(ds.mapBaseToOceanEdge.values) == [0, 4, 2, 0, 0, 3, 0, 1]
    assert list(ds.mapBaseToOceanVertex.values) == [0, 0, 1, 0, 0]


@pytest.mark.parametrize('element', ['Cell', 'Edge', 'Vertex'])
def test_the_map_round_trips_with_the_forward_map(element):
    """
    mapBaseTo*[mapCulledToBase*[i]] == i + 1 for every element of the culled
    mesh.  This is the property that makes the inverse usable: follow it back
    through the forward map and you land where you started.
    """
    ds_forward = _forward_map()
    ds = map_base_to_culled(ds_forward, 'ocean', BASE_SIZES)

    forward = ds_forward[f'mapCulledToBase{element}'].values
    inverse = ds[f'mapBaseToOcean{element}'].values
    assert list(inverse[forward]) == list(range(1, forward.size + 1))


def test_the_maps_are_dimensioned_by_the_base_mesh():
    """
    Not by the culled mesh, which is what the forward maps are dimensioned by
    and the easiest thing to get backwards.
    """
    ds = map_base_to_culled(_forward_map(), 'ocean', BASE_SIZES)
    for element, dim in [
        ('Cell', 'nCells'),
        ('Edge', 'nEdges'),
        ('Vertex', 'nVertices'),
    ]:
        field = ds[f'mapBaseToOcean{element}']
        assert field.dims == (dim,)
        assert field.sizes[dim] == BASE_SIZES[dim]


def test_the_long_name_records_the_one_based_convention():
    """
    The upstream mapCulledToBase* fields are zero-based and these are not, so
    a reader who checks only the field name would get it wrong.
    """
    ds = map_base_to_culled(_forward_map(), 'ocean', BASE_SIZES)
    long_name = ds.mapBaseToOceanCell.attrs['long_name']
    assert 'one-based' in long_name
    assert 'ocean' in long_name


def test_all_nine_fields_are_built_and_named_for_their_culled_mesh():
    ds = base_to_culled_maps(
        {prefix: _forward_map() for prefix in CULLED_MESH_SUFFIXES},
        BASE_SIZES,
    )
    assert sorted(ds.data_vars) == sorted(
        f'mapBaseTo{suffix}{element}'
        for suffix in CULLED_MESH_SUFFIXES.values()
        for element in ['Cell', 'Edge', 'Vertex']
    )


def test_a_missing_culled_mesh_is_reported():
    with pytest.raises(ValueError, match='land'):
        base_to_culled_maps(
            {'ocean': _forward_map(), 'ocean_no_cavities': _forward_map()},
            BASE_SIZES,
        )


def test_a_mesh_that_was_culled_to_nothing_maps_to_all_zeros():
    ds = map_base_to_culled(
        _forward_map({'Cell': [], 'Edge': [], 'Vertex': []}),
        'land',
        BASE_SIZES,
    )
    assert not ds.mapBaseToLandCell.values.any()
    assert ds.mapBaseToLandCell.sizes['nCells'] == BASE_SIZES['nCells']


def test_an_index_past_the_end_of_the_base_mesh_raises():
    """
    A forward map from a different, larger mesh.  Without the check it would
    either scatter out of bounds or, worse, wrap and give a wrong answer.
    """
    with pytest.raises(ValueError, match='outside the base mesh'):
        map_base_to_culled(
            _forward_map({'Cell': [0, 6], 'Edge': [0], 'Vertex': [0]}),
            'ocean',
            BASE_SIZES,
        )


def test_a_negative_index_raises():
    with pytest.raises(ValueError, match='outside the base mesh'):
        map_base_to_culled(
            _forward_map({'Cell': [0, -1], 'Edge': [0], 'Vertex': [0]}),
            'ocean',
            BASE_SIZES,
        )


def test_two_culled_elements_on_one_base_element_raises():
    """
    A cull is a subset, so the forward map is injective.  A repeat means the
    map belongs to a different mesh; the scatter would silently keep only the
    last of the two.
    """
    with pytest.raises(ValueError, match='same base cell'):
        map_base_to_culled(
            _forward_map({'Cell': [2, 2], 'Edge': [0], 'Vertex': [0]}),
            'ocean',
            BASE_SIZES,
        )


def test_a_culled_mesh_larger_than_the_base_mesh_raises():
    """
    Caught before the duplicate check, so that the message points at the size
    mismatch rather than at whichever index happens to repeat.
    """
    with pytest.raises(ValueError, match='only 5'):
        map_base_to_culled(
            _forward_map(
                {'Cell': [0], 'Edge': [0], 'Vertex': [0, 1, 2, 3, 4, 0]}
            ),
            'ocean',
            BASE_SIZES,
        )


def test_an_unknown_culled_mesh_raises():
    with pytest.raises(ValueError, match='not a culled mesh'):
        map_base_to_culled(_forward_map(), 'atmosphere', BASE_SIZES)
