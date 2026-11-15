from polaris.tasks.e3sm.analysis.misomip.centerline import _date_text


def test_a_frame_is_dated_by_the_end_of_its_month():
    """The month ending at the start of year 18, and noon on 1 March of
    year 1"""
    assert _date_text(17 * 365.0) == 'Year 18, Jan 1'
    assert _date_text(59.0) == 'Year 1, Mar 1'
