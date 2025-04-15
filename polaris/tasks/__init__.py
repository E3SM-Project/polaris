from typing import List

from polaris import Component

# import new components here
from polaris.tasks.mesh import mesh
from polaris.tasks.ocean import ocean
from polaris.tasks.seaice import seaice

# Add new components alphabetically to this dictionary
components: List[Component] = [
    mesh,
    ocean,
    seaice,
]
