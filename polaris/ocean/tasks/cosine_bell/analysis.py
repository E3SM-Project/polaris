import numpy as np
import xarray as xr

from polaris.ocean.convergence.spherical import SphericalConvergenceAnalysis


class Analysis(SphericalConvergenceAnalysis):
    """
    A step for analyzing the output from the cosine bell test case

    Attributes
    ----------
    resolutions : list of float
        The resolutions of the meshes that have been run

    icosahedral : bool
        Whether to use icosahedral, as opposed to less regular, JIGSAW
        meshes

    dependencies_dict : dict of dict of polaris.Steps
        The dependencies of this step
    """
    def __init__(self, component, resolutions, icosahedral, subdir,
                 dependencies):
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

        dependencies : dict of dict of polaris.Steps
            The dependencies of this step
        """
        # section = self.config['cosine_bell']
        # if icosahedral:
        #     conv_thresh = section.getfloat('icos_conv_thresh')
        #     conv_max = section.getfloat('icos_conv_max')
        # else:
        #     conv_thresh = section.getfloat('qu_conv_thresh')
        #     conv_max = section.getfloat('qu_conv_max')
        # This could come from spherical_convergence cfg section
        conv_thresh = 1.
        conv_max = 3.
        convergence_vars = {0: {'name': 'tracer1',
                                'title': 'tracer1',
                                'units': '',
                                'conv_thresh': conv_thresh,
                                'conv_max': conv_max,
                                'zidx': 0}}
        super().__init__(component=component, subdir=subdir,
                         resolutions=resolutions, dependencies=dependencies,
                         icosahedral=icosahedral,
                         convergence_vars=convergence_vars)

    def exact_solution(self, mesh_name, field_name='tracer1'):
        if field_name != 'tracer1':
            print(f'Variable {field_name} not available as an analytic '
                  'solution for the cosine_bell test case')

        config = self.config
        latCent = config.getfloat('cosine_bell', 'lat_center')
        lonCent = config.getfloat('cosine_bell', 'lon_center')
        radius = config.getfloat('cosine_bell', 'radius')
        psi0 = config.getfloat('cosine_bell', 'psi0')
        convergence_eval_time = config.getfloat('spherical_convergence',
                                                'convergence_eval_time')
        ds_mesh = xr.open_dataset(f'{mesh_name}_mesh.nc')
        ds_init = xr.open_dataset(f'{mesh_name}_init.nc')
        s_per_day = 86400.0
        # find new location of blob center
        # center is based on equatorial velocity
        R = ds_mesh.sphere_radius
        distTrav = 2.0 * np.pi * R / (s_per_day * convergence_eval_time)
        # distance in radians is
        distRad = distTrav / R
        newLon = lonCent + distRad
        if newLon > 2.0 * np.pi:
            newLon -= 2.0 * np.pi
        tracer = np.zeros_like(ds_init.tracer1[0, :, 0].values)
        latC = ds_init.latCell.values
        lonC = ds_init.lonCell.values
        # TODO replace this with great circle distance
        temp = R * np.arccos(np.sin(latCent) * np.sin(latC) +
                             np.cos(latCent) * np.cos(latC) * np.cos(
            lonC - newLon))
        mask = temp < radius
        tracer[mask] = (psi0 / 2.0 *
                        (1.0 + np.cos(3.1415926 * temp[mask] / radius)))
        return tracer
