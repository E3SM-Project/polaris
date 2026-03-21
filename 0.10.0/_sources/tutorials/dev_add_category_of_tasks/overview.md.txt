# Overview of the Tutorial

This tutorial guides you through the process of adding a new category of tasks
to Polaris, using the ocean component as an example. Below is a step-by-step
outline of the tutorial, with each step linked to its detailed instructions.

1. [Getting Started](getting_started.md)

   Set up your development environment, clone the Polaris repository, create a
   new branch, set up a conda environment, and obtain the necessary E3SM
   submodules.

2. [Making a New Category of Tasks](creating_category_of_tasks.md)

   Create a new Python package for your category of tasks, add an entry point
   function, and register it with the component.

3. [Adding a Shared Step](adding_shared_step.md)

   Introduce a shared `init` step for your category, set up a shared config
   file, and implement the initial mesh generation logic.

4. [Adding a First Task](adding_first_task.md)

   Create the first actual task (e.g., `default`), add it to your category,
   and wire it up to use the shared step.

5. [Testing the First Task and Step](testing_first_task.md)

   Test your new task by listing, setting up, and running it, and verify that
   the mesh is created as expected.

6. [Fleshing out the `init` Step](fleshing_out_step.md)

   Expand the `init` step to add vertical coordinates and initial conditions,
   and update the config file accordingly.

7. [Adding Plots](adding_plots.md)

   Add plotting functionality to visualize the initial condition as a sanity
   check.

8. [Adding Step Outputs](adding_outputs.md)

   Explicitly define the output files produced by your step to enable
   validation and future workflow enhancements.

9. [Adding a `forward` Step](adding_forward.md)

   Implement a `forward` step to run the model, configure model options, and
   add it to your task.

10. [Adding a Visualization Step](adding_viz.md)

    Add a `viz` step to generate plots from the model output, and integrate it
    into your task.

11. [Documentation](documenting.md)

    Document your new category of tasks for both users and developers, and
    pdate the API documentation.

---

→ [Continue *Getting Started*](getting_started.md)
