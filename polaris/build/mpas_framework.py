import importlib.resources
import os
import shlex

from jinja2 import Template


def get_framework_check(e3sm_base_dir, component_dir, build_config, clean):
    """
    Get shell code for a build script that decides whether an MPAS
    component's build must start with ``make clean``.

    The MPAS components in an E3SM checkout share one framework build in
    ``components/mpas-framework/src``.  MPAS's own check (the
    ``.mpas_core_<core>`` file in each component's directory) does not notice
    when another component built the framework last, and nothing notices a
    change of compiler.  The code sets ``polaris_needs_clean`` to ``true``
    when ``clean`` is requested, when the last build that Polaris made in the
    checkout had a different configuration, when the checkout was built
    outside of Polaris, or when another component was built more recently.
    It sets ``polaris_build_record`` and ``polaris_build_config`` so the
    script can record this build's configuration before making it.

    Builds of different components from one checkout at the same time still
    collide.

    Parameters
    ----------
    e3sm_base_dir : str
        The base of the E3SM checkout

    component_dir : str
        The directory of the component being built in the checkout (e.g.
        ``components/mpas-ocean`` within ``e3sm_base_dir``)

    build_config : dict
        The options that describe the build, such as the core, machine,
        compiler, MPI library, make target, make flags and load script

    clean : bool
        Whether a clean build was requested

    Returns
    -------
    check : str
        The shell code
    """
    config_text = ' '.join(
        f'{key}={str(value).strip()}' for key, value in build_config.items()
    )

    template_filename = importlib.resources.files('polaris.build').joinpath(
        'check_mpas_framework.template'
    )
    with open(str(template_filename), 'r', encoding='utf-8') as f:
        template = Template(f.read())

    return template.render(
        e3sm_base_dir=e3sm_base_dir,
        framework_dir=os.path.join(
            e3sm_base_dir, 'components', 'mpas-framework', 'src'
        ),
        component_dir=component_dir,
        build_config=shlex.quote(config_text),
        clean=clean,
    )
