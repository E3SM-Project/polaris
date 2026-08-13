"""
Tests that each single-column forward step writes the variables it validates
against a baseline.

A variable that a step lists in ``validate_vars`` but never writes to
``output.nc`` makes the baseline comparison fail no matter what the model
computes, so the two have to be kept in step with one another.
"""

import os
import tempfile
from importlib.resources import files as imp_res_files

from jinja2 import Template

from polaris.tasks.ocean import Ocean
from polaris.tasks.ocean.single_column import add_single_column_tasks
from polaris.yaml import PolarisYaml

# Omega field groups that supply each MPAS-Ocean variable name a step may
# validate.  layerThickness is not an Omega field of its own: it is derived
# in open_model_dataset() from PseudoThickness, which the State group
# supplies, and SpecVol, which the Eos group supplies.
REQUIRED_GROUPS = {
    'temperature': ['Tracers'],
    'salinity': ['Tracers'],
    'normalVelocity': ['State'],
    'layerThickness': ['State', 'Eos'],
}


# the task yaml files are templates; the values do not matter for this test
_TEMPLATE_REPLACEMENTS = dict(
    dt='0000_00:10:00',
    output_interval='0000_01:00:00',
    output_freq='3600',
)


def _read_history_contents(package, filename, template_replacements=None):
    """Return the Omega History stream ``Contents`` in a yaml file, or None"""
    text = imp_res_files(package).joinpath(filename).read_text()
    if template_replacements is not None:
        text = Template(text).render(**template_replacements)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_filename = os.path.join(tmpdir, 'model.yaml')
        with open(tmp_filename, 'w') as tmp_file:
            tmp_file.write(text)
        yaml = PolarisYaml.read(
            filename=tmp_filename,
            model='Omega',
            streams_section='IOStreams',
        )
    history = yaml.streams.get('History')
    if history is None:
        return None
    return history.get('Contents', [])


def _omega_history_contents(step):
    """Return the Omega History stream contents a step's yaml files ask for,
    or None if none of them define a History stream."""
    contents = None
    for entry in step.model_config_data:
        yaml_filename = entry.get('yaml')
        if yaml_filename is None:
            continue
        history = _read_history_contents(
            package=entry['package'],
            filename=yaml_filename,
            template_replacements=entry.get('template_replacements'),
        )
        if history is None:
            continue
        if contents is None:
            contents = []
        contents.extend(history)

    # the task-specific yaml is only added in dynamic_model_config(), which
    # doesn't run at setup, so read it directly from the task package
    task_package = getattr(step, 'task_package', None)
    if task_package is not None:
        history = _read_history_contents(
            package=task_package,
            filename='forward.yaml',
            template_replacements=_TEMPLATE_REPLACEMENTS,
        )
        if history is not None:
            if contents is None:
                contents = []
            contents.extend(history)
    return contents


def test_omega_history_supplies_the_validated_variables():
    """Tasks without an Omega History stream are not run with Omega and are
    skipped; the rest have to write what they validate."""
    component = Ocean()
    add_single_column_tasks(component)

    checked = 0
    for subdir, task in component.tasks.items():
        for step_name, step in task.steps.items():
            validate_vars = getattr(step, 'validate_vars', None)
            if not validate_vars:
                continue
            contents = _omega_history_contents(step)
            if contents is None:
                continue
            for variables in validate_vars.values():
                for variable in variables:
                    for group in REQUIRED_GROUPS.get(variable, []):
                        assert group in contents, (
                            f'{subdir}/{step_name} validates {variable} but '
                            f'its Omega History stream does not include the '
                            f'{group} group'
                        )
                        checked += 1

    # guard against the loop silently checking nothing
    assert checked > 0
