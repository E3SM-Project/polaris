import importlib.resources as imp_res

import matplotlib.pyplot as plt


def use_mplstyle():
    """
    Use the Polaris matplotlib style file
    """
    style_filename = str(
        imp_res.files('polaris.viz') / 'polaris.mplstyle')
    plt.style.use(style_filename)
