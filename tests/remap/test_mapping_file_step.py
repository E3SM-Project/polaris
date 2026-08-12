from polaris.remap import MappingFileStep


class _FakeComponent:
    name = 'fake'


def _make_step(**kwargs):
    return MappingFileStep(
        component=_FakeComponent(),
        name='map',
        subdir='map',
        **kwargs,
    )


def test_remapper_does_not_use_tmp():
    """
    /tmp is node-local on many HPC machines, so the SCRIP and .h5m files
    must go in the step's work directory instead.
    """
    step = _make_step()
    assert step.remapper.use_tmp is False


def test_remapper_method_is_passed_through():
    step = _make_step(method='conserve')
    assert step.remapper.method == 'conserve'


def test_remapper_defaults_to_bilinear():
    step = _make_step()
    assert step.remapper.method == 'bilinear'


def test_remapper_ntasks_is_passed_through():
    step = _make_step(ntasks=128, min_tasks=16)
    assert step.remapper.ntasks == 128
