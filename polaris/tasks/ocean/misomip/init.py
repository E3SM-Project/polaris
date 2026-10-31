import os

from mpas_tools.cime.constants import constants
from mpas_tools.io import open_dataset

from polaris.tasks.ocean.isomip_plus.init import Init

#: The profiles of the initial condition and of the restoring in each
#: experiment.  IceOcean1ra continues from IceOcean1r, so only its restoring
#: is used.
PROFILES = {
    'ocean0': {'init': 'warm', 'restoring': 'warm'},
    'ocean1': {'init': 'cold', 'restoring': 'warm'},
    'ocean2': {'init': 'warm', 'restoring': 'cold'},
    'ocean3': {'init': 'warm', 'restoring': 'warm'},
    'ocean4': {'init': 'cold', 'restoring': 'cold'},
    'iceocean1r': {'init': 'cold', 'restoring': 'warm'},
    'iceocean1ra': {'init': 'cold', 'restoring': 'cold'},
}


class MisomipInit(Init):
    """
    A step for making the ocean's initial condition and forcing for a
    MISOMIP experiment, from the land-ice fields that E3SM's coupler
    delivers from MALI's geometry

    Every cell is kept, with a thin film under grounded ice.  The draft
    follows from the land-ice pressure with E3SM's gravity.
    """

    def __init__(
        self,
        component,
        subdir,
        ocean_mesh_step,
        topo_step,
        land_ice_fields_step,
        experiment,
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        subdir : str
            The subdirectory for the step

        ocean_mesh_step : polaris.Step
            The step that gave the ocean's mesh latitude and longitude,
            writing ``ocean_mesh.nc``

        topo_step : polaris.Step
            The step that remapped the protocol's bed to the ocean's mesh
            without smoothing

        land_ice_fields_step : polaris.Step
            The step that computed the land-ice fields on the ocean's mesh,
            writing ``land_ice_fields.nc``

        experiment : str
            One of the experiments in :py:data:`PROFILES`
        """
        super().__init__(
            component=component,
            indir=None,
            culled_mesh=ocean_mesh_step,
            topo=topo_step,
            experiment=experiment,
            thin_film=True,
            profiles=PROFILES[experiment],
            name='ocean_init',
            subdir=subdir,
        )
        self.gravity = constants['SHR_CONST_G']
        self.add_input_file(
            filename='land_ice_fields.nc',
            work_dir_target=os.path.join(
                land_ice_fields_step.path, 'land_ice_fields.nc'
            ),
        )

    def get_mesh_target(self, mesh_step):
        """
        Get the ocean's mesh with the projection's latitude and longitude

        Parameters
        ----------
        mesh_step : polaris.Step
            The step that gave the ocean's mesh latitude and longitude

        Returns
        -------
        target : str
            The path of the mesh, relative to the base work directory
        """
        return os.path.join(mesh_step.path, 'ocean_mesh.nc')

    def read_topography(self):
        """
        Read the protocol's bed and the land-ice fields from MALI

        Returns
        -------
        ds_topo : xarray.Dataset
            The bed and the land-ice fields, with a ``Time`` dimension
        """
        ds_bed = open_dataset('topography.nc')
        ds_topo = open_dataset('land_ice_fields.nc')
        # without the remapped bed's attributes, such as cell_measures,
        # which fields derived from it would otherwise carry into the
        # initial condition
        ds_topo['bedrockTopography'] = ds_bed.bedrockTopography.drop_attrs()
        return ds_topo
