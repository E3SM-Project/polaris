import sys
from typing import TYPE_CHECKING  # noqa: F401

if TYPE_CHECKING or sys.version_info >= (3, 9, 0):
    import importlib.resources as imp_res  # noqa: F401
else:
    # python <= 3.8
    import importlib_resources as imp_res  # noqa: F401

import matplotlib.pyplot as plt


def use_mplstyle():
    """
    Use the Polaris matplotlib style file
    """
    style_filename = str(
        imp_res.files('polaris.viz') / 'polaris.mplstyle')
    plt.style.use(style_filename)
