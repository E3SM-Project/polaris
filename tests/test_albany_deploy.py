import configparser
import importlib.util
import logging
import os
from types import SimpleNamespace

from jinja2 import Template
from ruamel.yaml import YAML

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_pm_gpu_builds_albany_for_gpus_only_with_gpu_compilers():
    """
    pm-gpu's CUDA variants apply to its GPU compilers, and its CPU compilers
    get the default variants from the pins
    """
    pins = _read_pins()
    ctx = _albany_context(
        machine='pm-gpu', pairs=[('gnugpu', 'mpich'), ('gnu', 'mpich')]
    )
    ctx.pins = pins

    _load_hooks().pre_spack(ctx)

    gnugpu = _render_library_specs(ctx, compiler='gnugpu', mpi='mpich')
    gnu = _render_library_specs(ctx, compiler='gnu', mpi='mpich')

    trilinos = pins['spack']['trilinos']
    albany = pins['spack']['albany']
    assert f'trilinos-for-albany@{trilinos}+cuda+ampere80+zen3' in gnugpu
    assert f'albany@{albany}+mpas~py+unit_tests+cuda+sfad sfadsize=12' in (
        gnugpu
    )
    default_albany = pins['spack']['albany_variants']
    assert f'trilinos-for-albany@{trilinos}' in gnu
    assert f'albany@{albany}{default_albany}' in gnu


def test_machine_wide_albany_variants_apply_to_every_compiler():
    """
    A machine's albany_variants apply to every compiler, unless the machine
    also sets them for one compiler
    """
    ctx = _albany_context(
        machine='chrysalis',
        pairs=[('gnu', 'openmpi'), ('intel', 'openmpi')],
        deploy={
            'albany_variants': '+mpas+debug',
            'intel_albany_variants': '+mpas+fpe',
        },
    )

    _load_hooks().pre_spack(ctx)

    assert ctx.pins['spack']['albany_variants_gnu'] == '+mpas+debug'
    assert ctx.pins['spack']['albany_variants_intel'] == '+mpas+fpe'


def _load_hooks():
    filename = os.path.join(_ROOT, 'deploy', 'hooks.py')
    spec = importlib.util.spec_from_file_location('deploy_hooks', filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _read_pins():
    parser = configparser.ConfigParser()
    parser.read(os.path.join(_ROOT, 'deploy', 'pins.cfg'))
    return {
        section: dict(parser.items(section)) for section in parser.sections()
    }


def _albany_context(machine, pairs, deploy=None):
    machine_config = configparser.ConfigParser()
    if deploy is None:
        machine_config.read(
            os.path.join(_ROOT, 'polaris', 'machines', f'{machine}.cfg')
        )
    else:
        machine_config.read_dict({'deploy': deploy})
    return SimpleNamespace(
        args=SimpleNamespace(with_albany=True, spack_path='/spack'),
        config={'spack': {}},
        machine=machine,
        machine_config=machine_config,
        pins=_read_pins(),
        runtime={
            'toolchain': {
                'pairs': [
                    {'compiler': compiler, 'mpi': mpi}
                    for compiler, mpi in pairs
                ]
            }
        },
        software='polaris',
        logger=logging.getLogger(__name__),
    )


def _render_library_specs(ctx, compiler, mpi):
    filename = os.path.join(_ROOT, 'deploy', 'spack.yaml.j2')
    with open(filename) as f:
        template = Template(f.read())
    rendered = template.render(
        pins=ctx.pins,
        spack=ctx.pins['spack'],
        pixi=ctx.pins['pixi'],
        all=ctx.pins['all'],
        software=ctx.software,
        machine=ctx.machine,
        compiler=compiler,
        mpi=mpi,
        exclude_packages=[],
        e3sm_hdf5_netcdf=True,
        use_e3sm_hdf5_netcdf=True,
    )
    return YAML(typ='safe').load(rendered)['library']
