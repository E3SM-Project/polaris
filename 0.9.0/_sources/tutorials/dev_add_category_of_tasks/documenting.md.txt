# Documentation

Make sure to add some documentation of your new category of tasks.  The
documentation is written in the
[MyST](https://myst-parser.readthedocs.io/en/latest/syntax/typography.html)
flavor of Markdown, similar to what GitHub uses. See {ref}`dev-docs` for
details.

You need to add all of the public functions, classes and methods to the
{ref}`dev-api` in `docs/developers_guide/<component>/api.md`, following the
examples for other categories of tasks.

You also need to add a file to both the user's guide and the developer's guide
describing the category of tasks and its tasks and steps.

For the user's guide, make a copy of
`docs/users_guide/<component>/tasks/template.md` called
`docs/users_guide/<component>/tasks/<category>.md`.  In that file, you
should describe the category of tasks and its tasks in a way that would be
relevant for a user wanting to run the task and look at the output.
This file should describe all of the config options relevant the tasks
collectively and each task (if it has its own config options), including what
they are used for and whether it is a good idea to modify them.  Add
`<category>` in the appropriate place (in alphabetical order) to the list
of categories of tasks in the file
`docs/users_guide/<component>/tasks/index.md`.

For the developer's guide, create a file
`docs/developers_guide/<component>/tasks/<category>.md`. In this file,
you will describe the category of tasks, its tasks and steps in a way that is
relevant to developers who might want to modify the code or use it as an
example for developing their own tasks.  Currently, the descriptions are
brief in part because of the daunting task of documenting a large number of
tasks but should be fleshed out over time.  It would help new developers
if new categories and tasks were documented well. Add `<category>` in
the appropriate place (in alphabetical order) to the list of categories of
tasks in `docs/developers_guide/<component>/tasks/index.md`.

At this point, you are ready to make a pull request with the new category of
tasks!

---

← [Back to *Adding a Visualization Step*](adding_viz.md)
