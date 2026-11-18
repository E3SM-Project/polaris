import os

import matplotlib.pyplot as plt
import xarray as xr

from polaris.ocean.model import OceanIOStep
from polaris.viz import load_insets, plot_inset, plot_inset_overviews


class MeshReviewStep(OceanIOStep):
    """
    A step for plotting the mesh and bottom depth in regional insets, for
    reviewing how well a mesh resolves coastlines and bathymetry

    Each file is a path relative to the base work directory, or an absolute
    path.  A file that isn't passed to the constructor comes from the option
    of the same name in the ``mesh_review`` config section.

    Attributes
    ----------
    init_filename : str or None
        The initial state

    mesh_filename : str or None
        The MPAS mesh, if not the initial state

    vert_coord_filename : str or None
        The vertical coordinate, read only if the initial state has no
        ``bottomDepth`` (as for Omega)
    """

    def __init__(
        self,
        component,
        subdir,
        init_filename=None,
        mesh_filename=None,
        vert_coord_filename=None,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the step belongs to

        subdir : str
            The subdirectory for the step

        init_filename : str, optional
            The initial state

        mesh_filename : str, optional
            The MPAS mesh, if not the initial state

        vert_coord_filename : str, optional
            The vertical coordinate, read only if the initial state has no
            ``bottomDepth`` (as for Omega)
        """
        super().__init__(
            component=component, name='viz_mesh_review', subdir=subdir
        )
        self.init_filename = init_filename
        self.mesh_filename = mesh_filename
        self.vert_coord_filename = vert_coord_filename

    def setup(self):
        """
        Add the mesh, initial state and inset definitions as inputs
        """
        super().setup()
        section = self.config['mesh_review']
        init_filename = self.init_filename or section.get('init_filename')
        mesh_filename = (
            self.mesh_filename or section.get('mesh_filename') or init_filename
        )
        vert_coord_filename = self.vert_coord_filename or section.get(
            'vert_coord_filename'
        )

        # an absolute path is unchanged when joined to the base work directory
        self.add_init_input_file(work_dir_target=init_filename)
        self.add_horiz_mesh_input_file(work_dir_target=mesh_filename)
        if vert_coord_filename:
            self.add_vert_coord_input_file(work_dir_target=vert_coord_filename)
        self.add_input_file(
            filename='insets.yaml', package='polaris.tasks.ocean.mesh_review'
        )

    def run(self):
        """
        Plot the overview maps and each inset
        """
        config = self.config
        section = config['mesh_review']

        ds_mesh = xr.open_dataset(self.get_horiz_mesh_filename())
        ds = self.open_model_dataset(
            self.get_init_filename(), decode_timedelta=False
        )
        if 'bottomDepth' not in ds:
            ds = self.open_vert_coord_dataset(ds, decode_timedelta=False)
        if 'Time' in ds.sizes:
            ds = ds.isel(Time=0)

        contourf_kwargs = {
            'levels': config.getlist('mesh_review', 'levels', dtype=float),
            'cmap': section.get('cmap'),
            # cells above sea level are culled, so depths are never negative
            'extend': 'max',
        }
        contour_kwargs = {
            'levels': config.getlist('mesh_review', 'contours', dtype=float),
        }

        insets = load_insets('insets.yaml')
        os.makedirs('output', exist_ok=True)
        plot_inset_overviews(ds_mesh, insets, output_dir='output')
        for inset in insets:
            fig, _ = plot_inset(
                ds_mesh,
                ds.bottomDepth,
                inset,
                'Bottom depth (m)',
                filename=f'output/inset_{inset.index:02d}.png',
                contourf_kwargs=contourf_kwargs,
                contour_kwargs=contour_kwargs,
            )
            plt.close(fig)
