import json
import os

from polaris.analysis import Manifest, find_fragments, publish
from polaris.analysis.publish import MERGED_FILENAME, PLOTS_DIRNAME

SEASONS = ['ANN', 'DJF', 'MAM', 'JJA', 'SON']


def _make_step(work_dir, step_name, subdir, seasons=None, years=(21, 40)):
    """A step directory holding maps of temperature and its fragment."""
    if seasons is None:
        seasons = SEASONS
    step_path = os.path.join(work_dir, subdir)
    os.makedirs(step_path, exist_ok=True)
    manifest = Manifest(step_name=step_name)
    for season in seasons:
        plot = f'temperature_{season}_-100m.png'
        data = f'temperature_{season}_-100m.nc'
        for filename in (plot, data):
            with open(os.path.join(step_path, filename), 'w') as out:
                out.write(f'{subdir}/{filename}')
        manifest.add(
            plot=plot,
            data=data,
            group='climatology_maps',
            gallery='temperature',
            title=f'Potential temperature at 100 m, {season}',
            field='temperature',
            season=season,
            reduction='-100m',
            start_year=years[0],
            end_year=years[1],
        )
    manifest.write(step_path)
    return step_path


def _merged(output_path):
    with open(os.path.join(output_path, MERGED_FILENAME)) as data:
        return json.load(data)['products']


def test_fragments_are_found_and_sorted(tmp_path):
    work_dir = str(tmp_path / 'work')
    _make_step(work_dir, 'maps', 'climatology_maps/0021-0040/temperature')
    _make_step(work_dir, 'maps', 'climatology_maps/0001-0010/temperature')
    fragments = find_fragments(work_dir)
    assert len(fragments) == 2
    # sorted, so that a publish is reproducible
    assert fragments == sorted(fragments)


def test_products_are_published_by_symlink(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, missing = publish(find_fragments(work_dir), output_path)

    assert missing == []
    assert len(published) == len(SEASONS)

    name = 'climatology_maps_temperature_ANN_-100m_0021-0040.png'
    link = os.path.join(output_path, PLOTS_DIRNAME, name)
    # a link, not a copy: the step remains the one owner of the file
    assert os.path.islink(link)
    assert os.path.realpath(link) == os.path.realpath(
        os.path.join(step_path, 'temperature_ANN_-100m.png')
    )


def test_the_published_name_carries_the_facets(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    _make_step(work_dir, 'maps', 'climatology_maps/0021-0040/temperature')

    publish(find_fragments(work_dir), output_path)
    names = sorted(os.listdir(os.path.join(output_path, PLOTS_DIRNAME)))

    assert 'climatology_maps_temperature_ANN_-100m_0021-0040.png' in names
    assert 'climatology_maps_temperature_ANN_-100m_0021-0040.nc' in names


def test_two_ranges_coexist(tmp_path):
    """The range is in the name, so a new range never clobbers an old one."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    _make_step(
        work_dir,
        'maps',
        'climatology_maps/0021-0040/temperature',
        seasons=['ANN'],
        years=(21, 40),
    )
    _make_step(
        work_dir,
        'maps',
        'climatology_maps/0001-0010/temperature',
        seasons=['ANN'],
        years=(1, 10),
    )

    published, _ = publish(find_fragments(work_dir), output_path)
    assert len(published) == 2

    names = sorted(os.listdir(os.path.join(output_path, PLOTS_DIRNAME)))
    assert 'climatology_maps_temperature_ANN_-100m_0001-0010.png' in names
    assert 'climatology_maps_temperature_ANN_-100m_0021-0040.png' in names


def test_the_merged_manifest_names_every_product(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    _make_step(work_dir, 'maps', 'climatology_maps/0021-0040/temperature')

    published, _ = publish(find_fragments(work_dir), output_path)
    merged = _merged(output_path)

    assert merged == published
    # the merged entry points at the published path, not the step's
    first = merged[0]
    assert first['plot'] == os.path.join(
        PLOTS_DIRNAME, 'climatology_maps_temperature_ANN_-100m_0021-0040.png'
    )
    assert first['step'] == 'maps'
    # and it still carries the facets that identify the product
    assert first['season'] == 'ANN'
    assert first['gallery'] == 'temperature'


def test_order_is_preserved_through_the_merge(tmp_path):
    """A gallery reads ANN, DJF, ... because the step plotted them so."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    _make_step(work_dir, 'maps', 'climatology_maps/0021-0040/temperature')

    published, _ = publish(find_fragments(work_dir), output_path)
    assert [entry['season'] for entry in published] == SEASONS


def test_a_missing_file_is_reported_not_silently_omitted(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )
    os.remove(os.path.join(step_path, 'temperature_DJF_-100m.png'))

    published, missing = publish(find_fragments(work_dir), output_path)

    assert len(missing) == 1
    assert missing[0].endswith('temperature_DJF_-100m.png')
    # the manifest defines the published set, so the absent one is not in it
    assert len(published) == len(SEASONS) - 1
    assert 'DJF' not in [entry['season'] for entry in published]


def test_publishing_twice_replaces_the_links(tmp_path):
    """Re-publishing an analysis must not fail on the links it left."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    _make_step(work_dir, 'maps', 'climatology_maps/0021-0040/temperature')

    publish(find_fragments(work_dir), output_path)
    published, missing = publish(find_fragments(work_dir), output_path)

    assert missing == []
    assert len(published) == len(SEASONS)


def test_a_product_with_no_data_file_publishes_its_plot(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = os.path.join(work_dir, 'moc/0021-0040')
    os.makedirs(step_path)
    with open(os.path.join(step_path, 'moc.png'), 'w') as out:
        out.write('moc')
    manifest = Manifest(step_name='moc')
    manifest.add(
        plot='moc.png', group='moc', gallery='moc', title='Global MOC'
    )
    manifest.write(step_path)

    published, missing = publish(find_fragments(work_dir), output_path)

    assert missing == []
    assert len(published) == 1
    # no range facets, so no range in the name
    assert published[0]['plot'] == os.path.join(PLOTS_DIRNAME, 'moc_moc.png')
    assert published[0]['data'] is None
