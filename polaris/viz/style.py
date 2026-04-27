import importlib.resources as imp_res

import matplotlib.pyplot as plt
from mpas_tools.viz.colormaps import register_sci_viz_colormaps

_SCI_VIZ_COLORMAPS_REGISTERED = False


def use_mplstyle():
    """
    Use the Polaris matplotlib style file
    """
    global _SCI_VIZ_COLORMAPS_REGISTERED

    if not _SCI_VIZ_COLORMAPS_REGISTERED:
        register_sci_viz_colormaps()
        _SCI_VIZ_COLORMAPS_REGISTERED = True

    style_filename = str(imp_res.files('polaris.viz') / 'polaris.mplstyle')
    plt.style.use(style_filename)
