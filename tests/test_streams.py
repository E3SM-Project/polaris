import os

import pytest

from polaris.streams import find_stream_files, get_stream, read_file

STREAMS = """<streams>
<immutable_stream name="restart"
                  type="input;output"
                  filename_template="case.mpaso.rst.$Y-$M-$D_$S.nc"/>

<stream name="timeSeriesStatsMonthlyOutput"
        type="output"
        filename_template="case.mpaso.hist.am.timeSeriesStatsMonthly.$Y-$M-$D.nc"
        output_interval="00-01-00_00:00:00">

    <var name="xtime"/>
</stream>
</streams>
"""


def _touch(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w'):
        pass


def test_a_run_s_streams_file_is_read_from_its_path(tmp_path):
    filename = tmp_path / 'streams.ocean'
    filename.write_text(STREAMS)

    tree = read_file(str(filename))

    stream = get_stream(tree, 'timeSeriesStatsMonthlyOutput')
    assert stream.attrib['output_interval'] == '00-01-00_00:00:00'
    # immutable streams are found too
    assert get_stream(tree, 'restart').attrib['type'] == 'input;output'


def test_a_missing_stream_names_the_streams_there_are(tmp_path):
    filename = tmp_path / 'streams.ocean'
    filename.write_text(STREAMS)
    tree = read_file(str(filename))

    with pytest.raises(ValueError, match='restart, timeSeriesStatsMonthly'):
        get_stream(tree, 'globalStatsOutput')


def test_files_are_found_in_date_order_with_their_dates(tmp_path):
    """Months 10 and 2 sort by date, not by name, and a file the template
    does not match is left out."""
    prefix = 'case.mpaso.hist.am.timeSeriesStatsMonthly'
    template = f'{prefix}.$Y-$M-$D.nc'
    for name in ['0002-10-01', '0002-02-01', '0001-12-01']:
        _touch(str(tmp_path / f'{prefix}.{name}.nc'))
    _touch(str(tmp_path / f'{prefix}.nc'))

    files = find_stream_files(template, [str(tmp_path)])

    assert [(f.year, f.month, f.day) for f in files] == [
        (1, 12, 1),
        (2, 2, 1),
        (2, 10, 1),
    ]
    assert all(os.path.isabs(f.path) for f in files)


def test_the_first_directory_is_preferred(tmp_path):
    """A file archived and still in the run directory is taken from the
    archive, which is listed first."""
    template = 'case.mali.hist.$Y-$M-$D_$S.nc'
    archive = tmp_path / 'archive'
    run = tmp_path / 'run'
    _touch(str(archive / 'case.mali.hist.0001-01-01_00000.nc'))
    _touch(str(run / 'case.mali.hist.0001-01-01_00000.nc'))
    _touch(str(run / 'case.mali.hist.0002-01-01_43200.nc'))

    files = find_stream_files(template, [str(archive), str(run)])

    assert [os.path.dirname(f.path) for f in files] == [str(archive), str(run)]
    assert files[1].seconds == 43200


def test_a_relative_directory_and_a_time_of_day_are_matched(tmp_path):
    template = 'analysis_members/globalStats.$Y-$M-$D_$h.$m.$s.nc'
    _touch(
        str(tmp_path / 'analysis_members/globalStats.0001-01-01_06.30.15.nc')
    )

    files = find_stream_files(template, [str(tmp_path)])

    assert len(files) == 1
    assert files[0].seconds == 6 * 3600 + 30 * 60 + 15


@pytest.mark.parametrize(
    'template, message',
    [
        ('case.$Y-$d.nc', 'cannot be matched'),
        ('case.$Y-$Y.nc', 'more than once'),
    ],
)
def test_templates_that_cannot_be_matched_raise(tmp_path, template, message):
    with pytest.raises(ValueError, match=message):
        find_stream_files(template, [str(tmp_path)])
