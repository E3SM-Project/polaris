# Adding Validation

One of the main purposes of having tasks is to validate changes to the
code.  You can use polaris' validation code to compare the output of different
steps to one another (or files within a single step), but a very common type
of validation is to check if the contents of files exactly match the contents
of the same files from a "baseline" run (performed with a different branch of
E3SM and/or polaris).

Validation happens at the task level so that steps can be compared with
one another.  Well add baseline validation for both the initial state and
forward runs:

```bash
$ vim polaris/tasks/ocean/my_overflow/default/__init__.py
```
```{code-block} python
:emphasize-lines: 3, 10-19

from polaris import Task
from polaris.tasks.ocean.yet_another_channel.init import Init
from polaris.validate import compare_variables


class Default(Task):

    ...

    def validate(self):
        """
        Compare ``temperature``, ``salinity``, and ``layerThickness`` in the
        ``init`` step with a baseline if one was provided.
        """
        super().validate()

        variables = ['temperature', 'salinity', 'layerThickness']
        compare_variables(task=self, variables=variables,
                          filename1='init/initial_state.nc')
```
We check salinity, temperature and layer thickness in the initial state step.
Since we only provide `filename1` in the call to
{py:func}`polaris.validate.compare_variables()`, we will only do this
validation if a user has set up the task with a baseline, see
{ref}`dev-validation`.

---

← [Back to *Adding Step Outputs*](adding_outputs.md)

→ [Continue to *Testing the `init` Step*](testing_init.md)
