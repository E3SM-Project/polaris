from typing import List

from polaris.component import Component
# import new components here
from polaris.ocean import Ocean


def get_components():
    """
    Get a list of components, which in turn contain lists of test groups

    Returns
    -------
    components : list of polaris.Component
        A list of components containing all available tests
    """
    # add new components here
    components: List[Component] = [
        Ocean(),
    ]
    return components
