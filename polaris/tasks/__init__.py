from typing import List

from polaris import Component

# import new components here
from polaris.tasks.ocean import Ocean
from polaris.tasks.seaice import SeaIce


def get_components():
    """
    Get a list of components, which in turn contain lists tasks

    Returns
    -------
    components : list of polaris.Component
        A list of components containing all available tasks
    """
    # add new components here
    components: List[Component] = [
        Ocean(),
        SeaIce(),
    ]
    return components
