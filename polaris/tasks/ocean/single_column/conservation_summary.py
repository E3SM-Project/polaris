import json
import os

from polaris import Step
from polaris.ocean.conservation import (
    compute_flux_forcing,
    compute_frazil_fluxes,
    compute_total_energy,
    compute_total_mass,
    compute_total_salt,
    get_elapsed_seconds,
)

# the conservation budgets summarized for each forward step, in the order
# they appear in the summary log file
BUDGETS = ['mass', 'salt', 'energy']


class ConservationSummary(Step):
    """
    A step that gathers the conservation errors from each of a task's
    forward steps into a single log file listing the forward step name and
    the mass, salt and energy errors.

    Attributes
    ----------
    forward_steps : dict
        A mapping from forward step name to the path of that step's work
        directory relative to the base work directory
    """

    def __init__(
        self, component, indir, forward_steps, frazil_diagnostics=False
    ):
        """
        Create the step

        Parameters
        ----------
        component : polaris.Component
            The component the step belongs to

        indir : str
            The subdirectory that the task belongs to, that this step will
            go into a subdirectory of

        forward_steps : dict
            A mapping from forward step name to the path of that step's work
            directory relative to the base work directory
        """
        super().__init__(
            component=component, name='conservation_summary', indir=indir
        )
        self.forward_steps = dict(forward_steps)
        self.frazil_diagnostics = frazil_diagnostics
        self.add_output_file('conservation_summary.log')

    def run(self):
        """
        Write a log file listing the conservation error for each forward step
        """
        lines = [
            'Conservation errors for each forward step',
            '',
            f'{"forward step":<40s}{"budget interval":<32s}'
            + ''.join(f'{f"{budget} error":<16s}' for budget in BUDGETS),
        ]
        for name, path in self.forward_steps.items():
            filename = os.path.join(
                self.base_work_dir, path, 'property_check_results.json'
            )
            errors = _read_errors(filename)
            if not errors:
                lines.append(f'{name:<40s}{"no results found":<32s}')
                continue
            for interval, budget_errors in errors.items():
                error_strs = []
                for budget in BUDGETS:
                    error = budget_errors.get(budget)
                    if error is None:
                        error_strs.append(f'{"n/a":<16s}')
                    else:
                        error_strs.append(f'{error:<16.6e}')
                lines.append(
                    f'{name:<40s}{interval:<32s}' + ''.join(error_strs)
                )

        with open('conservation_summary.log', 'w') as handle:
            handle.write('\n'.join(lines) + '\n')

        self.logger.info('\n'.join(lines))

        if self.frazil_diagnostics:
            diagnostics = _frazil_diagnostics(
                self.component,
                self.base_work_dir,
                self.forward_steps,
                self.config,
            )
            with open('conservation_summary.log', 'a') as handle:
                handle.write('\nFrazil diagnostic terms\n')
                handle.write(diagnostics)
            self.logger.info('\nFrazil diagnostic terms\n%s', diagnostics)


def _frazil_diagnostics(component, base_work_dir, forward_steps, config):
    """Report domain-integrated forcing, frazil terms, and errors."""
    model = config.get('ocean', 'model')
    if model != 'omega':
        return f'Omega frazil fields unavailable for model {model}\n'

    lines = [
        'forward step budget       state delta       surface forcing     '
        'frazil term        unadjusted diff     adjusted diff      error',
    ]
    for name, path in forward_steps.items():
        results = _read_results(
            os.path.join(base_work_dir, path, 'property_check_results.json')
        )
        output_filename = os.path.join(base_work_dir, path, 'output.nc')
        mesh_filename = os.path.join(base_work_dir, path, 'mesh.nc')
        init_filename = os.path.join(base_work_dir, path, 'init.nc')
        output = component.open_model_dataset(
            output_filename, config=config, decode_times=True
        )
        mesh = component.open_model_dataset(mesh_filename, config=config)
        init = component.open_model_dataset(init_filename, config=config)
        dt = get_elapsed_seconds(output, time_index_end=-1)
        frazil = compute_frazil_fluxes(mesh, output)
        forcing = {
            budget: compute_flux_forcing(
                mesh, output, budget, dt, model=model, config=config
            )
            for budget in BUDGETS
        }
        state = {
            'mass': float(
                compute_total_mass(mesh, output.isel(Time=-1))
                - compute_total_mass(mesh, init.isel(Time=0))
            ),
            'salt': float(
                compute_total_salt(mesh, output.isel(Time=-1))
                - compute_total_salt(mesh, init.isel(Time=0))
            ),
            'energy': float(
                compute_total_energy(mesh, output.isel(Time=-1), model)
                - compute_total_energy(mesh, init.isel(Time=0), model)
            ),
        }
        for budget in BUDGETS:
            unadjusted = state[budget] - forcing[budget]
            adjusted = unadjusted - frazil[budget]
            result = results.get(budget, {})
            status = 'PASS' if result.get('passed', False) else 'FAIL'
            lines.append(
                f'{name} {budget:<8s} {state[budget]:>16.6e} '
                f'{forcing[budget]:>16.6e} {frazil[budget]:>16.6e} '
                f'{unadjusted:>16.6e} {adjusted:>16.6e} '
                f'{result.get("relative_error", float("nan")):>10.3e} '
                f'{status}'
            )
        output.close()
        mesh.close()
        init.close()

    return '\n'.join(lines) + '\n'


def _read_errors(filename):
    """
    Read the relative error for each budget and each conservation interval
    from a step's ``property_check_results.json``

    Parameters
    ----------
    filename : str
        The path to the results file

    Returns
    -------
    errors : dict of dict
        A mapping from a string describing the conservation interval to a
        mapping from budget name to relative error
    """
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename) as handle:
            results = json.load(handle)
    except json.JSONDecodeError:
        # the file is incomplete or corrupt, likely because the forward step
        # was interrupted while writing it
        return {}

    errors: dict = {}
    for result in results:
        interval = f'{result["baseline"]} to {result["time_index_end"]}'
        errors.setdefault(interval, {})
        errors[interval][result['property']] = result['relative_error']
    return errors


def _read_results(filename):
    """Read the final result for each budget from a property-check file."""
    if not os.path.exists(filename):
        return {}
    try:
        with open(filename) as handle:
            results = json.load(handle)
    except json.JSONDecodeError:
        return {}
    return {result['property']: result for result in results}
