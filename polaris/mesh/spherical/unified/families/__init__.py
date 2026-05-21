from typing import Protocol

from polaris.mesh.spherical.unified.families.default import (
    DefaultUnifiedMeshFamily,
    build_ocean_background_from_mode,
)
from polaris.mesh.spherical.unified.families.so_region import (
    SORegionUnifiedMeshFamily,
)


class UnifiedMeshFamily(Protocol):
    name: str

    def setup_sizing_field_step(self, step): ...

    def build_ocean_background(self, ds_coastline, section): ...


_FAMILY_LIST: list[UnifiedMeshFamily] = [
    DefaultUnifiedMeshFamily(),
    SORegionUnifiedMeshFamily(),
]

_FAMILIES: dict[str, UnifiedMeshFamily] = {
    family.name: family for family in _FAMILY_LIST
}


def get_unified_mesh_family(config):
    """
    Get the unified-mesh family object for a combined mesh config.
    """
    family_name = config.get('unified_mesh', 'mesh_family')
    try:
        return _FAMILIES[family_name]
    except KeyError as exc:
        valid_families = ', '.join(sorted(_FAMILIES))
        raise ValueError(
            f'Unexpected unified mesh family {family_name!r}. Valid '
            f'families are: {valid_families}'
        ) from exc


__all__ = [
    'build_ocean_background_from_mode',
    'get_unified_mesh_family',
]
