"""
Lists of variables used to compare mesh files against a baseline.

These lists are kept in a dependency-light module so that both framework
steps (e.g. :py:class:`polaris.mesh.spherical.SphericalBaseStep`) and task
steps that cull or otherwise derive MPAS meshes can share them.
"""

#: Variables in an MPAS mesh file to compare against a baseline.  Only
#: variables present in both a base mesh and a culled mesh are included, so
#: that the same list can be used for either.
MPAS_MESH_VALIDATE_VARS = [
    'latCell',
    'lonCell',
    'xCell',
    'yCell',
    'zCell',
    'areaCell',
    'indexToCellID',
    'nEdgesOnCell',
    'cellsOnCell',
    'edgesOnCell',
    'verticesOnCell',
    'meshDensity',
    'latEdge',
    'lonEdge',
    'xEdge',
    'yEdge',
    'zEdge',
    'dcEdge',
    'dvEdge',
    'angleEdge',
    'indexToEdgeID',
    'nEdgesOnEdge',
    'cellsOnEdge',
    'edgesOnEdge',
    'verticesOnEdge',
    'weightsOnEdge',
    'latVertex',
    'lonVertex',
    'xVertex',
    'yVertex',
    'zVertex',
    'areaTriangle',
    'kiteAreasOnVertex',
    'indexToVertexID',
    'cellsOnVertex',
    'edgesOnVertex',
]

#: Variables in a lon/lat cell-width file to compare against a baseline
CELL_WIDTH_VALIDATE_VARS = ['cellWidth']
