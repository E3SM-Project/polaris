import os

import pytest
from PIL import Image

from polaris.analysis import publish
from polaris.analysis.thumbnail import (
    THUMBNAILS_DIRNAME,
    make_thumbnail,
    thumbnail_name,
)
from tests.analysis.test_publish import (
    SEASONS,
    _fragments,
    _make_step,
    write_plot,
)


def test_a_thumbnail_fits_inside_the_box_in_both_dimensions(tmp_path):
    """
    A width rule would make a tall plot taller than the box and several
    times the bytes of a wide one; a bounding box does not.
    """
    box = (320, 240)
    landscape = write_plot(str(tmp_path / 'wide.png'), size=(1600, 900))
    portrait = write_plot(str(tmp_path / 'tall.png'), size=(900, 1600))

    for source, name in ((landscape, 'wide.jpg'), (portrait, 'tall.jpg')):
        target = str(tmp_path / name)
        assert make_thumbnail(source, target, size=box)
        with Image.open(target) as thumbnail:
            width, height = thumbnail.size
        assert width <= box[0]
        assert height <= box[1]

    with Image.open(str(tmp_path / 'wide.jpg')) as wide:
        assert wide.size == (320, 180)
    with Image.open(str(tmp_path / 'tall.jpg')) as tall:
        assert tall.size == (135, 240)


def test_a_thumbnail_is_far_smaller_than_its_plot(tmp_path):
    """
    Thumbnails exist to make a page loadable over a throttled link, so the
    saving has to be an order of magnitude, not a few percent.
    """
    source = write_plot(str(tmp_path / 'plot.png'), size=(1600, 900))
    target = str(tmp_path / 'plot.jpg')
    make_thumbnail(source, target)
    assert os.path.getsize(target) * 10 < os.path.getsize(source)


def test_transparency_is_flattened_onto_white(tmp_path):
    """Without this, a JPEG thumbnail of an RGBA plot comes out black."""
    source = str(tmp_path / 'plot.png')
    Image.new('RGBA', (400, 300), (255, 255, 255, 0)).save(source)
    target = str(tmp_path / 'plot.jpg')
    make_thumbnail(source, target)

    with Image.open(target) as thumbnail:
        assert thumbnail.mode == 'RGB'
        assert thumbnail.getpixel((0, 0)) == (255, 255, 255)


def test_an_up_to_date_thumbnail_is_not_rendered_again(tmp_path):
    """Adding one product must cost one thumbnail, not all of them."""
    source = write_plot(str(tmp_path / 'plot.png'))
    target = str(tmp_path / 'plot.jpg')

    assert make_thumbnail(source, target) is True
    assert make_thumbnail(source, target) is False

    # touching the plot makes it stale again
    os.utime(source, (os.path.getmtime(target) + 10,) * 2)
    assert make_thumbnail(source, target) is True


def test_webp_is_smaller_than_jpeg(tmp_path):
    source = write_plot(str(tmp_path / 'plot.png'), size=(1600, 900))
    as_jpeg = str(tmp_path / 'plot.jpg')
    as_webp = str(tmp_path / 'plot.webp')
    make_thumbnail(source, as_jpeg, image_format='jpeg')
    make_thumbnail(source, as_webp, image_format='webp')
    assert os.path.getsize(as_webp) <= os.path.getsize(as_jpeg)


def test_the_name_follows_the_format():
    assert thumbnail_name('a_b_0021-0040.png') == 'a_b_0021-0040.jpg'
    assert thumbnail_name('a_b_0021-0040.png', 'webp') == 'a_b_0021-0040.webp'


def test_an_unsupported_format_is_refused(tmp_path):
    source = write_plot(str(tmp_path / 'plot.png'))
    with pytest.raises(ValueError, match='Unsupported thumbnail format'):
        make_thumbnail(source, str(tmp_path / 'plot.gif'), image_format='gif')


def test_a_mismatched_suffix_is_refused(tmp_path):
    source = write_plot(str(tmp_path / 'plot.png'))
    with pytest.raises(ValueError, match='must end in ".jpg"'):
        make_thumbnail(source, str(tmp_path / 'plot.webp'))


def test_publishing_renders_a_thumbnail_for_every_plot(tmp_path):
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir, 'maps', 'climatology_maps/0021-0040/temperature'
    )

    published, _ = publish(_fragments(step_path), output_path)

    thumbnails = sorted(
        os.listdir(os.path.join(output_path, THUMBNAILS_DIRNAME))
    )
    assert len(thumbnails) == len(SEASONS)
    assert 'climatology_maps_temperature_ANN_-100m_0021-0040.jpg' in thumbnails

    # and the merged manifest points at it, so a gallery needs nothing else
    for entry in published:
        assert entry['thumbnail'].startswith(f'{THUMBNAILS_DIRNAME}/')
        assert os.path.exists(os.path.join(output_path, entry['thumbnail']))


def test_thumbnails_are_files_not_symlinks(tmp_path):
    """They are generated here, so nothing upstream owns them."""
    work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step_path = _make_step(
        work_dir,
        'maps',
        'climatology_maps/0021-0040/temperature',
        seasons=['ANN'],
    )

    published, _ = publish(_fragments(step_path), output_path)
    thumbnail = os.path.join(output_path, published[0]['thumbnail'])
    assert not os.path.islink(thumbnail)
