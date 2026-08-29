import os
import re

from polaris.analysis import Manifest, generate_site, publish
from polaris.analysis.manifest import FRAGMENT_FILENAME
from polaris.analysis.site import GALLERIES_DIRNAME, INDEX_FILENAME
from tests.analysis.test_publish import SEASONS, write_plot

PROVENANCE = {'polaris version': '1.1.0-alpha.6', 'command': 'polaris serial'}


def _make_step(
    work_dir,
    subdir,
    group='climatology_maps',
    gallery='temperature',
    seasons=None,
    years=(21, 40),
    data=True,
):
    """A step directory holding one gallery of maps, and its fragment"""
    if seasons is None:
        seasons = SEASONS
    step_path = os.path.join(work_dir, subdir)
    os.makedirs(step_path, exist_ok=True)
    manifest = Manifest(step_name=subdir)
    for season in seasons:
        plot = f'{gallery}_{season}.png'
        write_plot(os.path.join(step_path, plot))
        data_filename = None
        if data:
            data_filename = f'{gallery}_{season}.nc'
            with open(os.path.join(step_path, data_filename), 'w') as out:
                out.write(season)
        manifest.add(
            plot=plot,
            data=data_filename,
            group=group,
            gallery=gallery,
            title=f'{gallery} at 100 m, {season}',
            field=gallery,
            season=season,
            start_year=years[0],
            end_year=years[1],
        )
    manifest.write(step_path)
    return os.path.join(step_path, FRAGMENT_FILENAME)


def _publish_and_generate(tmp_path, fragments, simulation_name='QU240'):
    """Publish the fragments and generate the site over what was published"""
    output_path = str(tmp_path / 'output')
    published, missing = publish(fragments, output_path)
    assert missing == []
    filenames = generate_site(
        published,
        output_path,
        simulation_name=simulation_name,
        provenance=PROVENANCE,
    )
    return output_path, filenames


def _read(filename):
    with open(filename) as page:
        return page.read()


def _hrefs(text):
    return re.findall(r'href="([^"]*)"', text)


def _images(text):
    return re.findall(r'<img\b[^>]*>', text, flags=re.DOTALL)


def test_the_landing_page_lists_a_group_per_range(tmp_path):
    work_dir = str(tmp_path / 'work')
    fragments = [
        _make_step(work_dir, 'maps/0021-0040', years=(21, 40)),
        _make_step(work_dir, 'maps/0001-0010', years=(1, 10)),
    ]

    output_path, filenames = _publish_and_generate(tmp_path, fragments)
    index = _read(os.path.join(output_path, INDEX_FILENAME))

    # the group is the product group and the range, which the collector
    # composes, so a step never learns that ranges accumulate side by side
    assert '<h2>Climatology maps, years 0021-0040</h2>' in index
    assert '<h2>Climatology maps, years 0001-0010</h2>' in index
    # one page per gallery, plus the landing page
    assert len(filenames) == 3


def test_a_gallery_page_holds_the_products_in_plotted_order(tmp_path):
    work_dir = str(tmp_path / 'work')
    fragment = _make_step(work_dir, 'maps/0021-0040')

    output_path, filenames = _publish_and_generate(tmp_path, [fragment])
    gallery = _read(filenames[1])

    assert os.path.basename(filenames[1]) == (
        'climatology_maps_temperature_0021-0040.html'
    )
    captions = re.findall(r'<span class="caption">([^<]*)</span>', gallery)
    seasons = [caption.split(', ')[-1] for caption in captions]
    # ANN, DJF, MAM, JJA, SON because that is the order the step plotted
    # them in, with no sort key or season-ordering table anywhere
    assert seasons == SEASONS


def test_every_link_on_a_page_resolves(tmp_path):
    """The pages are relative, so a wrong prefix is a broken gallery."""
    work_dir = str(tmp_path / 'work')
    fragments = [
        _make_step(work_dir, 'maps/0021-0040'),
        _make_step(work_dir, 'salinity/0021-0040', gallery='salinity'),
    ]

    output_path, filenames = _publish_and_generate(tmp_path, fragments)

    for filename in filenames:
        text = _read(filename)
        targets = _hrefs(text) + re.findall(r'src="([^"]*)"', text)
        assert targets
        for target in targets:
            resolved = os.path.join(os.path.dirname(filename), target)
            assert os.path.exists(resolved), f'{target} from {filename}'


def test_a_thumbnail_links_to_the_plot_and_the_data_beside_it(tmp_path):
    work_dir = str(tmp_path / 'work')
    fragment = _make_step(work_dir, 'maps/0021-0040', seasons=['ANN'])

    _, filenames = _publish_and_generate(tmp_path, [fragment])
    gallery = _read(filenames[1])

    assert '../plots/climatology_maps_temperature_ANN_0021-0040.png' in _hrefs(
        gallery
    )
    assert '../plots/climatology_maps_temperature_ANN_0021-0040.nc' in _hrefs(
        gallery
    )


def test_a_product_with_no_data_file_has_no_data_link(tmp_path):
    work_dir = str(tmp_path / 'work')
    fragment = _make_step(
        work_dir, 'maps/0021-0040', seasons=['ANN'], data=False
    )

    _, filenames = _publish_and_generate(tmp_path, [fragment])
    gallery = _read(filenames[1])

    assert 'netCDF' not in gallery


def test_images_are_lazy_and_carry_their_size(tmp_path):
    """Lazy loading is what a page costs; the size is what keeps it still."""
    work_dir = str(tmp_path / 'work')
    fragment = _make_step(work_dir, 'maps/0021-0040', seasons=['ANN'])

    _, filenames = _publish_and_generate(tmp_path, [fragment])

    for filename in filenames:
        images = _images(_read(filename))
        assert images
        for image in images:
            assert 'loading="lazy"' in image
            # the thumbnails are made from a 160x90 stand-in plot
            assert 'width="160"' in image
            assert 'height="90"' in image


def test_a_page_asks_for_nothing_but_its_images(tmp_path):
    """One request and its images: no stylesheet, no script, no font."""
    work_dir = str(tmp_path / 'work')
    fragment = _make_step(work_dir, 'maps/0021-0040', seasons=['ANN'])

    _, filenames = _publish_and_generate(tmp_path, [fragment])

    for filename in filenames:
        text = _read(filename)
        assert '<style>' in text
        assert '<script' not in text
        assert 'rel="stylesheet"' not in text
        assert 'http://' not in text and 'https://' not in text


def test_the_landing_page_shows_each_gallerys_first_product(tmp_path):
    """It is deterministic because the collector preserves order."""
    work_dir = str(tmp_path / 'work')
    fragments = [
        _make_step(work_dir, 'maps/0021-0040'),
        _make_step(work_dir, 'salinity/0021-0040', gallery='salinity'),
    ]

    output_path, _ = _publish_and_generate(tmp_path, fragments)
    index = _read(os.path.join(output_path, INDEX_FILENAME))

    images = _images(index)
    assert len(images) == 2
    assert 'climatology_maps_temperature_ANN_0021-0040.jpg' in images[0]
    assert 'climatology_maps_salinity_ANN_0021-0040.jpg' in images[1]
    # and the caption names the gallery rather than the product
    assert '<span class="caption">Temperature</span>' in index
    assert '<span class="caption">Salinity</span>' in index
    assert (
        f'{GALLERIES_DIRNAME}/climatology_maps_salinity_0021-0040.html'
        in _hrefs(index)
    )


def test_every_page_carries_the_simulation_and_the_provenance(tmp_path):
    work_dir = str(tmp_path / 'work')
    fragment = _make_step(work_dir, 'maps/0021-0040', seasons=['ANN'])

    _, filenames = _publish_and_generate(
        tmp_path, [fragment], simulation_name='v3.LR.historical'
    )

    for filename in filenames:
        text = _read(filename)
        assert 'v3.LR.historical' in text
        assert 'years 0021-0040' in text
        for label, value in PROVENANCE.items():
            assert f'<dt>{label}</dt><dd>{value}</dd>' in text
        # and when it was generated, which nothing else records
        assert '<dt>generated</dt>' in text


def test_a_title_is_escaped_rather_than_interpolated(tmp_path):
    work_dir = str(tmp_path / 'work')
    step_path = os.path.join(work_dir, 'maps/0021-0040')
    os.makedirs(step_path)
    write_plot(os.path.join(step_path, 'temperature.png'))
    manifest = Manifest(step_name='maps')
    manifest.add(
        plot='temperature.png',
        group='climatology_maps',
        gallery='temperature',
        title='Temperature <&> salinity',
    )
    manifest.write(step_path)

    _, filenames = _publish_and_generate(
        tmp_path, [os.path.join(step_path, FRAGMENT_FILENAME)]
    )
    gallery = _read(filenames[1])

    assert 'Temperature &lt;&amp;&gt; salinity' in gallery
    assert 'Temperature <&> salinity' not in gallery


def test_publishing_nothing_still_generates_a_page(tmp_path):
    """A suite run with no products is an empty gallery, not a failure."""
    output_path, filenames = _publish_and_generate(tmp_path, [])

    assert len(filenames) == 1
    index = _read(os.path.join(output_path, INDEX_FILENAME))
    assert 'No products were published.' in index
    assert '0 products' in index
