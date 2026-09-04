import json
import os

from polaris import Step

# the conservation budgets summarized for each forward step, in the order
# they appear in the summary log file
BUDGETS = ['mass', 'salt', 'energy']


class ConservationSummary(Step):
    """
    A step that gathers the conservation errors from each of the ``thermo``
    forward steps into a single log file listing the forward step name and
    the mass, salt and energy errors.

    Attributes
    ----------
    forward_steps : dict
        A mapping from forward step name to the path of that step's work
        directory relative to the base work directory
    """

    def __init__(self, component, indir, forward_steps):
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
        self.add_output_file('conservation_summary.log')

    def run(self):
        """
        Write a log file listing the conservation error for each forward step
        """
        lines = [
            'Conservation errors for each thermo forward step',
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
