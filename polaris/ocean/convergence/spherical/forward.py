from polaris.ocean.convergence import ConvergenceForward


class SphericalConvergenceForward(ConvergenceForward):
    """
    A step for performing forward ocean component runs as part of a spherical
    convergence test

    Attributes
    ----------
    resolution : float
        The resolution of the (uniform) mesh in km

    package : Package
        The package name or module object that contains the YAML file

    yaml_filename : str
        A YAML file that is a Jinja2 template with model config options

    """

    def __init__(self, component, name, subdir, resolution, base_mesh, init,
                 package, yaml_filename='forward.yaml', options=None,
                 output_filename='output.nc', validate_vars=None):
        """
        Create a new step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str
            The name of the step

        subdir : str
            The subdirectory for the step

        resolution : float
            The resolution of the (uniform) mesh in km

        package : Package
            The package name or module object that contains the YAML file

        yaml_filename : str, optional
            A YAML file that is a Jinja2 template with model config options

        options : dict, optional
            A dictionary of options and value to replace model config options
            with new values

        output_filename : str, optional
            The output file that will be written out at the end of the forward
            run

        validate_vars : list of str, optional
            A list of variables to validate against a baseline if requested
        """
        super().__init__(component=component, name=name, subdir=subdir,
                         resolution=resolution, base_mesh=base_mesh,
                         init=init, package=package,
                         yaml_filename=yaml_filename,
                         output_filename=output_filename,
                         validate_vars=validate_vars)

    def compute_cell_count(self):
        """
        Compute the approximate number of cells in the mesh, used to constrain
        resources

        Returns
        -------
        cell_count : int or None
            The approximate number of cells in the mesh
        """
        # use a heuristic based on QU30 (65275 cells) and QU240 (10383 cells)
        cell_count = 6e8 / self.resolution**2
        return cell_count
