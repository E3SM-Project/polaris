import os
from types import SimpleNamespace

import pytest

from polaris.analysis import generate_site, publish
from polaris.analysis.page import PAGE_FILENAME, Page, publish_pages
from polaris.tasks.e3sm.analysis.misomip.publish import get_site_links
from polaris.tasks.e3sm.analysis.misomip.summary import (
    add_captions,
    get_published_plots,
    get_run_highlights,
    get_years_text,
    read_captions,
)
from tests.analysis.test_site import PROVENANCE, _make_step, _read

PLOT = 'climatology_maps_temperature_ANN_0021-0040.png'

CAPTIONS = f"""LINK|Every plot of the run|../index.html
NOTE|About this run|The ocean is MPAS-Ocean on a 2 km mesh.
NOTE|-|Code: E3SM 1db1a5af2b.

NOTE|Every five years|Melt rises through year 2.
TABLE|Monthly means over each year|Year ; Melt (Gt/yr)
ROW|1 ; 3.1–12.8
ROW|5 ; 23.6|24.3
{PLOT}|Temperature|Averaged over years 21–40.
"""


def _captions(tmp_path, text):
    filename = str(tmp_path / 'captions.txt')
    with open(filename, 'w') as out:
        out.write(text)
    return read_captions(filename)


def test_a_summary_shows_notes_a_table_and_a_published_plot(tmp_path):
    """The page links each plot where the publish step puts it, so the
    summary needs no copies of its own."""
    fragment = _make_step(str(tmp_path / 'work'), 'maps', seasons=['ANN'])
    plots = get_published_plots([fragment])
    assert list(plots) == [PLOT]
    page = Page(name='summary', title='Summary')

    add_captions(page, _captions(tmp_path, CAPTIONS), plots)

    assert [section['title'] for section in page.sections] == [
        None,
        'About this run',
        'Every five years',
        'Temperature',
    ]
    assert page.sections[1]['paragraphs'] == [
        'The ocean is MPAS-Ocean on a 2 km mesh.',
        'Code: E3SM 1db1a5af2b.',
    ]
    # a row's cells may hold the field separator
    row = page.sections[2]['table']['rows'][1]
    assert [cell['value'] for cell in row] == ['5', '23.6|24.3']

    step_path = str(tmp_path / 'summary')
    os.makedirs(step_path)
    page.write(step_path)
    output_path = str(tmp_path / 'output')
    published, _ = publish([fragment], output_path)
    pages = publish_pages(
        [os.path.join(step_path, PAGE_FILENAME)], output_path
    )
    generate_site(
        published, output_path, 'Ocean1', provenance=PROVENANCE, pages=pages
    )
    summary = os.path.join(output_path, 'summary')
    text = _read(os.path.join(summary, 'index.html'))
    assert '<caption>Monthly means over each year</caption>' in text
    assert f'src="../plots/{PLOT}"' in text
    assert os.path.exists(os.path.join(summary, '..', 'plots', PLOT))


@pytest.mark.parametrize(
    'text, match',
    [
        ('missing.png|A plot|Its caption.\n', f'The plots are:\n  {PLOT}'),
        ('TABLE|A table|a ; b\n', 'a table goes under a NOTE'),
        ('NOTE|Notes|\nTABLE|A table|a ; b\nROW|1\n', 'has 1 cells'),
        ('NOTE|Notes\n', 'too few fields'),
    ],
)
def test_a_captions_file_that_does_not_fit_names_its_line(
    tmp_path, text, match
):
    plots = {PLOT: f'../plots/{PLOT}'}
    with pytest.raises(ValueError, match=match):
        add_captions(
            Page('summary', 'Summary'), _captions(tmp_path, text), plots
        )


def test_a_run_s_years_say_whether_it_is_finished():
    assert get_years_text(1, 5) == 'years 1–5'
    assert get_years_text(1, 1, 100) == 'year 1 of 100, running'
    assert get_years_text(1, 5, 100) == 'years 1–5 of 100, running'
    assert get_years_text(1, 20, 20) == 'years 1–20, finished'


def test_the_highlights_name_mali_s_mode_the_integrator_and_resolution():
    for mode, text in [
        ('static', 'MALI static'),
        ('data', 'MALI data mode'),
        ('prognostic', 'MALI prognostic'),
    ]:
        run = SimpleNamespace(
            kind='e3sm',
            run=SimpleNamespace(
                case=SimpleNamespace(landice_mode=mode),
                namelist_option=lambda option: "'split_explicit'",
            ),
        )
        assert get_run_highlights(run, '2km') == [
            text,
            'split-explicit',
            '2 km',
        ]
    run = SimpleNamespace(
        kind='standalone',
        run=SimpleNamespace(namelist_option=lambda option: 'RK4'),
    )
    assert get_run_highlights(run, '4km') == [
        'standalone MPAS-Ocean',
        'RK4',
        '4 km',
    ]


def test_every_run_has_the_same_links_in_the_same_order():
    pages = [
        {'name': name, 'title': name, 'href': f'{name}/index.html'}
        for name in ['provenance', 'e3sm_run_health', 'summary']
    ]
    assert get_site_links(pages, '../../../index.html') == [
        ('Summary', 'summary/index.html'),
        ('Gallery', 'index.html'),
        ('Run health', 'e3sm_run_health/index.html'),
        ('Provenance', 'provenance/index.html'),
        ('All runs', '../../../index.html'),
    ]
    # without a summary or a page of all runs, the rest keep their order
    assert [text for text, _ in get_site_links(pages[:2])] == [
        'Gallery',
        'Run health',
        'Provenance',
    ]
