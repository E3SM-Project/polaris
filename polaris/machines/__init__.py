import importlib.resources as imp_res
import os as os
import socket as socket
import sys as sys

from mache import discover_machine as mache_discover_machine

from polaris.config import PolarisConfigParser as PolarisConfigParser


def discover_machine(quiet=False):
    """
    Figure out the machine from the host name

    Parameters
    ----------
    quiet : bool, optional
        Whether to print warnings if the machine name is ambiguous

    Returns
    -------
    machine : str
        The name of the current machine
    """
    machine = mache_discover_machine(quiet=quiet)
    if machine is None:
        possible_hosts = _get_possible_hosts()
        hostname = socket.gethostname()
        for possible_machine, hostname_contains in possible_hosts.items():
            if hostname_contains in hostname:
                machine = possible_machine
                break
    return machine


def _get_possible_hosts():
    machine_contents = imp_res.contents('polaris.machines')
    possible_hosts = dict()
    for filename in machine_contents:
        if filename.endswith('.cfg'):
            machine = os.path.split(filename)[0]
            config = PolarisConfigParser()
            config.add_from_package('polaris.machines', filename)
            if config.has_section('discovery') and config.has_option(
                'discovery', 'hostname_contains'
            ):
                hostname_contains = config.get(
                    'discovery', 'hostname_contains'
                )
                possible_hosts[machine] = hostname_contains

    return possible_hosts
