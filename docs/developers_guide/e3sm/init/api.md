# e3sm/init

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init

.. autosummary::
   :toctree: generated/

   add_tasks.add_e3sm_init_tasks
```

## Tasks

### topo

#### combine

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.topo.combine

.. autosummary::
   :toctree: generated/

   CombineStep
   CombineStep.get_subdir
   CombineStep.setup
   CombineStep.constrain_resources
   CombineStep.run
   CombineTask
   VizCombinedStep
   VizCombinedStep.setup
   VizCombinedStep.run
```

#### remap

```{eval-rst}
.. currentmodule:: polaris.tasks.e3sm.init.topo.remap

.. autosummary::
   :toctree: generated/

   MaskTopoStep
   MaskTopoStep.setup
   MaskTopoStep.constrain_resources
   MaskTopoStep.define_masks
   MaskTopoStep.run

   RemapTopoStep
   RemapTopoStep.setup
   RemapTopoStep.constrain_resources
   RemapTopoStep.define_smoothing
   RemapTopoStep.run
   RemapTopoTask
   VizRemappedTopoStep
   VizRemappedTopoStep.run
```
