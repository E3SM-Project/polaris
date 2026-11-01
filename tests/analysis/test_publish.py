import json
import logging
import os

import numpy as np
from PIL import Image

from polaris.analysis import Manifest, publish
from polaris.analysis.manifest import FRAGMENT_FILENAME
from polaris.analysis.publish import MERGED_FILENAME, PLOTS_DIRNAME

SEASONS = ['ANN', 'DJF', 'MAM', 'JJA', 'SON']


def write_plot(filename, size=(160, 90)):
    """
    A stand-in plot: a real RGBA image with structure in it.

    The structure matters.  A flat colour compresses to almost nothing as
    PNG, so a thumbnail of it cannot be much smaller and a size comparison
    against it would prove nothing.  A field with both smooth variation and
    fine detail behaves like the contour maps this suite actually publishes.
    """
    width, height = size
    y, x = np.mgrid[0:height, 0:width]
    field = np.sin(x / 23.0) * np.cos(y / 17.0) + 0.35 * np.sin(
        x / 3.0 + y / 5.0
    )
    band = ((field - field.min()) / np.ptp(field) * 255).astype(np.uint8)
    rgba = np.dstack(
        [
            band,
            np.roll(band, 40, axis=1),
            255 - band,
            np.full_like(band, 255),
        ]
    )
    Image.fromarray(rgba, mode='RGBA').save(filename)
    return filename


def _make_step(
    work_dir,
    step_name,
    subdir,
    seasons=None,
    years=(21, 40),
    plot_size=(160, 90),
):
    """A step directory holding maps of temperature and its fragment."""
    if seasons is None:
        seasons = SEASONS
    step_path = os.path.join(work_dir, subdir)
    os.makedirs(step_path, exist_ok=True)
    manifest = Manifest(step_name=step_name)
    for season in seasons:
        plot = f'temperature_{season}_-100m.png'
        data = f'temperature_{season}_-100m.nc'
        write_plot(os.path.join(step_path, plot), size=plot_size)
        with open(os.path.join(step_path, data), 'w') as out:
            out.write(f'{subdir}/{data}')
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


def _fragments(*step_paths):
    """
    The fragments the publish step declares, one per step that made products.

    The paths are known without looking for them: the filename is a constant
    and each step's work directory is fixed when the suite is built.
    """
    return [
        os.path.join(step_path, FRAGMENT_FILENAME) for step_path in step_paths
    ]


def _read(filename):
    with open(filename, 'rb') as data:
        return data.read()


def _merged(output_path):
    with open(os.path.join(output_path, MERGED_FILENAME)) as data:
        return json.load(data)['products']


def test_a_fragment_that_was_never_written_is_reported(tmp_path):
    """Reported rather than raising, so this is usable on a list nothing has
    checked.  The publish step does not rely on it: its fragments are
    declared inputs, and a missing one stops it before it runs."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )
    silent = os.path.join(work_dir, 'moc/0021-0040')
    os.makedirs(silent)

    published, missing = publish(_fragments(step_path, silent), output_path)

    assert len(published) == len(SEASONS)
    assert missing == [os.path.join(silent, FRAGMENT_FILENAME)]


def test_plots_are_published_by_copy(tmp_path):
    """A copy, not a link, so a web server that cannot read the work
    directory can still serve the plot."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, missing = publish(_fragments(step_path), output_path)

    assert missing == []
    assert len(published) == len(SEASONS)

    name = 'climatology_maps_temperature_ANN_-100m_0021-0040.png'
    copy = os.path.join(output_path, PLOTS_DIRNAME, name)
    assert not os.path.islink(copy)
    assert _read(copy) == _read(
        os.path.join(step_path, 'temperature_ANN_-100m.png')
    )


def test_data_files_are_not_published_by_default(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, missing = publish(_fragments(step_path), output_path)

    assert missing == []
    names = os.listdir(os.path.join(output_path, PLOTS_DIRNAME))
    assert not [name for name in names if name.endswith('.nc')]
    # so the gallery has nothing to link to
    assert all(entry['data'] is None for entry in published)


def test_data_files_are_copied_if_asked(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, _ = publish(_fragments(step_path), output_path, copy_data=True)

    name = 'climatology_maps_temperature_ANN_-100m_0021-0040.nc'
    assert published[0]['data'] == os.path.join(PLOTS_DIRNAME, name)
    copy = os.path.join(output_path, PLOTS_DIRNAME, name)
    assert not os.path.islink(copy)
    assert _read(copy) == _read(
        os.path.join(step_path, 'temperature_ANN_-100m.nc')
    )


def test_the_published_name_carries_the_facets(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    publish(_fragments(step_path), output_path, copy_data=True)
    names = sorted(os.listdir(os.path.join(output_path, PLOTS_DIRNAME)))

    assert 'climatology_maps_temperature_ANN_-100m_0021-0040.png' in names
    assert 'climatology_maps_temperature_ANN_-100m_0021-0040.nc' in names


def test_two_ranges_coexist(tmp_path):
    """The range is in the name, so a new range never clobbers an old one."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    recent = _make_step(
        work_dir,
        'maps',
        'climatology_maps/0021-0040/temperature',
        seasons=['ANN'],
        years=(21, 40),
    )
    earlier = _make_step(
        work_dir,
        'maps',
        'climatology_maps/0001-0010/temperature',
        seasons=['ANN'],
        years=(1, 10),
    )

    published, _ = publish(_fragments(earlier, recent), output_path)
    assert len(published) == 2

    names = sorted(os.listdir(os.path.join(output_path, PLOTS_DIRNAME)))
    assert 'climatology_maps_temperature_ANN_-100m_0001-0010.png' in names
    assert 'climatology_maps_temperature_ANN_-100m_0021-0040.png' in names


def test_a_fragment_reached_through_a_symlink_finds_its_products(tmp_path):
    """The publish step reads its fragments as declared inputs, which are
    symlinks into the steps that wrote them, and a product is named relative
    to the step rather than to the link."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )
    links = os.path.join(work_dir, 'publish', 'fragments')
    os.makedirs(links)
    link = os.path.join(links, 'temperature.json')
    os.symlink(os.path.join(step_path, FRAGMENT_FILENAME), link)

    published, missing = publish([link], output_path)

    assert missing == []
    assert len(published) == len(SEASONS)
    copy = os.path.join(output_path, published[0]['plot'])
    assert _read(copy) == _read(
        os.path.join(step_path, 'temperature_ANN_-100m.png')
    )


def test_the_merged_manifest_names_every_product(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, _ = publish(_fragments(step_path), output_path)
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
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, _ = publish(_fragments(step_path), output_path)
    assert [entry['season'] for entry in published] == SEASONS


def test_a_missing_file_is_reported_not_silently_omitted(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )
    os.remove(os.path.join(step_path, 'temperature_DJF_-100m.png'))

    published, missing = publish(_fragments(step_path), output_path)

    assert len(missing) == 1
    assert missing[0].endswith('temperature_DJF_-100m.png')
    # the manifest defines the published set, so the absent one is not in it
    assert len(published) == len(SEASONS) - 1
    assert 'DJF' not in [entry['season'] for entry in published]


def test_publishing_twice_replaces_the_copies(tmp_path):
    """Re-publishing an analysis must not fail on the copies it left, and
    must pick up a plot that was made again."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    publish(_fragments(step_path), output_path)
    source = os.path.join(step_path, 'temperature_ANN_-100m.png')
    write_plot(source, size=(80, 45))
    # a plot made again within the same second still has a new time
    mtime = os.stat(source).st_mtime_ns + 10**9
    os.utime(source, ns=(mtime, mtime))
    published, missing = publish(_fragments(step_path), output_path)

    assert missing == []
    assert len(published) == len(SEASONS)
    copy = os.path.join(output_path, published[0]['plot'])
    assert _read(copy) == _read(source)


def test_an_unchanged_plot_is_not_copied_again(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, _ = publish(_fragments(step_path), output_path)
    copy = os.path.join(output_path, published[0]['plot'])
    inode = os.stat(copy).st_ino
    publish(_fragments(step_path), output_path)

    assert os.stat(copy).st_ino == inode


def test_links_from_an_earlier_version_are_replaced(tmp_path):
    """Earlier versions published by symlink, and copying through one of
    those would write onto the step's own file."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir,
        'maps',
        'climatology_maps/0021-0040/temperature',
        seasons=['ANN'],
    )
    plots_path = os.path.join(output_path, PLOTS_DIRNAME)
    os.makedirs(plots_path)
    stem = 'climatology_maps_temperature_ANN_-100m_0021-0040'
    for suffix in ['.png', '.nc']:
        os.symlink(
            os.path.join(step_path, f'temperature_ANN_-100m{suffix}'),
            os.path.join(plots_path, f'{stem}{suffix}'),
        )

    publish(_fragments(step_path), output_path)

    assert not os.path.islink(os.path.join(plots_path, f'{stem}.png'))
    # a data file that is no longer published is not left behind
    assert sorted(os.listdir(plots_path)) == [f'{stem}.png']
    assert os.path.exists(os.path.join(step_path, 'temperature_ANN_-100m.nc'))


def test_a_product_with_no_data_file_publishes_its_plot(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = os.path.join(work_dir, 'moc/0021-0040')
    os.makedirs(step_path)
    write_plot(os.path.join(step_path, 'moc.png'))
    manifest = Manifest(step_name='moc')
    manifest.add(
        plot='moc.png', group='moc', gallery='moc', title='Global MOC'
    )
    manifest.write(step_path)

    published, missing = publish(_fragments(step_path), output_path)

    assert missing == []
    assert len(published) == 1
    # no range facets, so no range in the name
    assert published[0]['plot'] == os.path.join(PLOTS_DIRNAME, 'moc_moc.png')
    assert published[0]['data'] is None


def test_a_step_that_published_nothing_is_named_in_the_log(tmp_path, caplog):
    """An empty fragment is an absence in the gallery, so the log is the only
    place the step that wrote it is named at all."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    maps = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )
    quiet = _make_step(work_dir, 'moc', 'moc/0021-0040', seasons=[])

    with caplog.at_level(logging.INFO):
        publish(
            _fragments(maps, quiet),
            output_path,
            logger=logging.getLogger('test_publish'),
        )

    assert f'published {len(SEASONS)} products from 2 manifests' in caplog.text
    assert '1 steps published nothing:' in caplog.text
    assert '  moc' in caplog.text
