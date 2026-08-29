import json
import logging
import os

import pytest

from polaris.analysis import Manifest
from polaris.analysis.publish import MERGED_FILENAME, PLOTS_DIRNAME
from polaris.analysis.site import GALLERIES_DIRNAME, INDEX_FILENAME
from polaris.analysis.thumbnail import THUMBNAILS_DIRNAME
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis import add_analysis_tasks
from tests.analysis.test_publish import write_plot
from tests.ocean.analysis.test_analysis_tasks import (
    PRODUCT_TASK_SUBDIRS,
    TASK_SUBDIRS,
)

PUBLISH_SUBDIR = 'analysis/publish'


def _make_component():
    component = Ocean()
    add_analysis_tasks(component)
    return component


def _publish_step(component):
    return component.tasks[PUBLISH_SUBDIR].steps['publish']


def _product_steps(component):
    """Every step of the other tasks that makes products, in suite order"""
    steps = {}
    for task_subdir in PRODUCT_TASK_SUBDIRS:
        for step in component.tasks[task_subdir].steps.values():
            if step.makes_products:
                steps[step.subdir] = step
    return steps


def _configure(component, order):
    """Configure the tasks in the order given, as a set would in any order"""
    for task_subdir in order:
        component.tasks[task_subdir].configure()


def _set_range(component, section, start_year, end_year):
    config = component.tasks[PUBLISH_SUBDIR].config
    config.set(section, 'start_year', str(start_year), user=True)
    config.set(section, 'end_year', str(end_year), user=True)


def test_the_publish_step_depends_on_every_step_that_makes_products():
    component = _make_component()
    step = _publish_step(component)

    products = _product_steps(component)
    assert len(products) > 1
    assert [dep.subdir for dep in step.dependencies.values()] == list(products)
    # the dependency's name is its work directory, so two ranges of one
    # product do not collide
    assert 'analysis_global_stats_0001-0010' in step.dependencies


def test_the_climatology_is_not_a_dependency():
    """It makes what the maps are plotted from, and publishes nothing."""
    component = _make_component()
    step = _publish_step(component)

    subdirs = [dep.subdir for dep in step.dependencies.values()]
    assert 'analysis/climatology/0001-0010' not in subdirs
    climatology = component.tasks['analysis/climatology_maps'].steps[
        'climatology'
    ]
    assert not climatology.makes_products


@pytest.mark.parametrize('order', ['publish first', 'publish last'])
def test_the_dependencies_are_the_steps_that_are_set_up(order):
    """Tasks are configured in an arbitrary order, so this cannot depend on
    it: Polaris checks that a dependency is a step object that was set up,
    and a task discards its steps and builds new ones every time it is
    configured."""
    component = _make_component()
    _set_range(component, 'ocean_analysis_climatology', 21, 40)
    _set_range(component, 'ocean_analysis_time_series', 1, 60)

    subdirs = TASK_SUBDIRS
    if order == 'publish first':
        subdirs = [PUBLISH_SUBDIR] + PRODUCT_TASK_SUBDIRS
    _configure(component, subdirs)

    products = _product_steps(component)
    dependencies = _publish_step(component).dependencies
    assert [dep.subdir for dep in dependencies.values()] == list(products)
    for dependency in dependencies.values():
        # the same object, not one that merely names the same directory
        assert dependency is products[dependency.subdir]
    assert 'analysis/global_stats/0001-0060' in products


def test_a_dependency_is_asked_for_one_pickle_however_often_it_rebuilds():
    component = _make_component()
    _configure(component, TASK_SUBDIRS)
    _configure(component, TASK_SUBDIRS)

    for step in _product_steps(component).values():
        assert step.outputs.count('step_after_run.pickle') == 1


def _write_fragment(base_work_dir, step, seasons):
    """Make a step's work directory look like it ran and made products"""
    step_path = os.path.join(base_work_dir, step.path)
    os.makedirs(step_path, exist_ok=True)
    manifest = Manifest(step_name=step.name)
    for season in seasons:
        plot = f'{step.name}_{season}.png'
        write_plot(os.path.join(step_path, plot))
        manifest.add(
            plot=plot,
            group='climatology_maps',
            gallery=step.name,
            title=f'{step.name}, {season}',
            season=season,
            start_year=1,
            end_year=10,
        )
    manifest.write(step_path)


def test_the_step_publishes_the_fragments_of_the_steps_it_depends_on(
    tmp_path,
):
    component = _make_component()
    step = _publish_step(component)
    base_work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    step.config.set('ocean_analysis', 'output_path', output_path, user=True)
    step.base_work_dir = base_work_dir
    step.logger = logging.getLogger('test_publish_step')

    products = _product_steps(component)
    _write_fragment(base_work_dir, products['analysis/moc/0001-0010'], ['ANN'])
    # every other step ran and made nothing, which is not an error
    step.run()

    with open(os.path.join(output_path, MERGED_FILENAME)) as data:
        published = json.load(data)['products']
    assert len(published) == 1
    assert published[0]['plot'] == os.path.join(
        PLOTS_DIRNAME, 'climatology_maps_moc_ANN_0001-0010.png'
    )
    # the thumbnail and the gallery are made from what was published
    assert os.path.exists(os.path.join(output_path, published[0]['thumbnail']))
    assert os.path.exists(os.path.join(output_path, INDEX_FILENAME))
    assert os.listdir(os.path.join(output_path, GALLERIES_DIRNAME)) == [
        'climatology_maps_moc_0001-0010.html'
    ]


def test_the_step_reads_the_thumbnail_options_from_the_config(tmp_path):
    component = _make_component()
    step = _publish_step(component)
    base_work_dir = str(tmp_path / 'work')
    output_path = str(tmp_path / 'output')
    config = step.config
    config.set('ocean_analysis', 'output_path', output_path, user=True)
    config.set('ocean_analysis', 'thumbnail_size', '40, 40', user=True)
    config.set('ocean_analysis', 'thumbnail_format', 'webp', user=True)
    config.set('ocean_analysis', 'thumbnail_quality', '50', user=True)
    step.base_work_dir = base_work_dir
    step.logger = logging.getLogger('test_publish_step')

    products = _product_steps(component)
    _write_fragment(base_work_dir, products['analysis/moc/0001-0010'], ['ANN'])
    step.run()

    thumbnails = os.listdir(os.path.join(output_path, THUMBNAILS_DIRNAME))
    assert thumbnails == ['climatology_maps_moc_ANN_0001-0010.webp']


def test_the_output_path_defaults_to_the_work_directory(tmp_path):
    component = _make_component()
    step = _publish_step(component)
    step.base_work_dir = str(tmp_path)

    assert step.output_path() == os.path.join(str(tmp_path), 'analysis_output')
