from polaris.mesh.base.uniform import add_uniform_spherical_base_mesh_step


def get_base_mesh_steps():
    """
    Get a list of supported base mesh steps from the mesh component

    Returns
    -------
    base_mesh_steps : list of polaris.mesh.spherical.BaseMeshStep
        All supported base mesh steps in the mesh component
    """
    base_mesh_steps = []
    for icosahedral in [True, False]:
        for resolution in [480.0, 240.0, 120.0, 60.0, 30.0]:
            base_mesh_step, _ = add_uniform_spherical_base_mesh_step(
                resolution=resolution,
                icosahedral=icosahedral,
            )
            base_mesh_steps.append(base_mesh_step)

    # Add more base meshes here

    return base_mesh_steps
