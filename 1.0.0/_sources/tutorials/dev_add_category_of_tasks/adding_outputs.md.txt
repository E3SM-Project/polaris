# Adding Step Outputs

Now that we've written the full `run()` method for the step, we know what
the output files will be.  It is a very good idea to define the outputs
explicitly.  For one, polaris will check to make sure they are created as
expected and raise an error if not.  For another, we anticipate that defining
outputs will be a requirement for future work on task parallelism in which
the connection between tasks and steps will be determined based on their
inputs and outputs.  For this step, we add the following outputs in the
constructor:

```bash
$ vim polaris/tasks/ocean/my_overflow/init.py
```
```{code-block} python
:emphasize-lines: 11-13

...

class Init(Step):
    ...

    def __init__(self, task, resolution):

        ...
        super().__init__(component=component, name=name, indir=indir)

        output_filenames = ['culled_mesh.nc', 'init.nc', 'culled_graph.info']
        for filename in output_filenames:
            self.add_output_file(filename=filename)
```

All of these outputs will be used as inputs to the subsequent `forward` and
`viz` steps that we will define later in the tutorial.  You could add other
outputs (in this step and example would be `base_mesh.nc`) and this would be
harmless even if no other step uses them as inputs.

## Testing

As always, it's best to repeat the testing procedure from
[Testing the First Task and Step](testing_first_task.md) in a new work
directory. As long as these 3 expected files are produced, you shouldn't see
any errors.

---

← [Back to *Adding Plots*](adding_plots.md)

→ [Continue to *Adding a `forward` Step*](adding_forward.md)
