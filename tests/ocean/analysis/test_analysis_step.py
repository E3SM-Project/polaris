import json
import os

import pytest

from polaris.analysis.manifest import (
    FRAGMENT_FILENAME,
    Manifest,
    read_fragment,
)
from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.analysis import add_analysis_tasks


def _make_component():
    component = Ocean()
    add_analysis_tasks(component)
    return component


def _step(component, task_subdir, name, tmp_path):
    """A step of the suite with a work directory, as the runner would give
    it one"""
    step = component.tasks[task_subdir].steps[name]
    step.work_dir = str(tmp_path / step.path)
    os.makedirs(step.work_dir, exist_ok=True)
    return step


def _fragment(step):
    return os.path.join(step.work_dir, FRAGMENT_FILENAME)


def _moc(tmp_path):
    return _step(_make_component(), 'analysis/moc', 'moc', tmp_path)


def test_a_step_that_makes_products_writes_a_fragment_before_it_runs(
    tmp_path,
):
    """Empty until the step has something to put in it, so that a step which
    makes nothing still leaves the input the publish step declares."""
    step = _moc(tmp_path)

    step.runtime_setup()

    manifest = read_fragment(_fragment(step))
    assert manifest.products == []
    # the work directory names the range as well as the product
    assert manifest.step_name == 'analysis/moc/0001-0010'


def test_the_fragment_is_current_as_each_product_is_described(tmp_path):
    """Written as products are added rather than at the end of run(), so no
    step author has to remember a call."""
    step = _moc(tmp_path)
    step.runtime_setup()

    for season in ('ANN', 'DJF'):
        step.add_product(
            plot=f'moc_{season}.png',
            data=f'moc_{season}.nc',
            group='moc',
            gallery='moc',
            title=f'Overturning streamfunction, {season}',
            season=season,
        )
        plots = [
            product.plot for product in read_fragment(_fragment(step)).products
        ]
        assert plots[-1] == f'moc_{season}.png'

    # order is meaning, and the fragment keeps it
    assert plots == ['moc_ANN.png', 'moc_DJF.png']


def test_a_product_covers_the_step_s_range_without_being_told(tmp_path):
    """The range is what keeps two analyses of one simulation apart in the
    published names, so it is not something to pass at each call."""
    step = _moc(tmp_path)
    step.runtime_setup()

    step.add_product(
        plot='moc_ANN.png',
        group='moc',
        gallery='moc',
        title='Overturning streamfunction, ANN',
    )
    step.add_product(
        plot='moc_reference.png',
        group='moc',
        gallery='moc',
        title='Overturning streamfunction from an earlier run',
        start_year=1,
        end_year=5,
    )

    products = read_fragment(_fragment(step)).products
    assert products[0].facets['start_year'] == step.start_year
    assert products[0].facets['end_year'] == step.end_year
    # a caller with its own range keeps it
    assert products[1].facets['end_year'] == 5


def test_a_rerun_does_not_leave_the_products_of_the_last_one(tmp_path):
    """A step is built fresh for each run, and so is its fragment: what an
    earlier run described is gone before this one starts."""
    step = _moc(tmp_path)
    stale = Manifest(step_name=step.subdir)
    stale.add(plot='moc_ANN.png', group='moc', gallery='moc', title='ANN')
    stale.write(step.work_dir)

    step.runtime_setup()

    with open(_fragment(step)) as data:
        assert json.load(data)['products'] == []


def test_a_step_that_makes_no_products_writes_nothing(tmp_path):
    """The climatology is what the maps are plotted from, not something a
    reader browses."""
    component = _make_component()
    step = _step(
        component, 'analysis/climatology_maps', 'climatology', tmp_path
    )

    step.runtime_setup()

    assert not os.path.exists(_fragment(step))
    with pytest.raises(ValueError, match='makes_products = False'):
        step.add_product(
            plot='climatology.png',
            group='climatology_maps',
            gallery='climatology',
            title='A product the climatology has no business making',
        )


def test_the_fragment_is_a_declared_output_of_the_steps_that_write_one():
    """Declared, so a step that failed to write one is named itself rather
    than as a missing input of publish."""
    component = _make_component()
    maps = component.tasks['analysis/climatology_maps'].steps

    for name, step in maps.items():
        assert (FRAGMENT_FILENAME in step.outputs) == step.makes_products, name
