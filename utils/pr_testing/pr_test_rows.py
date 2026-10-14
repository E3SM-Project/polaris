"""
The machine, compiler and MPI combinations that PR testing runs on
"""

import configparser
from dataclasses import dataclass
from importlib import resources
from typing import List, Optional, Tuple


@dataclass(frozen=True)
class Row:
    """
    A machine, compiler and MPI library to test on

    Attributes
    ----------
    machine : str
        The Polaris machine

    compiler : str
        The Polaris compiler

    mpi : str
        The MPI library

    template : str, optional
        The row's label in the PR template's testing checklist, if it has
        one

    model : str, optional
        The model the row tests, ``omega`` or ``mpas-ocean``, when rows of
        both are tested; ``None`` when the model goes without saying
    """

    machine: str
    compiler: str
    mpi: str
    template: Optional[str] = None
    model: Optional[str] = None

    @property
    def name(self) -> str:
        """The row as ``<machine>/<compiler>``, then ``/<model>`` if any"""
        name = f'{self.machine}/{self.compiler}'
        if self.model is not None:
            name = f'{name}/{self.model}'
        return name

    @property
    def label(self) -> str:
        """How reports name the row"""
        polaris = f'{self.machine}, {self.compiler}, {self.mpi}'
        if self.template is not None and self.template != polaris:
            polaris = f'{self.template} (Polaris `{self.compiler}`)'
        if self.model is not None:
            polaris = f'{polaris} ({MODEL_LABELS[self.model]})'
        return polaris


#: how reports name each model
MODEL_LABELS = {'omega': 'Omega', 'mpas-ocean': 'MPAS-Ocean'}


#: machines whose rows are tested from the same login nodes
SHARED_LOGIN_NODES = [{'pm-cpu', 'pm-gpu'}]

#: compilers Polaris has renamed, by machine and new name, so that a
#: baseline can run from a Polaris checkout from before the rename.  Aurora's
#: compilers are renamed with mache 5.0.0 (E3SM-Project/polaris#835).
FORMER_COMPILERS = {
    ('aurora', 'intel'): 'oneapi-ifx',
    ('aurora', 'intelgpu'): 'oneapi-ifxgpu',
}


def get_machine_rows(rows: List[Row], machine: str) -> List[Row]:
    """
    The rows a tester on a machine runs: those of the machine, and of any
    machine that shares its login nodes

    Parameters
    ----------
    rows : list of pr_test_rows.Row
        The rows to choose from

    machine : str
        The Polaris machine the tester is on

    Returns
    -------
    machine_rows : list of pr_test_rows.Row
        The tester's rows, in order
    """
    machines = get_login_machines(machine)
    return [row for row in rows if row.machine in machines]


def get_login_machines(machine: str) -> List[str]:
    """
    A machine and any machines that share its login nodes, sorted

    Parameters
    ----------
    machine : str
        The Polaris machine

    Returns
    -------
    machines : list of str
        The machines tested from the same login nodes
    """
    machines = {machine}
    for group in SHARED_LOGIN_NODES:
        if machine in group:
            machines |= group
    return sorted(machines)


def group_login_rows(rows: List[Row]) -> List[Tuple[List[str], List[Row]]]:
    """
    The rows grouped by the login nodes they are tested from

    Parameters
    ----------
    rows : list of pr_test_rows.Row
        The rows to group

    Returns
    -------
    groups : list of tuple
        The machines that share each group's login nodes and the group's
        rows, in the order the rows first appear
    """
    groups: List[Tuple[List[str], List[Row]]] = []
    for row in rows:
        if any(row in group_rows for _, group_rows in groups):
            continue
        machine_rows = get_machine_rows(rows, row.machine)
        machines = list(dict.fromkeys(r.machine for r in machine_rows))
        groups.append((machines, machine_rows))
    return groups


def get_polaris_mpi(machine: str, compiler: str) -> Optional[str]:
    """
    The MPI library Polaris uses with a compiler on a machine

    Parameters
    ----------
    machine : str
        The Polaris machine

    compiler : str
        The Polaris compiler

    Returns
    -------
    mpi : str, optional
        The MPI library, or ``None`` if Polaris does not support the
        compiler on the machine
    """
    filename = f'{machine}.cfg'
    try:
        text = (
            resources.files('polaris.machines')
            .joinpath(filename)
            .read_text(encoding='utf-8')
        )
    except (FileNotFoundError, OSError):
        return None
    parser = configparser.ConfigParser()
    parser.read_string(text)
    option = f'mpi_{compiler.replace("-", "_")}'
    value = parser.get('deploy', option, fallback='').strip()
    return value or None
