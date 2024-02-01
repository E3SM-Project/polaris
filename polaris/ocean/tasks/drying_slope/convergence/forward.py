import numpy as np

from polaris.mesh.planar import compute_planar_hex_nx_ny
from polaris.ocean.convergence import ConvergenceForward


class Forward(ConvergenceForward):
    """
    A step for performing forward ocean component runs as part of drying slope
    test cases.

    Attributes
    ----------
    resolution : float
        The resolution of the test case in km
    """
    def __init__(self, component, name, resolution, subdir, init,
                 damping_coeff, coord_type, method,
                 drag_type='constant_and_rayleigh'):
        """
        Create a new test case

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        resolution : km
            The resolution of the test case in km

        subdir : str
            The subdirectory that the step belongs to

        init : polaris.Step
            The step which generates the mesh and initial condition
        """
        options = dict()
        if coord_type == 'single_layer':
            options['config_disable_thick_sflux'] = '.true.'
            options['config_disable_vel_hmix'] = '.true.'

        if method == 'ramp':
            options['config_zero_drying_velocity_ramp'] = '.true.'

        options['config_implicit_bottom_drag_type'] = drag_type
        # for drag types not specified here, defaults are used or given in
        # forward.yaml
        if drag_type == 'constant':
            options['config_implicit_constant_bottom_drag_coeff'] = '3.0e-3'
        elif drag_type == 'constant_and_rayleigh':
            # update the damping coefficient to the requested value *after*
            # loading forward.yaml
            options['config_Rayleigh_damping_coeff'] = damping_coeff

        options['config_tidal_forcing_model'] = 'monochromatic'
        super().__init__(component=component,
                         name=name, subdir=subdir,
                         resolution=resolution, mesh=init, init=init,
                         package='polaris.ocean.tasks.drying_slope',
                         yaml_filename='forward.yaml',
                         graph_filename='culled_graph.info',
                         output_filename='output.nc',
                         forcing=True, options=options,
                         validate_vars=['layerThickness', 'normalVelocity'])

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        section = self.config['drying_slope']
        lx = section.getfloat('lx')
        ly = np.sqrt(3.0) / 2.0 * lx
        nx, ny = compute_planar_hex_nx_ny(lx, ly, self.resolution)
        cell_count = nx * ny
        return cell_count

    def dynamic_model_config(self, at_setup):
        """
        Set the model time step from config options at setup and runtime

        Parameters
        ----------
        at_setup : bool
            Whether this method is being run during setup of the step, as
            opposed to at runtime
        """
        super().dynamic_model_config(at_setup=at_setup)
        config = self.config
        section = config['drying_slope']
        thin_film_thickness = section.getfloat('thin_film_thickness')

        options = dict()
        options['config_drying_min_cell_height'] = thin_film_thickness
        options['config_zero_drying_velocity_ramp_hmin'] = \
            thin_film_thickness
        options['config_zero_drying_velocity_ramp_hmax'] = \
            thin_film_thickness * 2.
        self.add_model_config_options(options=options)
