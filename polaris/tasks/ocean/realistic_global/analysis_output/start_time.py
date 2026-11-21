#: The time the runs of the analysis_output restart and sampling_convergence
#: tasks start, which the names of their time-mean files count from
START_TIME = '0001-01-01_00:00:00'


def check_start_time(config, task_name: str):
    """
    Raise unless ``start_time`` in ``[realistic_global_forward]`` is
    ``START_TIME``

    The restart and sampling_convergence tasks declare the time-mean files
    their runs write when the tasks are created, before a user's config is
    read, so the file names assume that start time.

    Parameters
    ----------
    config : polaris.config.PolarisConfigParser
        The config options of the step

    task_name : str
        The name of the task, for the error message
    """
    start_time = config.get('realistic_global_forward', 'start_time').strip()
    if start_time != START_TIME:
        raise ValueError(
            f'The analysis_output {task_name} task needs start_time = '
            f'{START_TIME} in [realistic_global_forward], not {start_time}, '
            f'since the names of its time-mean files assume it.'
        )
