from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Experiment:
    """
    A MISMIP+ experiment

    Attributes
    ----------
    name : str
        The protocol's name for the experiment, such as ``Ice1r``

    start_from : str or None
        The name of the experiment whose end this one starts from, or
        ``None`` to start from the steady state

    years : int
        The length of the experiment in years

    melt : {'none', 'mismip', 'constant'}
        MALI's option for the melt rate under floating ice: none, the
        protocol's Eq. 17, or Ice2's constant rate beyond 480 km
    """

    name: str
    start_from: Optional[str]
    years: int
    melt: str

    @property
    def subdir(self):
        """
        The subdirectory of the experiment's task
        """
        return self.name.lower()


# the experiments in the order they must be added, so that each comes after
# the one it starts from
EXPERIMENTS = [
    Experiment(name='Ice0', start_from=None, years=100, melt='none'),
    Experiment(name='Ice1r', start_from=None, years=100, melt='mismip'),
    Experiment(name='Ice1ra', start_from='Ice1r', years=100, melt='none'),
    Experiment(name='Ice1rr', start_from='Ice1r', years=900, melt='mismip'),
    Experiment(name='Ice2r', start_from=None, years=100, melt='constant'),
    Experiment(name='Ice2ra', start_from='Ice2r', years=100, melt='none'),
    Experiment(name='Ice2rr', start_from='Ice2r', years=900, melt='constant'),
]
