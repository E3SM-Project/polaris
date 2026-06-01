import os
from typing import Union

from polaris import Component


class Ocean(Component):
    """
    The collection of all test case for the MPAS-Ocean core

    Attributes
    ----------
    model : str
        The ocean model being used, either ``'mpas-ocean'``, ``'omega'``, or
        ``'unknown'`` if no ``OceanModelStep`` or ``OceanIOStep`` is present
        in any task, or if only model-fixed ``OceanIOStep`` instances are
        present (steps that set ``self.model`` explicitly at construction time)
    """

    def __init__(self):
        """
        Construct the collection of MPAS-Ocean test cases
        """
        super().__init__(name='ocean')
        self.model: Union[None, str] = None

    def configure(self, config, tasks):
        """
        Configure the component

        Parameters
        ----------
        config : polaris.config.PolarisConfigParser
            config options to modify

        tasks : list of polaris.Task
            The tasks to be set up for this component
        """
        section = config['ocean']
        model = section.get('model')
        has_ocean_model_steps, has_fixed_io, has_agnostic_io = (
            self._has_ocean_io_model_steps(tasks)
        )
        if not (has_ocean_model_steps or has_fixed_io or has_agnostic_io):
            # No ocean I/O or model steps, so no model detection or build
            # needed.
            if model == 'detect':
                model = 'unknown'
            self.model = model
            return

        model_cfgs = {'mpas-ocean': 'mpas_ocean.cfg', 'omega': 'omega.cfg'}

        if has_ocean_model_steps or has_agnostic_io:
            # Need a single global model: either a binary is required, or
            # model-agnostic IO steps need the model from config.
            if model == 'detect':
                model = self._detect_model(config)
                print('Detected ocean model:', model)
                config.set('ocean', 'model', model)
            if model not in model_cfgs:
                raise ValueError(f'Unknown ocean model {model}')
            config.add_from_package('polaris.ocean', model_cfgs[model])
            if has_ocean_model_steps:
                # Try to detect the model build; trigger a build if absent
                component_path = config.get('paths', 'component_path')
                if model == 'omega':
                    detected = self._detect_omega_build(component_path)
                else:
                    detected = self._detect_mpas_ocean_build(component_path)
                if not detected:
                    build = config.getboolean('build', 'build')
                    if not build:
                        print(
                            f'Ocean model {model} not found in '
                            f'{component_path}, setting build option to True'
                        )
                        config.set('build', 'build', 'True', user=True)
            self.model = model
        else:
            # Only model-fixed IO steps; each step knows its own model.
            # Load config for every model referenced by those steps.
            from polaris.ocean.model.ocean_io_step import OceanIOStep

            fixed_models = {
                step.model
                for task in tasks
                for step in task.steps.values()
                if isinstance(step, OceanIOStep) and step.model is not None
            }
            for m in sorted(fixed_models):
                if m not in model_cfgs:
                    raise ValueError(f'Unknown ocean model {m}')
                config.add_from_package('polaris.ocean', model_cfgs[m])
            self.model = model if model != 'detect' else 'unknown'

    def _has_ocean_io_model_steps(self, tasks) -> tuple[bool, bool, bool]:
        """
        Determine if any steps in this component descend from OceanIOStep or
        OceanModelStep, and distinguish model-fixed from model-agnostic IO
        steps.

        Returns
        -------
        has_ocean_model_steps : bool
            True if any step is an ``OceanModelStep`` (needs a model binary).
        has_model_fixed_io_steps : bool
            True if any ``OceanIOStep`` has ``self.model`` set explicitly at
            construction time (does not need global model detection).
        has_model_agnostic_io_steps : bool
            True if any ``OceanIOStep`` does *not* have ``self.model`` set
            (reads the model from config; requires global model detection).
        """
        # local import to avoid circular imports
        from polaris.ocean.model.ocean_io_step import OceanIOStep
        from polaris.ocean.model.ocean_model_step import OceanModelStep

        has_ocean_model_steps = any(
            isinstance(step, OceanModelStep)
            for task in tasks
            for step in task.steps.values()
        )
        has_model_fixed_io_steps = any(
            isinstance(step, OceanIOStep) and step.model is not None
            for task in tasks
            for step in task.steps.values()
        )
        has_model_agnostic_io_steps = any(
            isinstance(step, OceanIOStep) and step.model is None
            for task in tasks
            for step in task.steps.values()
        )

        return (
            has_ocean_model_steps,
            has_model_fixed_io_steps,
            has_model_agnostic_io_steps,
        )

    def _detect_model(self, config) -> str:
        """
        Detect which ocean model to use
        """
        # build config options for each model, so the default component_path
        # can be read if it hasn't been overridden
        omega_config = config.copy()
        omega_config.add_from_package('polaris.ocean', 'omega.cfg')
        omega_path = omega_config.get('paths', 'component_path')

        mpas_ocean_config = config.copy()
        mpas_ocean_config.add_from_package('polaris.ocean', 'mpas_ocean.cfg')
        mpas_ocean_path = mpas_ocean_config.get('paths', 'component_path')

        if self._detect_omega_build(omega_path):
            return 'omega'
        elif self._detect_mpas_ocean_build(mpas_ocean_path):
            return 'mpas-ocean'
        else:
            raise ValueError(
                f'Could not detect ocean model; neither MPAS-Ocean '
                f'nor Omega appear to be available; '
                f'searched {omega_path} and {mpas_ocean_path}.'
            )

    def _detect_omega_build(self, path) -> bool:
        """
        Detect if Omega is available
        """
        required_files = [
            'configs/Default.yml',
            'src/omega.exe',
        ]
        path = os.path.abspath(path)

        all_found = True
        for required_file in required_files:
            if not os.path.exists(os.path.join(path, required_file)):
                all_found = False
                break
        return all_found

    def _detect_mpas_ocean_build(self, path) -> bool:
        """
        Detect if MPAS-Ocean is available

        Returns
        -------
        is_mpas_ocean : bool
            True if MPAS-Ocean appears to be available, False otherwise
        """
        required_files = [
            'default_inputs/namelist.ocean.forward',
            'default_inputs/streams.ocean.forward',
            'src/Registry_processed.xml',
            'ocean_model',
        ]
        path = os.path.abspath(path)

        all_found = True
        for required_file in required_files:
            if not os.path.exists(os.path.join(path, required_file)):
                all_found = False
                break
        return all_found


# create a single module-level instance available to other components
ocean = Ocean()
