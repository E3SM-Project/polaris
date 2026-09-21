import json
import os

import numpy as np
import xarray as xr

from polaris import Step

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
                self.base_work_dir, self.forward_steps, self.config
            )
            with open('conservation_summary.log', 'a') as handle:
                handle.write('\nFrazil diagnostic terms\n')
                handle.write(diagnostics)
            self.logger.info('\nFrazil diagnostic terms\n%s', diagnostics)


def _frazil_diagnostics(base_work_dir, forward_steps, config):
    """Integrate Omega frazil fluxes and report existing check errors."""
    model = config.get('ocean', 'model')
    if model != 'omega':
        return f'Omega frazil fields unavailable for model {model}\n'

    lines = [
        'forward step                 mass (kg)       salt (kg)       '
        'energy (J)      conservation errors',
    ]
    for name, path in forward_steps.items():
        errors = _read_errors(
            os.path.join(base_work_dir, path, 'property_check_results.json')
        )
        last_errors = {}
        for budget_errors in errors.values():
            last_errors.update(budget_errors)
        output_filename = os.path.join(base_work_dir, path, 'output.nc')
        output = xr.open_dataset(output_filename, decode_times=False)
        mesh_filename = os.path.join(base_work_dir, path, 'culled_mesh.nc')
        mesh = xr.open_dataset(mesh_filename, decode_times=False)
        times = np.asarray(output['time'].values, dtype=float)
        interval = np.diff(np.concatenate(([0.0], times)))
        area = np.asarray(mesh['areaCell'].values, dtype=float)
        values = []
        for field in (
            'FrazilOcnDtFrazilMass',
            'FrazilOcnDtFrazilSalt',
            'FrazilOcnDtFrazilEnergy',
        ):
            flux = np.asarray(output[field].values, dtype=float)
            values.append(float(np.sum(flux * interval[:, None] * area)))
        lines.append(
            f'{name:<28s}{values[0]:>16.6e}{values[1]:>16.6e}'
            f'{values[2]:>16.6e} '
            f'mass={last_errors.get("mass", float("nan")):.3e} '
            f'salt={last_errors.get("salt", float("nan")):.3e} '
            f'energy={last_errors.get("energy", float("nan")):.3e}'
        )
        output.close()
        mesh.close()

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
