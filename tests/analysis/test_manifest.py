import json
import os

import pytest

from polaris.analysis import Manifest, Product, read_fragment
from polaris.analysis.manifest import FRAGMENT_FILENAME

SEASONS = ['ANN', 'DJF', 'MAM', 'JJA', 'SON']


def _manifest(step_name='climatology_maps'):
    """A manifest holding one map per season, added in the plotted order."""
    manifest = Manifest(step_name=step_name)
    for season in SEASONS:
        manifest.add(
            plot=f'temperature_{season}_-100m.png',
            data=f'temperature_{season}_-100m.nc',
            group='climatology_maps',
            gallery='temperature',
            title=f'Potential temperature at 100 m, {season}',
            field='temperature',
            season=season,
            reduction='-100m',
            start_year=21,
            end_year=40,
        )
    return manifest


def test_add_records_the_reserved_keys_and_the_facets():
    product = _manifest().products[0]
    assert product.plot == 'temperature_ANN_-100m.png'
    assert product.data == 'temperature_ANN_-100m.nc'
    assert product.group == 'climatology_maps'
    assert product.gallery == 'temperature'
    assert product.title == 'Potential temperature at 100 m, ANN'
    # everything else is a facet, and nothing reserved leaks into them
    assert product.facets == {
        'field': 'temperature',
        'season': 'ANN',
        'reduction': '-100m',
        'start_year': 21,
        'end_year': 40,
    }


def test_products_keep_the_order_they_were_added_in():
    """A gallery reads ANN, DJF, ... because the step plotted them so."""
    manifest = _manifest()
    assert [product.facets['season'] for product in manifest.products] == (
        SEASONS
    )


def test_a_fragment_round_trips(tmp_path):
    written = _manifest()
    filename = written.write(str(tmp_path))
    assert filename == os.path.join(str(tmp_path), FRAGMENT_FILENAME)

    read = read_fragment(filename)
    assert read.step_name == written.step_name
    assert [product.to_dict() for product in read.products] == [
        product.to_dict() for product in written.products
    ]


def test_a_fragment_can_be_read_from_its_directory(tmp_path):
    """The collector finds fragments by directory, not by file name."""
    _manifest().write(str(tmp_path))
    assert len(read_fragment(str(tmp_path)).products) == len(SEASONS)


def test_the_fragment_on_disk_is_json_a_reader_can_follow(tmp_path):
    _manifest().write(str(tmp_path))
    with open(os.path.join(str(tmp_path), FRAGMENT_FILENAME)) as data:
        contents = json.load(data)
    assert contents['step'] == 'climatology_maps'
    assert len(contents['products']) == len(SEASONS)
    first = contents['products'][0]
    # the reserved keys come first, in a fixed order, so a fragment diffs
    # usefully between two analyses
    assert list(first)[:5] == ['plot', 'data', 'group', 'gallery', 'title']


def test_a_product_with_no_data_file_is_allowed(tmp_path):
    manifest = Manifest(step_name='moc')
    manifest.add(
        plot='moc.png',
        group='moc',
        gallery='moc',
        title='Global MOC',
    )
    manifest.write(str(tmp_path))
    assert read_fragment(str(tmp_path)).products[0].data is None


@pytest.mark.parametrize('missing', ['plot', 'group', 'gallery', 'title'])
def test_a_product_needs_its_reserved_keys(missing):
    kwargs = dict(
        plot='temperature_ANN_-100m.png',
        group='climatology_maps',
        gallery='temperature',
        title='Potential temperature at 100 m, ANN',
    )
    kwargs[missing] = ''
    with pytest.raises(ValueError, match=f'non-empty "{missing}"'):
        Product(**kwargs)


def test_a_facet_cannot_shadow_a_reserved_key():
    """The reserved names are ordinary parameters, so Python rejects this."""
    facets = {'gallery': 'other'}
    with pytest.raises(TypeError, match='gallery'):
        Manifest(step_name='climatology_maps').add(
            plot='temperature_ANN_-100m.png',
            group='climatology_maps',
            gallery='temperature',
            title='Potential temperature at 100 m, ANN',
            **facets,
        )


def test_two_products_cannot_share_a_plot():
    """Each plot is one product, so a repeated name is a step's mistake."""
    manifest = _manifest()
    with pytest.raises(ValueError, match='two products'):
        manifest.add(
            plot='temperature_ANN_-100m.png',
            group='climatology_maps',
            gallery='temperature',
            title='A second product claiming the same plot',
        )


def test_an_incomplete_entry_is_reported(tmp_path):
    filename = os.path.join(str(tmp_path), FRAGMENT_FILENAME)
    with open(filename, 'w') as out:
        json.dump({'step': 'moc', 'products': [{'plot': 'moc.png'}]}, out)
    with pytest.raises(ValueError, match='missing group, gallery, title'):
        read_fragment(filename)


def test_a_fragment_without_products_is_reported(tmp_path):
    filename = os.path.join(str(tmp_path), FRAGMENT_FILENAME)
    with open(filename, 'w') as out:
        json.dump({'step': 'moc'}, out)
    with pytest.raises(ValueError, match='no "products"'):
        read_fragment(filename)
