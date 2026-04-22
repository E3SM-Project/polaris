from dataclasses import dataclass
from typing import Any

from geometric_features import GeometricFeatures

CRITICAL_LAND_BLOCKAGE_TAG = 'Critical_Land_Blockage'
CRITICAL_PASSAGE_TAG = 'Critical_Passage'


@dataclass(frozen=True)
class CriticalTransects:
    """
    Default critical transect collections shared across mesh workflows.

    Attributes
    ----------
    land_blockages : geometric_features.FeatureCollection
        Transects where land must be preserved

    passages : geometric_features.FeatureCollection
        Transects where ocean must be preserved
    """

    land_blockages: Any
    passages: Any


def load_default_critical_transects(
    gf: GeometricFeatures | None = None,
) -> CriticalTransects:
    """
    Load the default critical transects from ``geometric_features``.

    Parameters
    ----------
    gf : geometric_features.GeometricFeatures, optional
        A shared ``GeometricFeatures`` instance to reuse

    Returns
    -------
    polaris.mesh.spherical.critical_transects.CriticalTransects
        The shared critical land blockage and passage collections
    """
    if gf is None:
        gf = GeometricFeatures()

    gf.read(
        componentName='ocean',
        objectType='transect',
        tags=[CRITICAL_LAND_BLOCKAGE_TAG, CRITICAL_PASSAGE_TAG],
    )

    land_blockages = gf.read(
        componentName='ocean',
        objectType='transect',
        tags=[CRITICAL_LAND_BLOCKAGE_TAG],
    )
    passages = gf.read(
        componentName='ocean',
        objectType='transect',
        tags=[CRITICAL_PASSAGE_TAG],
    )

    return CriticalTransects(
        land_blockages=land_blockages,
        passages=passages,
    )
