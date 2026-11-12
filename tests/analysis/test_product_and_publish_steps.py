import json
import logging
import os

from polaris import Component
from polaris.analysis.manifest import FRAGMENT_FILENAME
from polaris.analysis.page import PAGE_FILENAME, PageStep
from polaris.analysis.product_step import ProductStep
from polaris.analysis.publish import MERGED_FILENAME, PLOTS_DIRNAME
from polaris.analysis.publish_step import PAGES_DIRNAME, PublishStep
from polaris.analysis.site import INDEX_FILENAME
from polaris.config import PolarisConfigParser
from tests.analysis.test_publish import write_plot

#: The config section of the stand-in component's analysis
SECTION = 'stand_in_analysis'


class _Plots(ProductStep):
    """A plotting step of a component that is not the ocean"""

    def __init__(self, component):
        super().__init__(component=component, name='plots', subdir='a/plots')


class _Intermediate(ProductStep):
    """A step that only computes what another step plots"""

    makes_products = False

    def __init__(self, component):
        super().__init__(
            component=component, name='intermediate', subdir='a/intermediate'
        )


def _config(tmp_path):
    config = PolarisConfigParser()
    for option, value in [
        ('output_path', str(tmp_path / 'output')),
        ('simulation_name', 'stand-in'),
        ('copy_netcdf', 'True'),
        ('thumbnail_size', '40, 40'),
        ('thumbnail_scale', '1.0'),
        ('thumbnail_format', 'jpeg'),
        ('thumbnail_quality', '75'),
    ]:
        config.set(SECTION, option, value)
    return config


def test_a_product_step_of_any_component_writes_a_fragment(tmp_path):
    """The fragment is a declared output and is written before the step
    runs, whatever component the step belongs to."""
    component = Component(name='stand_in')
    step = _Plots(component)
    assert FRAGMENT_FILENAME in step.outputs

    step.work_dir = str(tmp_path)
    step.runtime_setup()

    with open(tmp_path / FRAGMENT_FILENAME) as fragment:
        assert json.load(fragment)['products'] == []


def test_a_step_that_makes_no_products_declares_no_fragment():
    component = Component(name='stand_in')
    step = _Intermediate(component)

    assert FRAGMENT_FILENAME not in step.outputs


def test_a_publish_step_reads_its_options_from_its_own_section(tmp_path):
    """A component other than the ocean publishes a gallery, with its
    options in a section of its own."""
    component = Component(name='stand_in')
    plots = _Plots(component)
    intermediate = _Intermediate(component)
    publish = PublishStep(
        component=component,
        subdir='a/publish',
        product_steps=[plots, intermediate],
        section=SECTION,
    )
    # only the step that makes products is a dependency
    assert list(publish.dependencies) == ['a_plots']

    config = _config(tmp_path)
    base_work_dir = str(tmp_path / 'work')
    plots.config = config
    plots.work_dir = os.path.join(base_work_dir, plots.path)
    os.makedirs(plots.work_dir)
    plots.runtime_setup()
    write_plot(os.path.join(plots.work_dir, 'field.png'))
    with open(os.path.join(plots.work_dir, 'field.nc'), 'w') as out:
        out.write('field')
    plots.add_product(
        plot='field.png',
        data='field.nc',
        group='maps',
        gallery='field',
        title='A field',
    )

    publish.config = config
    publish.base_work_dir = base_work_dir
    publish.work_dir = os.path.join(base_work_dir, publish.path)
    publish.logger = logging.getLogger('test_product_and_publish_steps')
    os.makedirs(os.path.join(publish.work_dir, 'fragments'))
    os.symlink(
        os.path.join(plots.work_dir, FRAGMENT_FILENAME),
        os.path.join(publish.work_dir, 'fragments', 'a_plots.json'),
    )
    publish.fragment_filenames = [os.path.join('fragments', 'a_plots.json')]

    publish.run()

    output_path = str(tmp_path / 'output')
    assert publish.output_path() == output_path
    with open(os.path.join(output_path, MERGED_FILENAME)) as data:
        published = json.load(data)['products']
    assert len(published) == 1
    names = os.listdir(os.path.join(output_path, PLOTS_DIRNAME))
    assert any(name.endswith('.nc') for name in names)
    assert os.path.exists(os.path.join(output_path, INDEX_FILENAME))


class _Provenance(PageStep):
    """A step that makes a page beside the galleries"""

    def __init__(self, component):
        super().__init__(
            component=component,
            name='provenance',
            subdir='a/provenance',
            page_name='provenance',
            page_title='Provenance of the run',
        )


def test_a_publish_step_publishes_a_page_step_s_page(tmp_path):
    component = Component(name='stand_in')
    plots = _Plots(component)
    provenance = _Provenance(component)
    assert PAGE_FILENAME in provenance.outputs
    publish = PublishStep(
        component=component,
        subdir='a/publish',
        product_steps=[plots, provenance],
        section=SECTION,
    )
    assert list(publish.dependencies) == ['a_plots', 'a_provenance']
    assert publish.page_filenames == [
        os.path.join(PAGES_DIRNAME, 'a_provenance.json')
    ]

    config = _config(tmp_path)
    base_work_dir = str(tmp_path / 'work')
    for step in [plots, provenance]:
        step.config = config
        step.work_dir = os.path.join(base_work_dir, step.path)
        os.makedirs(step.work_dir)
    plots.runtime_setup()
    provenance.page.add_section('Code', entries=[('E3SM', 'v3.2.0')])
    provenance.write_page()

    publish.config = config
    publish.base_work_dir = base_work_dir
    publish.work_dir = os.path.join(base_work_dir, publish.path)
    publish.logger = logging.getLogger('test_product_and_publish_steps')
    for dirname, name, step, filename in [
        ('fragments', 'a_plots', plots, FRAGMENT_FILENAME),
        (PAGES_DIRNAME, 'a_provenance', provenance, PAGE_FILENAME),
    ]:
        os.makedirs(os.path.join(publish.work_dir, dirname))
        os.symlink(
            os.path.join(step.work_dir, filename),
            os.path.join(publish.work_dir, dirname, f'{name}.json'),
        )
    publish.fragment_filenames = [os.path.join('fragments', 'a_plots.json')]

    publish.run()

    page = os.path.join(str(tmp_path / 'output'), 'provenance', 'index.html')
    with open(page) as text:
        assert 'v3.2.0' in text.read()
