import configparser
import os
import re
import tomllib

import pytest
from ruamel.yaml import YAML

#: Packages whose conda name in ``deploy/pixi.toml.j2`` differs from the
#: name pip knows them by in ``pyproject.toml``
CONDA_NAMES = {
    'matplotlib': 'matplotlib-base',
}

#: Packages the mypy hook installs that are not polaris dependencies.  Type
#: stubs exist only for the checker, so ``pyproject.toml`` has nothing to
#: agree with, but the deployed environment does install them.
STUBS_ONLY = {'types-requests'}

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _split(requirement):
    """Split a requirement into its name and its version constraint."""
    for index, char in enumerate(requirement):
        if char in '=<>!~[ ':
            return requirement[:index], requirement[index:].strip()
    return requirement, ''


def _normalize(constraint):
    """Put a conda and a pip constraint into the same form."""
    constraint = constraint.strip().strip('"')
    # conda spells "any version" as *, pip by saying nothing
    return '' if constraint == '*' else constraint


def _polaris_dependencies():
    """The constraints in ``pyproject.toml``, by pip name."""
    with open(os.path.join(_ROOT, 'pyproject.toml'), 'rb') as data:
        pyproject = tomllib.load(data)
    return dict(
        _split(entry) for entry in pyproject['project']['dependencies']
    )


def _deploy_dependencies():
    """
    The constraints the deployed environment is built from, by conda name

    ``deploy/pixi.toml.j2`` is a template whose versions come from
    ``deploy/pins.cfg``, and mache combines the two when it deploys.  The
    pins are substituted here rather than rendering the template, so that
    the jinja conditionals -- which depend on the platform and on how the
    environment was asked for -- do not have to be answered.
    """
    pins = configparser.ConfigParser()
    pins.read(os.path.join(_ROOT, 'deploy', 'pins.cfg'))
    values = {}
    for section in pins.sections():
        values.update(dict(pins.items(section)))

    with open(os.path.join(_ROOT, 'deploy', 'pixi.toml.j2')) as data:
        template = data.read()

    dependencies = {}
    in_dependencies = False
    for line in template.split('\n'):
        stripped = line.strip()
        if stripped.startswith('['):
            in_dependencies = stripped == '[dependencies]'
            continue
        if not in_dependencies or not stripped or stripped.startswith('#'):
            continue
        if stripped.startswith('{%') or stripped.startswith('{#'):
            continue
        match = re.match(r'^"?([A-Za-z0-9_.\-]+)"?\s*=\s*(.+)$', stripped)
        if match is None:
            continue
        name, value = match.groups()
        # a table entry pins the version alongside a build string
        table = re.search(r'version\s*=\s*"([^"]*)"', value)
        constraint = table.group(1) if table else value.strip().strip('"')
        # {{ pin }} placeholders come from pins.cfg
        constraint = re.sub(
            r'\{\{\s*(\w+)\s*\}\}',
            lambda m: values.get(m.group(1), m.group(0)),
            constraint,
        )
        dependencies[name] = constraint
    return dependencies


def _mypy_hook_dependencies():
    """The packages the mypy pre-commit hook installs."""
    with open(os.path.join(_ROOT, '.pre-commit-config.yaml')) as data:
        config = YAML(typ='safe').load(data)
    for repo in config['repos']:
        for hook in repo['hooks']:
            if hook['id'] == 'mypy':
                return dict(
                    _split(entry)
                    for entry in hook.get('additional_dependencies', [])
                )
    raise AssertionError('There is no mypy hook in .pre-commit-config.yaml')


def test_the_deploy_template_lists_the_polaris_dependencies():
    """
    ``deploy/`` is what most users get, so every polaris dependency has to
    be in the environment it builds.
    """
    deploy = _deploy_dependencies()
    missing = [
        name
        for name in _polaris_dependencies()
        if CONDA_NAMES.get(name, name) not in deploy
    ]
    assert not missing, (
        f'These are polaris dependencies but are not in '
        f'deploy/pixi.toml.j2, so a deployed environment would not have '
        f'them: {", ".join(sorted(missing))}.'
    )


@pytest.mark.parametrize('package', sorted(_polaris_dependencies()))
def test_pyproject_agrees_with_the_deployed_environment(package):
    """
    deploy/ is what most polaris users get, so it is the source of truth
    and pyproject.toml follows it.  Where the two name a version they have
    to name the same one, or a pip install and a deployed environment are
    two different environments wearing one set of version numbers.
    """
    deploy = _deploy_dependencies()
    conda_name = CONDA_NAMES.get(package, package)
    if conda_name not in deploy:
        pytest.skip(f'{package} is not in the deployed environment')
    assert _normalize(_polaris_dependencies()[package]) == _normalize(
        deploy[conda_name]
    ), (
        f'pyproject.toml asks for {package}'
        f'{_normalize(_polaris_dependencies()[package]) or " (any version)"} '
        f'but deploy/pixi.toml.j2 asks for {conda_name} '
        f'{_normalize(deploy[conda_name]) or "(any version)"}.  deploy/ is '
        f'the source of truth; change pyproject.toml to match it, or change '
        f'both.'
    )


@pytest.mark.parametrize('package', sorted(_mypy_hook_dependencies()))
def test_the_mypy_hook_pins_match_the_environment(package):
    """
    pre-commit installs the hook's dependencies into an environment of its
    own and cannot read a version from anywhere else, so the constraints in
    .pre-commit-config.yaml repeat what deploy/ and pyproject.toml say.  A
    hook pinned to a version polaris does not use checks against the wrong
    library, which is worse than not checking, because it still looks like
    it is working.
    """
    hook = _normalize(_mypy_hook_dependencies()[package])

    deploy = _deploy_dependencies()
    conda_name = CONDA_NAMES.get(package, package)
    assert conda_name in deploy, (
        f'The mypy hook installs "{package}" but deploy/pixi.toml.j2 has '
        f'no "{conda_name}", so the hook would check against a library the '
        f'deployed environment does not have.'
    )
    assert hook == _normalize(deploy[conda_name]), (
        f'The mypy hook pins {package}{hook} but deploy/pixi.toml.j2 asks '
        f'for {conda_name} {deploy[conda_name]}.'
    )

    if package in STUBS_ONLY:
        return
    polaris = _polaris_dependencies()
    assert package in polaris, (
        f'The mypy hook installs "{package}", which is not a polaris '
        f'dependency.  Add it to pyproject.toml, or to STUBS_ONLY if it is '
        f'only for the type checker.'
    )
    assert hook == _normalize(polaris[package]), (
        f'The mypy hook pins {package}{hook} but pyproject.toml asks for '
        f'{package}{polaris[package]}.'
    )


@pytest.mark.parametrize('package', sorted(STUBS_ONLY))
def test_stub_packages_are_not_polaris_dependencies(package):
    """A stub package is for the checker; shipping it would be a mistake."""
    assert package not in _polaris_dependencies()
