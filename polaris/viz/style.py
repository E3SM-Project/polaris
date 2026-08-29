import importlib.resources as imp_res
import threading
from contextlib import contextmanager
from typing import Any, cast

import matplotlib.pyplot as plt
import matplotlib.style
from mpas_tools.viz.colormaps import register_sci_viz_colormaps

_COLORMAP_LOCK = threading.Lock()
_SCI_VIZ_COLORMAPS_REGISTERED = False


@contextmanager
def mplstyle_context(dpi=None):
    """
    A context manager that applies the Polaris matplotlib style for the
    duration of a plot and restores the previous settings afterwards

    Matplotlib's ``rcParams`` are global to the process, so a step that
    assigns to them changes the appearance of plots made by any other step
    running at the same time.  Plotting inside this context manager keeps the
    settings scoped to the plot that needs them.

    Parameters
    ----------
    dpi : int, optional
        Dots per inch for saved figures, overriding the value from the
        Polaris style file
    """
    _register_colormaps()

    style_filename = str(imp_res.files('polaris.viz') / 'polaris.mplstyle')
    overrides: dict[str, Any] = {} if dpi is None else {'savefig.dpi': dpi}
    # rc_context is typed with a Literal of every rcParam name; 'savefig.dpi'
    # is one of them, but the key is built here rather than written inline
    with (
        matplotlib.style.context(style_filename),
        plt.rc_context(cast(Any, overrides)),
    ):
        yield


def _register_colormaps():
    """
    Add the scientific visualization colormaps to Matplotlib's registry, once
    per process
    """
    global _SCI_VIZ_COLORMAPS_REGISTERED

    with _COLORMAP_LOCK:
        if not _SCI_VIZ_COLORMAPS_REGISTERED:
            register_sci_viz_colormaps()
            _SCI_VIZ_COLORMAPS_REGISTERED = True
