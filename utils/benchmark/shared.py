"""
Small helpers shared by the benchmark driver modules.

These are intentionally self-contained so that ``utils/benchmark`` does
not depend on the other utilities in ``utils/``.
"""

import logging
import os
import subprocess
import sys


def to_abs(path, base_path):
    """
    Convert a relative path to an absolute path

    Parameters
    ----------
    path : str
        A relative or absolute path
    base_path : str
        The base path to use to convert relative paths to absolute paths

    Returns
    -------
    path : str
        The original ``path`` as an absolute path
    """
    if not os.path.isabs(path):
        path = os.path.normpath(os.path.join(base_path, path))
    return path


def get_logger(name, log_filename=None):
    """
    Get a logger that writes to stdout and, optionally, to a log file

    Parameters
    ----------
    name : str
        The name of the logger
    log_filename : str, optional
        The name of a file to write log output to in addition to stdout

    Returns
    -------
    logger : logging.Logger
        The logger
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    # start fresh in case this logger was already configured
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter('%(message)s')

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    if log_filename is not None:
        directory = os.path.dirname(os.path.abspath(log_filename))
        os.makedirs(directory, exist_ok=True)
        file_handler = logging.FileHandler(log_filename, 'w')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def check_call(args, logger=None, **kwargs):
    """
    Run a command, sending output to a logger if one is provided

    Parameters
    ----------
    args : str
        The command to run in a shell
    logger : logging.Logger, optional
        A logger to send output to
    kwargs
        Keyword arguments passed on to ``subprocess``

    Raises
    ------
    subprocess.CalledProcessError
        If the command returns a non-zero exit code
    """
    if logger is None:
        subprocess.check_call(args, shell=True, **kwargs)
        return

    process = subprocess.Popen(
        args,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        **kwargs,
    )
    assert process.stdout is not None
    for line in process.stdout:
        logger.info(line.decode('utf-8', errors='replace').rstrip('\n'))
    process.wait()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, args)


def check_output(args, cwd=None):
    """
    Run a command and return its stripped standard output

    Parameters
    ----------
    args : str
        The command to run in a shell
    cwd : str, optional
        The directory to run the command in

    Returns
    -------
    output : str
        The standard output of the command with whitespace stripped
    """
    output = subprocess.check_output(
        args, shell=True, cwd=cwd, stderr=subprocess.DEVNULL
    )
    return output.decode('utf-8').strip()


def print_commands(commands, header=None, logger=None):
    """
    Print a chain of shell commands in a readable form

    Parameters
    ----------
    commands : str
        A command or chain of commands joined by ``&&``
    header : str, optional
        A header to print above the commands
    logger : logging.Logger, optional
        A logger to print to instead of stdout
    """
    lines = []
    if header is not None:
        lines.append(72 * '-')
        lines.append(header)
        lines.append(72 * '-')
    pretty = commands.replace(' && ', '\n  ')
    lines.append(f'  {pretty}')
    text = '\n'.join(lines)
    if logger is None:
        print(text)
    else:
        logger.info(text)
