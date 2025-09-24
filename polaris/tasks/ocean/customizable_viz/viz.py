def get_viz_defaults():
    # indexed by mpas-ocean variable name in instantaneous output
    viz_dict = {
        'temperature': {'colormap': 'thermal', 'units': r'$^{\circ}$C'},
    }
    return viz_dict
