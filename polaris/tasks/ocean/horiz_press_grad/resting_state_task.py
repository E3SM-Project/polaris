import os

from polaris import Task
from polaris.tasks.ocean.horiz_press_grad.forward import Forward
from polaris.tasks.ocean.horiz_press_grad.init import Init
from polaris.tasks.ocean.horiz_press_grad.resting_analysis import (
    RestingAnalysis,
    sweep_suffix,
)


class HorizPressGradRestingStateTask(Task):
    """
    A two-column test of discrete hydrostatic consistency: conservative
    temperature and absolute salinity are horizontally uniform functions of
    pseudo-height, so specific volume is a function of pressure alone, isobars
    are level, and the true horizontal pressure-gradient acceleration (HPGA)
    is identically zero however the coordinate surfaces or the sea floor are
    tilted between the columns.

    Whatever HPGA the model returns is therefore error.  The task sweeps a
    tilt (``z_tilde_bot_grad`` for a tilted coordinate, ``geom_z_bot_grad``
    for a stepped sea floor) at each of several resolution pairs, and the
    analysis step measures the absolute error and the exponent with which it
    grows with tilt.

    This is a sibling of
    :py:class:`~polaris.tasks.ocean.horiz_press_grad.task.HorizPressGradTask`
    rather than a mode of it.  That task pairs each horizontal resolution with
    one vertical resolution and keys its steps by horizontal resolution alone,
    so it cannot express the repeated horizontal resolutions this sweep needs.

    Attributes
    ----------
    sweep_keys : list of tuple
        The ``(horiz_res, vert_res, tilt)`` triples in the sweep
    """

    def __init__(self, component, name):
        """
        Create the test case

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component that this task belongs to

        name : str
            The name of the test case, which must have a corresponding
            <name>.cfg config file in the horiz_press_grad package that
            specifies the resting-state sweep.
        """
        subdir = os.path.join('column', 'horiz_press_grad', name)
        super().__init__(component=component, name=name, subdir=subdir)

        self.sweep_keys: list[tuple[float, float, float]] = []

        self.config.add_from_package(
            'polaris.tasks.ocean.horiz_press_grad', 'horiz_press_grad.cfg'
        )
        self.config.add_from_package(
            'polaris.tasks.ocean.horiz_press_grad',
            f'{name}.cfg',
        )

        self._setup_steps()

    def configure(self):
        """
        Set config options for the test case
        """
        super().configure()

        # set up the steps again in case a user has provided a new sweep
        self._setup_steps()

    def _setup_steps(self):
        """
        setup steps given the resolution pairs and the tilt sweep
        """
        section = self.config['horiz_press_grad']
        horiz_resolutions = section.getexpression('horiz_resolutions')
        vert_resolutions = section.getexpression('vert_resolutions')
        tilt_values = section.getexpression('tilt_values')
        tilt_option = section.get('tilt_option')

        assert horiz_resolutions is not None, (
            'The "horiz_resolutions" configuration option must be set in the '
            '"horiz_press_grad" section.'
        )
        assert vert_resolutions is not None, (
            'The "vert_resolutions" configuration option must be set in the '
            '"horiz_press_grad" section.'
        )
        assert tilt_values is not None, (
            'The "tilt_values" configuration option must be set in the '
            '"horiz_press_grad" section.'
        )
        assert len(horiz_resolutions) == len(vert_resolutions), (
            'The "horiz_resolutions" and "vert_resolutions" configuration '
            'options must have the same length.'
        )

        # start fresh with no steps
        for step in list(self.steps.values()):
            self.remove_step(step)

        init_steps = dict()
        forward_steps = dict()
        sweep_keys = []

        for horiz_res, vert_res in zip(
            horiz_resolutions, vert_resolutions, strict=True
        ):
            for tilt in tilt_values:
                key = (float(horiz_res), float(vert_res), float(tilt))
                if key in init_steps:
                    raise ValueError(
                        'Duplicate sweep point '
                        f'{sweep_suffix(*key)} in the "horiz_press_grad" '
                        'resolution and tilt sweeps.'
                    )
                suffix = sweep_suffix(*key)

                init_step = Init(
                    component=self.component,
                    horiz_res=horiz_res,
                    vert_res=vert_res,
                    indir=self.subdir,
                    subdir_suffix=suffix,
                    tilt_option=tilt_option,
                    tilt=tilt,
                )
                self.add_step(init_step)
                init_steps[key] = init_step

                forward_step = Forward(
                    component=self.component,
                    horiz_res=horiz_res,
                    init=init_step,
                    indir=self.subdir,
                    subdir_suffix=suffix,
                )
                self.add_step(forward_step)
                forward_steps[key] = forward_step

                sweep_keys.append(key)

        self.sweep_keys = sweep_keys

        self.add_step(
            RestingAnalysis(
                component=self.component,
                indir=self.subdir,
                dependencies={
                    'init': init_steps,
                    'forward': forward_steps,
                },
                sweep_keys=sweep_keys,
            )
        )
