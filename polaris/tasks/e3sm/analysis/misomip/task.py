from polaris import Task
from polaris.e3sm.analysis.case import E3smCase
from polaris.tasks.e3sm.analysis.misomip.comparison import RunComparison
from polaris.tasks.e3sm.analysis.misomip.conservation import (
    CouplerConservation,
)
from polaris.tasks.e3sm.analysis.misomip.diagnostics import RunDiagnostics
from polaris.tasks.e3sm.analysis.misomip.plots import RunPlots
from polaris.tasks.e3sm.analysis.misomip.publish import MisomipPublish
from polaris.tasks.e3sm.analysis.misomip.runs import (
    get_configured_runs,
    runs_section,
)

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
        resolution = self.mesh_name.split('-')[1][1:]
        diagnostics = dict()
        products = []
        for kind, run in runs.items():
            label = f'{RUN_LABELS[kind]} {self.experiment}, {resolution}'
            diagnostics[kind] = self._add_shared_step(
                RunDiagnostics,
                f'{self.subdir}/{kind}/diagnostics_{run.key}',
                configured_run=run,
                experiment=self.experiment,
            )
            products.append(
                self._add_shared_step(
                    RunPlots,
                    f'{self.subdir}/{kind}/plots_{run.key}',
                    diagnostics=diagnostics[kind],
                    kind=kind,
                    label=label,
                )
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
        if 'e3sm' in runs:
            case = E3smCase(runs['e3sm'].path)
            if case.get_value('BUDGETS').upper() == 'TRUE':
                products.append(
                    self._add_shared_step(
                        CouplerConservation,
                        f'{self.subdir}/e3sm/conservation_{runs["e3sm"].key}',
                        case=case,
                    )
                )
        publish = MisomipPublish(
            component=self.component,
            subdir=f'{self.subdir}/publish',
            product_steps=products,
            mesh_name=self.mesh_name,
            experiment=self.experiment,
            runs_option=(
                f'{self.experiment}_e3sm_case or {self.experiment}_standalone '
                f'in [{runs_section(self.mesh_name)}]'
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
