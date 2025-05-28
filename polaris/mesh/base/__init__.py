from polaris.mesh.base.uniform import add_uniform_spherical_base_mesh_step


def get_base_mesh_steps():
    """
    Get a list of supported base mesh steps from the mesh component

    Returns
    -------
    base_mesh_steps : list of polaris.mesh.spherical.BaseMeshStep
        All supported base mesh steps in the mesh component
    """
    resolutions = {
        'icos': [480.0, 240.0, 120.0, 60.0, 30.0],
        'qu': [480.0, 240.0, 210.0, 180.0, 150.0, 120.0, 90.0, 60.0, 30.0],
    }

    base_mesh_steps = []
    for prefix, res_list in resolutions.items():
        icosahedral = prefix == 'icos'
        for resolution in res_list:
            base_mesh_step, _ = add_uniform_spherical_base_mesh_step(
                resolution=resolution,
                icosahedral=icosahedral,
            )
            base_mesh_steps.append(base_mesh_step)

    # Add more base meshes here

    return base_mesh_steps
