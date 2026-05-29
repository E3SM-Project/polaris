import multiprocessing
import os

import xarray as xr
from geometric_features import GeometricFeatures
from geometric_features.aggregation import get_aggregator_by_name
from mpas_tools.cime.constants import constants
from mpas_tools.io import write_netcdf
from mpas_tools.mesh.mask import (
    compute_mpas_region_masks,
    compute_mpas_transect_masks,
)
from mpas_tools.parallel import create_pool

from polaris.step import Step

VALID_MASK_TYPES = {'cell', 'edge', 'vertex'}


class ComputeFeatureMasksStep(Step):
    """
    A step for creating region or transect masks on a standard MPAS mesh.
    """

    def __init__(
        self,
        component,
        name='compute_feature_masks',
        subdir=None,
        mesh_step=None,
        mesh_filename=None,
        mesh_name=None,
        mask_group=None,
    ):
        """
        Create a new feature-mask step.

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        name : str, optional
            The name of the step

        subdir : str, optional
            The subdirectory for the step

        mesh_step : polaris.Step, optional
            An upstream step that produces the mesh

        mesh_filename : str, optional
            The mesh filename, either from ``mesh_step`` or configurable
            task config

        mesh_name : str, optional
            The mesh name for output filenames and metadata

        mask_group : str, optional
            A group name supported by ``get_aggregator_by_name()``
        """
        super().__init__(
            component=component,
            name=name,
            subdir=subdir,
            cpus_per_task=None,
            min_cpus_per_task=None,
        )
        self.mesh_step = mesh_step
        self.mesh_filename = mesh_filename
        self.mesh_name = mesh_name
        self.mask_group = mask_group
        self.output_filename = None
        self.geojson_filename = None

    def setup(self):
        """
        Set up the step in the work directory, including linking inputs.
        """
        super().setup()
        section = self.config['feature_masks']
        mesh_filename = _resolve_optional_option(
            self.mesh_filename, section.get('mesh_filename')
        )
        mesh_name = _resolve_optional_option(
            self.mesh_name, section.get('mesh_name')
        )
        mask_group = _resolve_optional_option(
            self.mask_group, section.get('mask_group')
        )

        if self.mesh_step is None:
            if mesh_filename is not None:
                self.add_input_file(filename='mesh.nc', target=mesh_filename)
        else:
            mesh_filename = _require_option(mesh_filename, 'mesh_filename')
            self.add_input_file(
                filename='mesh.nc',
                work_dir_target=os.path.join(
                    self.mesh_step.path, mesh_filename
                ),
            )

        if mesh_name is not None and mask_group is not None:
            self._set_output_filenames(mesh_name, mask_group)
            self.add_output_file(filename=self.output_filename)
            self.add_output_file(filename=self.geojson_filename)

        self.cpus_per_task = section.getint('cpus_per_task')
        self.min_cpus_per_task = section.getint('min_cpus_per_task')

    def constrain_resources(self, available_resources):
        """
        Constrain resources based on available cores.
        """
        section = self.config['feature_masks']
        self.cpus_per_task = section.getint('cpus_per_task')
        self.min_cpus_per_task = section.getint('min_cpus_per_task')
        super().constrain_resources(available_resources)

    def runtime_setup(self):
        """
        Set up runtime filenames after the work-dir config has been edited.
        """
        self._resolve_runtime_config()

    def run(self):
        """
        Run the feature-mask step.
        """
        super().run()
        section = self.config['feature_masks']
        mesh_filename, mesh_name, mask_group = self._resolve_runtime_config()
        source_mesh_filename = mesh_filename

        fc_mask, prefix, date = build_mask_feature_collection(mask_group)
        fc_mask.to_geojson(self.geojson_filename)

        feature_object_type = get_feature_object_type(fc_mask)
        mask_types = get_mask_types(
            section.get('mask_types'), feature_object_type
        )
        subdivision_resolution = _get_optional_float(
            section.get('subdivision_resolution')
        )

        if self.mesh_step is None:
            open_mesh_filename = mesh_filename
        else:
            open_mesh_filename = 'mesh.nc'
        ds_mesh = self._open_mesh_dataset(open_mesh_filename)

        pool = None
        try:
            pool = create_mask_pool(
                process_count=self.cpus_per_task,
                method=section.get('multiprocessing_method'),
            )
            ds_masks = compute_feature_masks(
                ds_mesh=ds_mesh,
                fc_mask=fc_mask,
                feature_object_type=feature_object_type,
                mask_types=mask_types,
                logger=self.logger,
                pool=pool,
                chunk_size=section.getint('chunk_size'),
                show_progress=section.getboolean('show_progress'),
                subdivision_threshold=section.getfloat(
                    'subdivision_threshold'
                ),
                subdivision_resolution=subdivision_resolution,
                add_edge_sign=section.getboolean('add_edge_sign'),
            )
        finally:
            if pool is not None:
                pool.terminate()

        ds_masks.attrs['mesh_name'] = mesh_name
        ds_masks.attrs['mask_group'] = mask_group
        ds_masks.attrs['feature_object_type'] = feature_object_type
        ds_masks.attrs['geometric_features_prefix'] = prefix
        ds_masks.attrs['geometric_features_date'] = date
        ds_masks.attrs['source_mesh_filename'] = source_mesh_filename

        ds_masks = self._post_process_masks(ds_masks, ds_mesh, mask_group)
        self._write_mask_dataset(ds_masks, self.output_filename)

    def _open_mesh_dataset(self, filename):
        """
        Open a standard MPAS mesh dataset.
        """
        return xr.open_dataset(filename, decode_cf=False, decode_times=False)

    def _write_mask_dataset(self, ds_masks, filename):
        """
        Write a standard MPAS mask dataset.
        """
        write_netcdf(ds_masks, filename, logger=self.logger)

    def _post_process_masks(self, ds_masks, ds_mesh, mask_group):
        """
        Post-process computed masks before writing. Default is a no-op.
        Subclasses may override to augment the dataset.
        """
        return ds_masks

    def _resolve_runtime_config(self):
        """
        Resolve required runtime config and update expected outputs.
        """
        section = self.config['feature_masks']
        mesh_filename = _resolve_required_option(
            self.mesh_filename, section.get('mesh_filename'), 'mesh_filename'
        )
        mesh_name = _resolve_required_option(
            self.mesh_name, section.get('mesh_name'), 'mesh_name'
        )
        mask_group = _resolve_required_option(
            self.mask_group, section.get('mask_group'), 'mask_group'
        )

        self._set_output_filenames(mesh_name, mask_group)
        assert self.output_filename is not None
        assert self.geojson_filename is not None
        self.outputs = [
            os.path.abspath(os.path.join(self.work_dir, self.output_filename)),
            os.path.abspath(
                os.path.join(self.work_dir, self.geojson_filename)
            ),
        ]

        return mesh_filename, mesh_name, mask_group

    def _set_output_filenames(self, mesh_name, mask_group):
        """
        Set output filenames from mesh and mask-group names.
        """
        _, prefix, date = get_aggregator_by_name(mask_group)
        self.output_filename = get_feature_masks_filename(
            mesh_name=mesh_name, prefix=prefix, date=date
        )
        self.geojson_filename = f'{prefix}{date}.geojson'


def build_mask_feature_collection(mask_group):
    """
    Build the feature collection for a named mask group.

    Parameters
    ----------
    mask_group : str
        A group name supported by
        :func:`geometric_features.get_aggregator_by_name`

    Returns
    -------
    fc_mask : geometric_features.FeatureCollection
        The feature collection

    prefix : str
        The filename prefix for the mask group

    date : str
        The date stamp for the mask group
    """
    aggregation_function, prefix, date = get_aggregator_by_name(mask_group)
    gf = GeometricFeatures()
    fc_mask = aggregation_function(gf)
    return fc_mask, prefix, date


def get_feature_object_type(fc_mask):
    """
    Get the common object type in a feature collection.

    Parameters
    ----------
    fc_mask : geometric_features.FeatureCollection
        The feature collection

    Returns
    -------
    object_type : {'region', 'transect'}
        The common feature object type
    """
    object_types = set()
    for feature in fc_mask.features:
        properties = feature.get('properties', {})
        object_type = properties.get('object', None)
        if object_type is None:
            name = properties.get('name', '<unnamed>')
            raise ValueError(
                f'Feature {name} is missing the required object property.'
            )
        object_types.add(object_type)

    if len(object_types) == 0:
        raise ValueError('The mask feature collection is empty.')

    if len(object_types) > 1:
        object_types_str = ', '.join(sorted(object_types))
        raise ValueError(
            f'Mask feature collections must contain a single object type. '
            f'Found: {object_types_str}.'
        )

    object_type = object_types.pop()
    if object_type not in ['region', 'transect']:
        raise ValueError(
            f'Unsupported mask feature object type {object_type}. '
            f'Expected region or transect.'
        )

    return object_type


def get_mask_types(mask_types, feature_object_type):
    """
    Resolve and validate mask types.

    Parameters
    ----------
    mask_types : str or list of str
        Mask types from config or caller

    feature_object_type : {'region', 'transect'}
        The common feature object type

    Returns
    -------
    mask_types : tuple of str
        The resolved mask types
    """
    if isinstance(mask_types, str):
        mask_types = mask_types.strip()
        if mask_types == 'default':
            if feature_object_type == 'region':
                return ('cell', 'vertex')
            return ('cell', 'edge', 'vertex')
        mask_types = mask_types.split()

    mask_types = tuple(mask_types)
    invalid = sorted(set(mask_types) - VALID_MASK_TYPES)
    if invalid:
        invalid_str = ', '.join(invalid)
        valid_str = ', '.join(sorted(VALID_MASK_TYPES))
        raise ValueError(
            f'Invalid mask type(s): {invalid_str}. Valid mask types are: '
            f'{valid_str}.'
        )

    return mask_types


def get_feature_masks_filename(mesh_name, prefix, date):
    """
    Get the output filename for a feature-mask file.
    """
    return f'{mesh_name}_{prefix}{date}.nc'


def compute_feature_masks(
    ds_mesh,
    fc_mask,
    feature_object_type,
    mask_types,
    logger,
    pool,
    chunk_size,
    show_progress,
    subdivision_threshold,
    subdivision_resolution,
    add_edge_sign,
):
    """
    Compute masks for a region or transect feature collection.

    Parameters
    ----------
    ds_mesh : xarray.Dataset
        A standard MPAS mesh dataset

    fc_mask : geometric_features.FeatureCollection
        The mask features

    feature_object_type : {'region', 'transect'}
        The common feature object type

    mask_types : tuple of {'cell', 'edge', 'vertex'}
        The mask types to compute

    logger : logging.Logger
        Logger for progress output

    pool : multiprocessing.Pool
        Pool for parallel computation

    chunk_size : int
        Number of points to process per chunk

    show_progress : bool
        Whether to show progress bars

    subdivision_threshold : float
        Region polygon subdivision threshold in degrees

    subdivision_resolution : float or None
        Transect subdivision resolution in meters

    add_edge_sign : bool
        Whether to add transect edge signs

    Returns
    -------
    ds_masks : xarray.Dataset
        The computed masks
    """
    if feature_object_type == 'region':
        if add_edge_sign:
            raise ValueError(
                'add_edge_sign=True is only valid for transect masks.'
            )
        return compute_mpas_region_masks(
            dsMesh=ds_mesh,
            fcMask=fc_mask,
            maskTypes=mask_types,
            logger=logger,
            pool=pool,
            chunkSize=chunk_size,
            showProgress=show_progress,
            subdivisionThreshold=subdivision_threshold,
        )

    if add_edge_sign and 'edge' not in mask_types:
        raise ValueError(
            'add_edge_sign=True requires edge to be included in mask_types.'
        )

    return compute_mpas_transect_masks(
        dsMesh=ds_mesh,
        fcMask=fc_mask,
        earthRadius=constants['SHR_CONST_REARTH'],
        maskTypes=mask_types,
        logger=logger,
        pool=pool,
        chunkSize=chunk_size,
        showProgress=show_progress,
        subdivisionResolution=subdivision_resolution,
        addEdgeSign=add_edge_sign,
    )


def create_mask_pool(process_count, method):
    """
    Create a multiprocessing pool for mask creation.
    """
    try:
        return create_pool(process_count=process_count, method=method)
    except RuntimeError:
        # The start method may already be fixed in a long-lived Python
        # process, such as a test runner.
        if process_count is None:
            process_count = multiprocessing.cpu_count()
        else:
            process_count = min(process_count, multiprocessing.cpu_count())
        if process_count <= 1:
            return None
        context = multiprocessing.get_context()
        return context.Pool(process_count)


def _resolve_required_option(constructor_value, config_value, option):
    value = _resolve_optional_option(constructor_value, config_value)
    return _require_option(value, option)


def _resolve_optional_option(constructor_value, config_value):
    value = constructor_value
    if value is None:
        value = config_value
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        if value == '' or value == '<<<missing>>>':
            return None
    return value


def _require_option(value, option):
    if value is None:
        raise ValueError(f'[feature_masks] {option} must be provided.')
    return value


def _get_optional_float(value):
    if value is None or value.lower() == 'none':
        return None
    return float(value)
