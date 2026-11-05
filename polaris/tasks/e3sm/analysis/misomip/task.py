from polaris import Task
from polaris.e3sm.analysis.case import E3smCase
from polaris.tasks.e3sm.analysis.misomip.comparison import RunComparison
from polaris.tasks.e3sm.analysis.misomip.conservation import (
    CouplerConservation,
    OceanVolumeBudget,
)
from polaris.tasks.e3sm.analysis.misomip.diagnostics import RunDiagnostics
from polaris.tasks.e3sm.analysis.misomip.exchange import ModelExchange
from polaris.tasks.e3sm.analysis.misomip.ice_sheet import IceSheetComparison
from polaris.tasks.e3sm.analysis.misomip.performance import RunPerformance
from polaris.tasks.e3sm.analysis.misomip.plots import RunPlots
from polaris.tasks.e3sm.analysis.misomip.protocol import (
    ProtocolFields,
    ProtocolMapStep,
)
from polaris.tasks.e3sm.analysis.misomip.publish import MisomipPublish
from polaris.tasks.e3sm.analysis.misomip.published import (
    PublishedComparison,
)
from polaris.tasks.e3sm.analysis.misomip.runs import (
    COUPLED_EXPERIMENTS,
    get_configured_runs,
    get_mean_months,
    runs_section,
)
from polaris.tasks.e3sm.analysis.misomip.yung2026 import (
    EXPERIMENTS as PUBLISHED_EXPERIMENTS,
)
from polaris.tasks.e3sm.analysis.misomip.yung2026 import get_yung2026_step

#: Labels of the runs in plot titles
RUN_LABELS = {'e3sm': 'E3SM', 'standalone': 'standalone'}


class MisomipAnalysisTask(Task):
    """
    A task that analyzes the E3SM and standalone runs of one MISOMIP
    experiment on one pair of meshes

    The task's steps are built from the config, once the user's config has
    been read: one set for each run the config names, with directories named
    for the months each run has, so analyzing more of a run gets new steps.

    Attributes
    ----------
    mesh_name : str
        The pair of meshes, such as ``misomip-o4km-li1km``

    experiment : str
        The experiment, such as ``ocean0``
    """

    def __init__(self, component, config, mesh_name, experiment):
        """
        Create the task

        Parameters
        ----------
        component : polaris.Component
            The e3sm/analysis component

        config : polaris.config.PolarisConfigParser
            The config shared by the MISOMIP analysis tasks

        mesh_name : str
            The pair of meshes

        experiment : str
            The experiment
        """
        subdir = f'{mesh_name}/misomip/{experiment}'
        # the tasks share a config, in which each has a section named for it
        super().__init__(
            component=component,
            name=f'misomip_{experiment}_{mesh_name}',
            subdir=subdir,
        )
        self.mesh_name = mesh_name
        self.experiment = experiment
        self.set_shared_config(config, link='misomip_analysis.cfg')

    def configure(self):
        """
        Build the steps from the runs the user's config names
        """
        super().configure()
        for step in list(self.steps.values()):
            self.remove_step(step)

        # every task sharing the config is configured, including those not
        # being set up, so a task without runs gets only its publish step,
        # which reports the missing runs if the task is set up
        runs = get_configured_runs(
            self.config, self.mesh_name, self.experiment
        )
        resolution = get_resolution(self.mesh_name)
        diagnostics = get_diagnostics_steps(
            self.component, self.config, self.mesh_name, self.experiment, runs
        )
        products = []
        for kind, run in runs.items():
            self.add_step(diagnostics[kind])
            label = f'{RUN_LABELS[kind]} {self.experiment}, {resolution}'
            products.append(
                self._add_shared_step(
                    RunPlots,
                    f'{self.subdir}/{kind}/plots_{run.key}',
                    diagnostics=diagnostics[kind],
                    kind=kind,
                    label=label,
                )
            )
            if diagnostics[kind].has_daily_volume:
                products.append(
                    self._add_shared_step(
                        OceanVolumeBudget,
                        f'{self.subdir}/{kind}/volume_budget_{run.key}',
                        diagnostics=diagnostics[kind],
                        kind=kind,
                    )
                )
        if self.config.getboolean('misomip_analysis', 'write_protocol_fields'):
            for kind, run in runs.items():
                map_step = self._add_shared_step(
                    ProtocolMapStep,
                    f'{self.subdir}/{kind}/protocol_map',
                    diagnostics=diagnostics[kind],
                )
                self._add_shared_step(
                    ProtocolFields,
                    f'{self.subdir}/{kind}/protocol_fields_{run.key}',
                    diagnostics=diagnostics[kind],
                    map_step=map_step,
                    kind=kind,
                )
        if len(diagnostics) == 2:
            key = f'{runs["e3sm"].key}_{runs["standalone"].key}'
            products.append(
                self._add_shared_step(
                    RunComparison,
                    f'{self.subdir}/comparison_{key}',
                    diagnostics=diagnostics,
                )
            )
        if diagnostics and self.experiment in PUBLISHED_EXPERIMENTS:
            yung2026 = get_yung2026_step(
                self.component,
                self.config,
                self.experiment,
                get_mean_months(self.config, self.experiment),
            )
            self.add_step(yung2026)
            key = '_'.join(run.key for run in runs.values())
            products.append(
                self._add_shared_step(
                    PublishedComparison,
                    f'{self.subdir}/published_{key}',
                    yung2026=yung2026,
                    diagnostics=diagnostics,
                )
            )
        if 'e3sm' in runs:
            case = E3smCase(runs['e3sm'].path)
            products.append(
                self._add_shared_step(
                    RunPerformance,
                    f'{self.subdir}/e3sm/performance_{runs["e3sm"].key}',
                    case=case,
                )
            )
            if case.get_value('BUDGETS').upper() == 'TRUE':
                products.append(
                    self._add_shared_step(
                        CouplerConservation,
                        f'{self.subdir}/e3sm/conservation_{runs["e3sm"].key}',
                        case=case,
                        diagnostics=diagnostics['e3sm'],
                    )
                )
            if self.experiment in COUPLED_EXPERIMENTS:
                key = runs['e3sm'].key
                products.append(
                    self._add_shared_step(
                        ModelExchange,
                        f'{self.subdir}/e3sm/model_exchange_{key}',
                        case=case,
                        diagnostics=diagnostics['e3sm'],
                    )
                )
                if diagnostics['e3sm'].landice_filenames:
                    products.append(
                        self._add_shared_step(
                            IceSheetComparison,
                            f'{self.subdir}/e3sm/ice_sheet_{key}',
                            case=case,
                            diagnostics=diagnostics['e3sm'],
                            experiment=self.experiment,
                        )
                    )
        publish = MisomipPublish(
            component=self.component,
            subdir=f'{self.subdir}/publish',
            product_steps=products,
            relative_path=f'{self.mesh_name}/{self.experiment}',
            missing=(
                f'No runs of {self.experiment} on {self.mesh_name} are '
                f'configured.  Set {self.experiment}_e3sm_case or '
                f'{self.experiment}_standalone in '
                f'[{runs_section(self.mesh_name)}].'
            ),
        )
        self.add_step(publish)

    def _add_shared_step(self, step_cls, subdir, **kwargs):
        """Get or create a shared step and add it to the task"""
        step = self.component.get_or_create_shared_step(
            step_cls=step_cls,
            subdir=subdir,
            config=self.config,
            config_filename='misomip_analysis.cfg',
            **kwargs,
        )
        self.add_step(step)
        return step


def get_diagnostics_steps(component, config, mesh_name, experiment, runs):
    """
    Get or create the shared diagnostics step of each run of an experiment

    Parameters
    ----------
    component : polaris.Component
        The e3sm/analysis component

    config : polaris.config.PolarisConfigParser
        The config shared by the MISOMIP analysis tasks

    mesh_name : str
        The pair of meshes

    experiment : str
        The experiment

    runs : dict of str to ConfiguredRun
        The experiment's runs, by kind

    Returns
    -------
    diagnostics : dict of str to RunDiagnostics
        The steps, by kind
    """
    return {
        kind: component.get_or_create_shared_step(
            step_cls=RunDiagnostics,
            subdir=f'{mesh_name}/misomip/{experiment}/{kind}/'
            f'diagnostics_{run.key}',
            config=config,
            config_filename='misomip_analysis.cfg',
            configured_run=run,
            experiment=experiment,
        )
        for kind, run in runs.items()
    }


def get_resolution(mesh_name):
    """
    Get the ocean resolution of a pair of meshes, such as ``4km``

    Parameters
    ----------
    mesh_name : str
        The pair of meshes, such as ``misomip-o4km-li1km``

    Returns
    -------
    resolution : str
        The ocean's resolution
    """
    return mesh_name.split('-')[1][1:]
