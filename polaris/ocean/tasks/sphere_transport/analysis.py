import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr

from polaris import Step
from polaris.ocean.resolution import resolution_to_subdir


class Analysis(Step):
    """
    A step for analyzing the output from sphere transport test cases

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW
        meshes

    case_name : str
        The name of the test case

    tcdata : dict
        Attributes of the convergence analysis
    """
    def __init__(self, component, resolutions, icosahedral, subdir,
                 case_name, dependencies):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolutions : list of float
            The resolutions of the meshes that have been run

        icosahedral : bool
            Whether to use icosahedral, as opposed to less regular, JIGSAW
            meshes

        subdir : str
            The subdirectory that the step resides in

        case_name: str
            The name of the test case

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        super().__init__(component=component, name='analysis', subdir=subdir)
        self.resolutions = resolutions
        self.icosahedral = icosahedral
        self.case_name = case_name
        self.tcdata = dict()

        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            base_mesh = dependencies['mesh'][resolution]
            init = dependencies['init'][resolution]
            forward = dependencies['forward'][resolution]
            self.add_input_file(
                filename=f'{mesh_name}_mesh.nc',
                work_dir_target=f'{base_mesh.path}/base_mesh.nc')
            self.add_input_file(
                filename=f'{mesh_name}_init.nc',
                work_dir_target=f'{init.path}/initial_state.nc')
            self.add_input_file(
                filename=f'{mesh_name}_output.nc',
                work_dir_target=f'{forward.path}/output.nc')

        self.add_output_file('convergence.csv')
        self.add_output_file('convergence.png')

    def run(self):
        """
        Run this step of the test case
        """
        plt.switch_backend('Agg')
        resolutions = self.resolutions
        case_name = self.case_name

        # Collect data
        ncells = []
        for resolution in resolutions:
            mesh_name = resolution_to_subdir(resolution)
            ncd = xr.open_dataset(f'{mesh_name}_output.nc')
            self.tcdata[resolution] = {'dataset': ncd}
            self.tcdata[resolution]['appx_mesh_size'] = _appx_mesh_size(ncd)
            self.tcdata[resolution]['err'] = _compute_error_from_output_ncfile(
                ncd)
            ncells.append(ncd.dims['nCells'])
        _print_data_as_csv(self.tcdata)

        # convergence analysis
        data = pd.read_csv('convergence.csv')

        section = self.config[case_name]

        all_above_thres = True
        error_message = ''
        l2_err = np.stack((data.l21, data.l22, data.l23), axis=1)

        for num_tracer in np.arange(1, 4):
            tracer = f'tracer{num_tracer}'
            conv_thresh = section.getfloat(f'{tracer}_conv_thresh')
            p = np.polyfit(np.log10(ncells),
                           np.log10(l2_err[:, num_tracer - 1]), 1)
            # factor of 2 because nCells is like an inverse area, and we
            # want the convergence rate vs. cell size
            conv = abs(p[0]) * 2.0

            if conv < conv_thresh:
                all_above_thres = False
                error_message = \
                    f'{error_message}\n' \
                    f'            {tracer}: {conv:.2f} < {conv_thresh}'

        fig, ax = plt.subplots()
        _plot_convergence(
            ax,
            case_name,
            data.dlambda,
            data.res,
            data.linf1,
            data.l21,
            data.linf2,
            data.l22,
            data.linf3,
            data.l23)
        fig.savefig('convergence.png', bbox_inches='tight')

        if not all_above_thres:
            raise ValueError('The following tracers have order of convergence '
                             '< min tolerance:' + error_message)


def _appx_mesh_size(dataset):
    ncells = dataset.sizes["nCells"]
    return np.sqrt(4 * np.pi / ncells)


def _compute_error_from_output_ncfile(dataset, lev=1):
    """
    Given an xarray dataset associated with the output.nc file from a test
    case in the sphere_transport test group, this function computes the
    linf and l2 relative error values by comparing the final time step to
    the initial condition.

    Parameters
    ----------
    dataset : xarray.Dataset
        a dataset initialized with an MPAS output.nc file.

    lev: int, optional
        vertical level to plot.

    Returns
    -------
    result : dict
        a dictionary containing the linf and l2 relative errors for each of the
        3 debug tracers.
    """
    tidx = 12  # this should correspond to 12 days
    tidx_filament = 6  # this should correspond to 6 days
    tracer1 = dataset["tracer1"].values
    tracer2 = dataset["tracer2"].values
    tracer3 = dataset["tracer3"].values
    tracer1_exact = tracer1[0, :, lev]
    tracer2_exact = tracer2[0, :, lev]
    tracer3_exact = tracer3[0, :, lev]
    tracer1_error = np.abs(tracer1[tidx, :, lev] - tracer1_exact)
    tracer2_error = np.abs(tracer2[tidx, :, lev] - tracer2_exact)
    tracer3_error = np.abs(tracer3[tidx, :, lev] - tracer3_exact)
    tracer1_max = np.amax(tracer1_exact)
    tracer2_max = np.amax(tracer2_exact)
    tracer3_max = np.amax(tracer3_exact)
    tracer1_min = np.amin(tracer1_exact)
    tracer2_min = np.amin(tracer2_exact)
    tracer3_min = np.amin(tracer3_exact)
    cell_area = dataset["areaCell"].values
    tracer1_linf = np.amax(tracer1_error) / np.amax(np.abs(tracer1_exact))
    tracer2_linf = np.amax(tracer2_error) / np.amax(np.abs(tracer2_exact))
    tracer3_linf = np.amax(tracer3_error) / np.amax(np.abs(tracer3_exact))
    tracer1_l2 = np.sqrt(
        np.sum(
            np.square(tracer1_error) *
            cell_area) /
        np.sum(
            np.square(tracer1_exact) *
            cell_area))
    tracer2_l2 = np.sqrt(
        np.sum(
            np.square(tracer2_error) *
            cell_area) /
        np.sum(
            np.square(tracer2_exact) *
            cell_area))
    tracer3_l2 = np.sqrt(
        np.sum(
            np.square(tracer3_error) *
            cell_area) /
        np.sum(
            np.square(tracer3_exact) *
            cell_area))
    tracer1_mass0 = np.sum(cell_area * tracer1_exact)
    tracer2_mass0 = np.sum(cell_area * tracer2_exact)
    tracer3_mass0 = np.sum(cell_area * tracer3_exact)
    over1 = []
    under1 = []
    over2 = []
    under2 = []
    over3 = []
    under3 = []
    for i in range(dataset.sizes["Time"]):
        dmax1 = tracer1[i, :, lev] - tracer1_max
        dmax2 = tracer2[i, :, lev] - tracer2_max
        dmax3 = tracer3[i, :, lev] - tracer3_max
        dmin1 = tracer1[i, :, lev] - tracer1_min
        dmin2 = tracer2[i, :, lev] - tracer2_min
        dmin3 = tracer3[i, :, lev] - tracer3_min
        isover1 = dmax1 > 0
        isunder1 = dmin1 < 0
        isover2 = dmax2 > 0
        isunder2 = dmin2 < 0
        isover3 = dmax3 > 0
        isunder3 = dmin3 < 0
        over1.append(np.amax(dmax1 * isover1) /
                     (tracer1_max - tracer1_min))
        under1.append(np.amax(-dmin1 * isunder1) /
                      (tracer1_max - tracer1_min))
        over2.append(np.amax(dmax2 * isover2) /
                     (tracer2_max - tracer2_min))
        under2.append(np.amax(-dmin2 * isunder2) /
                      (tracer2_max - tracer2_min))
        over3.append(np.amax(dmax3 * isover3) /
                     (tracer3_max - tracer3_min))
        under3.append(np.amax(-dmin3 * isunder3) /
                      (tracer3_max - tracer3_min))
    tracer1_mass12 = np.sum(cell_area * tracer1[tidx, :, lev])
    tracer2_mass12 = np.sum(cell_area * tracer2[tidx, :, lev])
    tracer3_mass12 = np.sum(cell_area * tracer3[tidx, :, lev])
    tracer1_masserr = np.abs(tracer1_mass0 - tracer1_mass12) / tracer1_mass0
    tracer2_masserr = np.abs(tracer2_mass0 - tracer2_mass12) / tracer2_mass0
    tracer3_masserr = np.abs(tracer3_mass0 - tracer3_mass12) / tracer3_mass0
    filament_tau = np.linspace(0, 1, 21)
    filament_area = np.zeros(21)
    filament_area0 = np.ones(21)
    for i, tau in enumerate(filament_tau):
        cells_above_tau = tracer2[tidx_filament, :, lev] >= tau
        cells_above_tau0 = tracer2[0, :, lev] >= tau
        filament_area[i] = np.sum(cell_area * cells_above_tau)
        filament_area0[i] = np.sum(cells_above_tau0 * cell_area)
    filament_norm = filament_area / filament_area0

    result = dict()
    result["tracer1"] = {
        "linf": tracer1_linf,
        "l2": tracer1_l2,
        "over": over1,
        "under": under1,
        "mass": tracer1_masserr}
    result["tracer2"] = {
        "linf": tracer2_linf,
        "l2": tracer2_l2,
        "over": over2,
        "under": under2,
        "filament": filament_norm,
        "mass": tracer2_masserr}
    result["tracer3"] = {
        "linf": tracer3_linf,
        "l2": tracer3_l2,
        "over": over3,
        "under": under3,
        "mass": tracer3_masserr}
    return result


def _make_convergence_arrays(tcdata):
    """
    Collects data from a set of test case runs at different resolutions
    to use for convergence data analysis and plotting.

    Parameters
    ----------
    tcdata : dict
        a dictionary whose keys are the resolution values for a
        ``sphere_transport`` test case

    Returns
    -------
    dlambda : list
        an array of increasing appx. mesh sizes

    linf1 : list
        the linf error of tracer1 for each resolution/mesh size pair

    linf2 : list
        the linf error of tracer2 for each resolution/mesh size pair

    linf3 : list
        the linf error of tracer3 for each resolution/mesh size pair

    l21 : list
        the l2 error of tracer1 for each resolution/mesh size pair

    l22 : list
        the l2 error of tracer2 for each resolution/mesh size pair

    l23 : list
        the l2 error of tracer3 for each resolution/mesh size pair

    """
    rvals = sorted(tcdata.keys())
    rvals.reverse()
    dlambda = []
    linf1 = []
    linf2 = []
    linf3 = []
    l21 = []
    l22 = []
    l23 = []
    u1 = []
    o1 = []
    u2 = []
    o2 = []
    u3 = []
    o3 = []
    mass1 = []
    mass2 = []
    mass3 = []
    for r in rvals:
        dlambda.append(tcdata[r]['appx_mesh_size'])
        linf1.append(tcdata[r]['err']['tracer1']['linf'])
        linf2.append(tcdata[r]['err']['tracer2']['linf'])
        linf3.append(tcdata[r]['err']['tracer3']['linf'])
        l21.append(tcdata[r]['err']['tracer1']['l2'])
        l22.append(tcdata[r]['err']['tracer2']['l2'])
        l23.append(tcdata[r]['err']['tracer3']['l2'])
        u1.append(np.array(tcdata[r]['err']['tracer1']['under']))
        o1.append(np.array(tcdata[r]['err']['tracer1']['over']))
        u2.append(np.array(tcdata[r]['err']['tracer2']['under']))
        o2.append(np.array(tcdata[r]['err']['tracer2']['over']))
        u3.append(np.array(tcdata[r]['err']['tracer3']['under']))
        o3.append(np.array(tcdata[r]['err']['tracer3']['over']))
        mass1.append(tcdata[r]['err']['tracer1']['mass'])
        mass2.append(tcdata[r]['err']['tracer2']['mass'])
        mass3.append(tcdata[r]['err']['tracer3']['mass'])
    return dlambda, linf1, linf2, linf3, l21, l22, l23, u1, o1, \
        u2, o2, u3, o3, mass1, mass2, mass3


def _print_data_as_csv(tcdata):
    """
    Print test case data in csv format

    Parameters
    ----------
    tcdata : dict
        a dictionary whose keys are the resolution values for a
        ``sphere_transport`` test case
    """
    rvals = sorted(tcdata.keys())
    rvals.reverse()
    dlambda, linf1, linf2, linf3, l21, l22, l23, u1, o1, u2, o2, u3, o3, \
        mass1, mass2, mass3 = _make_convergence_arrays(tcdata)
    headers = [
        "res",
        "dlambda",
        "linf1",
        "linf2",
        "linf3",
        "l21",
        "l22",
        "l23",
        "under1",
        "over1",
        "under2",
        "over2",
        "under3",
        "over3",
        "mass1",
        "mass2",
        "mass3"]
    data = np.stack((rvals,
                     dlambda,
                     linf1,
                     linf2,
                     linf3,
                     l21,
                     l22,
                     l23,
                     np.amax(np.abs(u1), axis=1),
                     np.amax(np.abs(o1), axis=1),
                     np.amax(np.abs(u2), axis=1),
                     np.amax(np.abs(o2), axis=1),
                     np.amax(np.abs(u3), axis=1),
                     np.amax(np.abs(o3), axis=1),
                     mass1,
                     mass2,
                     mass3), axis=1)
    df = pd.DataFrame(data, columns=headers)
    df.to_csv('convergence.csv', index=False)


def _plot_convergence(
        ax,
        tcname,
        dlambda,
        resvals,
        linf1,
        l21,
        linf2,
        l22,
        linf3,
        l23):
    """
    Creates a convergence plot for a test case from the ``sphere_transport``
    test group.

    Parameters
    ----------
    ax : matplotlib.Axes
        A matplotlib Axes instance

    tcname : str
        The name of the test case

    dlambda : numpy.ndarray
        An array of mesh size values

    resvals : numpy.ndarray
        An integer array of resolution values, e.g., [120, 240]

    linf1 : numpy.ndarray
        the linf error for tracer1

    l21 : numpy.ndarray
        the l2 error for tracer1

    linf2 : numpy.ndarray
        the linf error for tracer2

    l22 : numpy.ndarray
        the l2 error for tracer2

    linf3 : numpy.ndarray
        the linf error for tracer3

    l23 : numpy.ndarray
        the l2 error for tracer3
    """
    mSize = 8.0
    mWidth = mSize / 4
    prop_cycle = plt.rcParams['axes.prop_cycle']
    colors = prop_cycle.by_key()['color']
    o1ref = 5 * np.array(dlambda)
    o2ref = 50 * np.square(dlambda)
    ax.loglog(
        dlambda,
        linf1,
        '+:',
        color=colors[0],
        markersize=mSize,
        markerfacecolor='none',
        markeredgewidth=mWidth,
        label="tracer1_linf")
    ax.loglog(
        dlambda,
        l21,
        '+-',
        color=colors[0],
        markersize=mSize,
        markerfacecolor='none',
        markeredgewidth=mWidth,
        label="tracer1_l2")
    ax.loglog(
        dlambda,
        linf2,
        's:',
        color=colors[1],
        markersize=mSize,
        markerfacecolor='none',
        markeredgewidth=mWidth,
        label="tracer2_linf")
    ax.loglog(
        dlambda,
        l22,
        's-',
        color=colors[1],
        markersize=mSize,
        markerfacecolor='none',
        markeredgewidth=mWidth,
        label="tracer2_l2")
    ax.loglog(
        dlambda,
        linf3,
        'v:',
        color=colors[2],
        markersize=mSize,
        markerfacecolor='none',
        markeredgewidth=mWidth,
        label="tracer3_linf")
    ax.loglog(
        dlambda,
        l23,
        'v-',
        color=colors[2],
        markersize=mSize,
        markerfacecolor='none',
        markeredgewidth=mWidth,
        label="tracer3_l2")
    ax.loglog(dlambda, o1ref, 'k--', label="1st ord.")
    ax.loglog(dlambda, o2ref, 'k-.', label="2nd ord.")
    ax.set_xticks(dlambda)
    ax.set_xticklabels(resvals)
    ax.tick_params(which='minor', labelbottom=False)
    ax.set(title=tcname, xlabel='Resolution (km)', ylabel='Relative error')
    ax.legend(bbox_to_anchor=(1.05, 0.5), loc='center left')
