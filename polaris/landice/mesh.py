from mpas_tools.logging import check_call

from polaris.model_step import make_graph_file


def make_mali_mesh(
    in_filename,
    out_filename,
    levels,
    logger,
    vertical_spacing='uniform',
    thermal=False,
    dirichlet=False,
    hydro=False,
    observations=False,
    graph_filename=None,
):
    """
    Turn a culled planar MPAS mesh into a MALI mesh with the fields MALI needs,
    without needing a MALI build

    Parameters
    ----------
    in_filename : str
        The culled MPAS mesh file to convert

    out_filename : str
        The MALI mesh file to write

    levels : int
        The number of vertical levels in the MALI mesh

    logger : logging.Logger
        A logger for output from the conversion

    vertical_spacing : {'uniform', 'glimmer'}, optional
        The spacing of the vertical levels

    thermal : bool, optional
        Whether to add the fields for thermal initial conditions

    dirichlet : bool, optional
        Whether to add the fields for Dirichlet velocity boundary conditions

    hydro : bool, optional
        Whether to add the fields for subglacial hydrology initial conditions

    observations : bool, optional
        Whether to add the observational fields used in optimizations

    graph_filename : str, optional
        A graph file to write for partitioning the MALI mesh
    """
    args = [
        'create_landice_grid_from_generic_mpas_grid',
        '-i',
        in_filename,
        '-o',
        out_filename,
        '-l',
        f'{levels}',
        '-v',
        vertical_spacing,
    ]
    for flag, include in [
        ('--thermal', thermal),
        ('--diri', dirichlet),
        ('--hydro', hydro),
        ('--obs', observations),
    ]:
        if include:
            args.append(flag)

    check_call(args, logger=logger)

    if graph_filename is not None:
        make_graph_file(
            mesh_filename=out_filename, graph_filename=graph_filename
        )
