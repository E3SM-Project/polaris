"""
Unit tests for the Galewsky jet's initial velocity and diagnostics on a
coarse icosahedral mesh.  The mesh is built with JIGSAW and
``MpasMeshConverter.x`` in a few seconds; the tests are skipped if the
converter is not available.
"""

import os
import shutil

import jigsawpy
import numpy as np
import pytest
from mpas_tools.io import open_dataset
from mpas_tools.logging import check_call
from mpas_tools.mesh.creation.jigsaw_to_netcdf import jigsaw_to_netcdf

from polaris.constants import get_constant
from polaris.tasks.ocean.galewsky_jet.diagnostics import (
    divergence,
    global_l2,
    relative_vorticity,
)
from polaris.tasks.ocean.galewsky_jet.initial_state import (
    jet_velocity,
    normal_velocity_from_streamfunction,
    streamfunction,
)

pytestmark = pytest.mark.skipif(
    shutil.which('MpasMeshConverter.x') is None,
    reason='MpasMeshConverter.x is needed to build a test mesh',
)

RADIUS = get_constant('mean_radius')
JET = dict(u_max=80.0, phi0=np.pi / 7.0, phi1=0.5 * np.pi - np.pi / 7.0)


@pytest.fixture(scope='module')
def ds_mesh(tmp_path_factory):
    """
    An icosahedral mesh with 4 subdivisions (2562 cells, about 480 km)
    """
    work_dir = tmp_path_factory.mktemp('icos_mesh')
    cwd = os.getcwd()
    os.chdir(work_dir)
    try:
        opts = jigsawpy.jigsaw_jig_t()
        opts.geom_file = 'geom.msh'
        opts.jcfg_file = 'icos.jig'
        opts.mesh_file = 'icos.msh'
        opts.verbosity = 0
        geom = jigsawpy.jigsaw_msh_t()
        geom.mshID = 'ellipsoid-mesh'
        geom.radii = RADIUS * 1e-3 * np.ones(3, float)
        jigsawpy.savemsh(opts.geom_file, geom)
        icos = jigsawpy.jigsaw_msh_t()
        jigsawpy.cmd.icosahedron(opts, 4, icos)
        jigsaw_to_netcdf(
            msh_filename='icos.msh',
            output_name='triangles.nc',
            on_sphere=True,
            sphere_radius=RADIUS,
        )
        check_call(['MpasMeshConverter.x', 'triangles.nc', 'mesh.nc'])
        ds = open_dataset('mesh.nc')
        ds.load()
    finally:
        os.chdir(cwd)
    return ds


def test_streamfunction_velocity_is_nondivergent(ds_mesh):
    psi = streamfunction(ds_mesh.latVertex.values, **JET)
    normal_velocity = normal_velocity_from_streamfunction(ds_mesh, psi)
    div = divergence(ds_mesh, normal_velocity)
    # round-off relative to the scale u_max / a
    assert np.abs(div).max() < 1e-12 * JET['u_max'] / RADIUS


def test_streamfunction_velocity_matches_jet(ds_mesh):
    psi = streamfunction(ds_mesh.latVertex.values, **JET)
    normal_velocity = normal_velocity_from_streamfunction(ds_mesh, psi)
    point_sampled = jet_velocity(ds_mesh.latEdge.values, **JET) * np.cos(
        ds_mesh.angleEdge.values
    )
    # the difference is truncation error, about 1.1 m/s at this resolution
    assert np.abs(normal_velocity - point_sampled).max() < 2.0


def test_solid_body_vorticity(ds_mesh):
    """
    u = u0 cos(phi) has vorticity 2 u0 sin(phi) / a
    """
    u0 = 20.0
    psi = -RADIUS * u0 * np.sin(ds_mesh.latVertex.values)
    normal_velocity = normal_velocity_from_streamfunction(ds_mesh, psi)
    vort = relative_vorticity(ds_mesh, normal_velocity)
    expected = 2.0 * u0 * np.sin(ds_mesh.latVertex.values) / RADIUS
    area = ds_mesh.areaTriangle.values
    error = global_l2(vort - expected, area) / global_l2(expected, area)
    assert error < 0.03


def test_divergence_of_meridional_flow(ds_mesh):
    """
    v = u0 cos(phi) northward has divergence -2 u0 sin(phi) / a
    """
    u0 = 20.0
    normal_velocity = (
        u0 * np.cos(ds_mesh.latEdge.values) * np.sin(ds_mesh.angleEdge.values)
    )
    div = divergence(ds_mesh, normal_velocity)
    expected = -2.0 * u0 * np.sin(ds_mesh.latCell.values) / RADIUS
    area = ds_mesh.areaCell.values
    error = global_l2(div - expected, area) / global_l2(expected, area)
    assert error < 0.03


def test_operators_broadcast_over_time(ds_mesh):
    psi = -RADIUS * 20.0 * np.sin(ds_mesh.latVertex.values)
    normal_velocity = normal_velocity_from_streamfunction(ds_mesh, psi)
    stacked = np.stack([normal_velocity, 2.0 * normal_velocity])
    vort = relative_vorticity(ds_mesh, stacked)
    assert vort.shape == (2, ds_mesh.sizes['nVertices'])
    np.testing.assert_allclose(vort[1], 2.0 * vort[0])
    div = divergence(ds_mesh, stacked)
    assert div.shape == (2, ds_mesh.sizes['nCells'])
