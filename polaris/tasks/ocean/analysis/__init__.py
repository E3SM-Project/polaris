from polaris import Task
from polaris.config import PolarisConfigParser
from polaris.tasks.ocean.analysis.climatology import Climatology as Climatology
from polaris.tasks.ocean.analysis.climatology_maps import (
    ClimatologyMaps as ClimatologyMaps,
)
from polaris.tasks.ocean.analysis.climatology_maps import get_field_groups
from polaris.tasks.ocean.analysis.global_stats import (
    GlobalStatsTimeSeries as GlobalStatsTimeSeries,
)
from polaris.tasks.ocean.analysis.heat_content_series import (
    HeatContentSeries as HeatContentSeries,
)
from polaris.tasks.ocean.analysis.moc import Moc as Moc
from polaris.tasks.ocean.analysis.publish import Publish as Publish
from polaris.tasks.ocean.analysis.sim_files import year_range_key


def add_analysis_tasks(component):
    """
    Add the tasks that analyze a completed Omega simulation

    Parameters
    ----------
    component : polaris.tasks.ocean.Ocean
        The ocean component the tasks will be added to
    """
    filepath = f'{component.name}/analysis/analysis.cfg'
    config = PolarisConfigParser(filepath=filepath)
    config.add_from_package('polaris.tasks.ocean.analysis', 'analysis.cfg')

    tasks = [
        task_cls(component=component, config=config)
        for task_cls in [
            ClimatologyMapsTask,
            GlobalStatsTask,
            HeatContentSeriesTask,
            MocTask,
        ]
    ]

    # the publish step depends on the steps of every other analysis task, so
    # the task that carries it is created once those steps exist, and each of
    # those tasks is told to have it rebuilt whenever they rebuild
    publish_task = PublishTask(component=component, config=config, tasks=tasks)
    for task in tasks:
        task.publish_task = publish_task
    tasks.append(publish_task)

    for task in tasks:
        component.add_task(task)


class AnalysisTask(Task):
    """
    A task of the ocean analysis suite

    A task is a thin grouping over shared steps and introduces no directory
    level of its own.  Its steps are built from config options rather than
    fixed at construction, so that a user who asks for a different range of
    years gets steps in different directories -- which have never run, and so
    run -- without having to delete anything or pass a flag.

    Attributes
    ----------
    range_section : str
        The config section holding the ``start_year`` and ``end_year`` this
        task's steps are keyed on

    publish_task : polaris.tasks.ocean.analysis.PublishTask or None
        The task that publishes this task's products, which has to rebuild
        its step whenever this one rebuilds its steps
    """

    def __init__(self, component, config, name, range_section):
        """
        Create the task and its steps

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to

        config : polaris.config.PolarisConfigParser
            The config parser shared by every analysis task

        name : str
            The name of the task, which is also its subdirectory under
            ``analysis``

        range_section : str
            The config section holding the ``start_year`` and ``end_year``
            this task's steps are keyed on
        """
        super().__init__(
            component=component, name=name, subdir=f'analysis/{name}'
        )
        self.range_section = range_section
        self.publish_task = None
        self.set_shared_config(config, link='analysis.cfg')
        self._setup_steps()

    def configure(self):
        """
        Build the steps again now that the user's config file has been read

        ``polaris setup`` merges the user's config into the task and then
        calls this before adding configs to steps, precisely so that steps
        created here are handled.

        The tasks sharing a config are configured in an arbitrary order --
        they are held in a set -- so a task that has just rebuilt its steps
        tells the task that publishes them to rebuild its own.  Whichever
        task is configured last therefore leaves the ``publish`` step
        depending on the steps that are really set up, rather than on the
        ones some earlier config asked for.
        """
        super().configure()
        self._setup_steps()
        if self.publish_task is not None:
            self.publish_task.rebuild_steps()

    def year_range(self):
        """
        Get the range of simulation years this task's steps cover

        Returns
        -------
        start_year : int
            The first year of the range, inclusive

        end_year : int
            The last year of the range, inclusive
        """
        section = self.config[self.range_section]
        return section.getint('start_year'), section.getint('end_year')

    def _setup_steps(self):
        """Discard the task's steps and build them from the config options"""
        raise NotImplementedError(
            f'{type(self).__name__} does not define _setup_steps()'
        )

    def _remove_all_steps(self):
        """Start fresh with no steps"""
        for step in list(self.steps.values()):
            self.remove_step(step)

    def _add_shared_step(self, step_cls, subdir, symlink=None, **kwargs):
        """Add a shared step at a subdirectory computed from the range"""
        step = self.component.get_or_create_shared_step(
            step_cls=step_cls,
            subdir=subdir,
            config=self.config,
            config_filename=self.config_filename,
            **kwargs,
        )
        self.add_step(step, symlink=symlink)
        return step


class ClimatologyMapsTask(AnalysisTask):
    """
    A task that plots map-view climatologies of the simulation's fields

    It has one step per field group, plus the shared climatology every field
    group reads, so that adding a field costs that field and not the others.
    """

    def __init__(self, component, config):
        """
        Create the climatology maps task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to

        config : polaris.config.PolarisConfigParser
            The config parser shared by every analysis task
        """
        super().__init__(
            component=component,
            config=config,
            name='climatology_maps',
            range_section='ocean_analysis_climatology',
        )

    def _setup_steps(self):
        start_year, end_year = self.year_range()
        key = year_range_key(start_year, end_year)

        self._remove_all_steps()

        self._add_shared_step(
            step_cls=Climatology,
            subdir=f'analysis/climatology/{key}',
            symlink='climatology',
            start_year=start_year,
            end_year=end_year,
        )

        fields = self.config.getlist('ocean_analysis_climatology', 'fields')
        for group, group_fields in get_field_groups(fields).items():
            self._add_shared_step(
                step_cls=ClimatologyMaps,
                subdir=f'analysis/climatology_maps/{key}/{group}',
                field_group=group,
                fields=group_fields,
                start_year=start_year,
                end_year=end_year,
            )


class GlobalStatsTask(AnalysisTask):
    """
    A task that plots time series of the simulation's global statistics
    """

    def __init__(self, component, config):
        """
        Create the global statistics task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to

        config : polaris.config.PolarisConfigParser
            The config parser shared by every analysis task
        """
        super().__init__(
            component=component,
            config=config,
            name='global_stats',
            range_section='ocean_analysis_time_series',
        )

    def _setup_steps(self):
        start_year, end_year = self.year_range()
        key = year_range_key(start_year, end_year)
        self._remove_all_steps()
        self._add_shared_step(
            step_cls=GlobalStatsTimeSeries,
            subdir=f'analysis/global_stats/{key}',
            start_year=start_year,
            end_year=end_year,
        )


class HeatContentSeriesTask(AnalysisTask):
    """
    A task that plots the time series of globally integrated ocean heat
    content
    """

    def __init__(self, component, config):
        """
        Create the ocean heat content time series task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to

        config : polaris.config.PolarisConfigParser
            The config parser shared by every analysis task
        """
        super().__init__(
            component=component,
            config=config,
            name='heat_content_series',
            range_section='ocean_analysis_time_series',
        )

    def _setup_steps(self):
        start_year, end_year = self.year_range()
        key = year_range_key(start_year, end_year)
        self._remove_all_steps()
        self._add_shared_step(
            step_cls=HeatContentSeries,
            subdir=f'analysis/heat_content_series/{key}',
            start_year=start_year,
            end_year=end_year,
        )


class MocTask(AnalysisTask):
    """
    A task that plots the global meridional overturning circulation
    """

    def __init__(self, component, config):
        """
        Create the MOC task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to

        config : polaris.config.PolarisConfigParser
            The config parser shared by every analysis task
        """
        super().__init__(
            component=component,
            config=config,
            name='moc',
            range_section='ocean_analysis_climatology',
        )

    def _setup_steps(self):
        start_year, end_year = self.year_range()
        key = year_range_key(start_year, end_year)
        self._remove_all_steps()
        self._add_shared_step(
            step_cls=Moc,
            subdir=f'analysis/moc/{key}',
            start_year=start_year,
            end_year=end_year,
        )


class PublishTask(AnalysisTask):
    """
    A task that publishes the results of the other analysis tasks

    It carries the one ``publish`` step of the suite, which depends on every
    step that makes products.  Nothing about the suite makes that step run
    last on its own, so the suite lists it last.

    Attributes
    ----------
    analysis_tasks : list of polaris.tasks.ocean.analysis.AnalysisTask
        The tasks whose steps make the products that are published
    """

    def __init__(self, component, config, tasks):
        """
        Create the publish task

        Parameters
        ----------
        component : polaris.tasks.ocean.Ocean
            The ocean component the task belongs to

        config : polaris.config.PolarisConfigParser
            The config parser shared by every analysis task

        tasks : list of polaris.tasks.ocean.analysis.AnalysisTask
            The tasks whose steps make products.  They are built before this
            one so that their steps exist, and rebuilt before this task is
            configured so that the steps this one depends on are the ones the
            user's config asked for.
        """
        self.analysis_tasks = tasks
        super().__init__(
            component=component,
            config=config,
            name='publish',
            range_section='ocean_analysis_climatology',
        )

    def rebuild_steps(self):
        """
        Build the publish step again, now that a task it depends on has
        rebuilt its steps

        A dependency is a step object rather than a path, and Polaris checks
        that the object it was given is one that was set up, so the step has
        to be rewired whenever a task discards its steps and builds new ones.
        """
        self._setup_steps()

    def _setup_steps(self):
        self._remove_all_steps()
        step = Publish(
            component=self.component,
            subdir='analysis/publish',
            product_steps=self._product_steps(),
        )
        step.set_shared_config(self.config, link=self.config_filename)
        self.add_step(step)

    def _product_steps(self):
        """The steps of the other tasks that make products, in suite order"""
        steps = {}
        for task in self.analysis_tasks:
            for step in task.steps.values():
                if step.makes_products:
                    steps[step.subdir] = step
        return list(steps.values())
