from polaris.ocean.resolution import resolution_to_subdir
from polaris.ocean.tasks.baroclinic_channel.baroclinic_channel_test_case import (  # noqa: E501
    BaroclinicChannelTestCase,
)
from polaris.ocean.tasks.baroclinic_channel.decomp import Decomp
from polaris.ocean.tasks.baroclinic_channel.default import Default
from polaris.ocean.tasks.baroclinic_channel.restart import Restart
from polaris.ocean.tasks.baroclinic_channel.rpe import Rpe
from polaris.ocean.tasks.baroclinic_channel.threads import Threads


def add_baroclinic_channel_tasks(component):
    """
    Add tasks for different baroclinic channel tests to the ocean component

    component : polaris.ocean.Ocean
        the ocean component that the tasks will be added to
    """
    for resolution in [10., 4., 1.]:
        resdir = resolution_to_subdir(resolution)
        resdir = f'baroclinic_channel/{resdir}'

        if resolution == 10.:
            component.add_task(
                Default(component=component, resolution=resolution,
                        indir=resdir))

            component.add_task(
                Decomp(component=component, resolution=resolution,
                       indir=resdir))

            component.add_task(
                Restart(component=component, resolution=resolution,
                        indir=resdir))

            component.add_task(
                Threads(component=component, resolution=resolution,
                        indir=resdir))

        component.add_task(
            Rpe(component=component, resolution=resolution,
                indir=resdir))
