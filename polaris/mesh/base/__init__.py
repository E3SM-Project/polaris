from typing import Dict, List, Tuple

from polaris.mesh.base.add import add_spherical_base_mesh_step


def get_base_mesh_steps():
    """
    Get a list of supported base mesh steps from the mesh component

    Returns
    -------
    base_mesh_steps : list of polaris.mesh.spherical.BaseMeshStep
        All supported base mesh steps in the mesh component
    """
    uniform_res: Dict[str, List[float]] = {
        'icos': [480.0, 240.0, 120.0, 60.0, 30.0],
        'qu': [480.0, 240.0, 210.0, 180.0, 150.0, 120.0, 90.0, 60.0, 30.0],
    }

    # Add more variable resolution base meshes here
    variable_res: Dict[str, List[Tuple[float, float]]] = {
        'so': [(12.0, 30.0)],
    }

    base_mesh_steps = []
    for prefix, uniform_res_list in uniform_res.items():
        for resolution in uniform_res_list:
            base_mesh_step, _ = add_spherical_base_mesh_step(
                prefix=prefix, min_res=resolution
            )
            base_mesh_steps.append(base_mesh_step)

    for prefix, variable_res_list in variable_res.items():
        for min_res, max_res in variable_res_list:
            base_mesh_step, _ = add_spherical_base_mesh_step(
                prefix=prefix,
                min_res=min_res,
                max_res=max_res,
            )
            base_mesh_steps.append(base_mesh_step)

    return base_mesh_steps
