# Testing the First Task and Step

As you've seen, it's a good idea to test things out frequently as you develop
tasks and steps. Before we add any more features (certainly before we add any
more steps or tasks), we'll run `default` and make sure we can create mesh.
It would be good to make sure what we've done so far works well before we move
on.

The first way to test things out is just to list the tasks and make sure your
new one show up:

```bash
$ polaris list

Testcases:
  ...
  94: ocean/planar/my_overflow/default
  ...
```

``` {note}
Your numbers will be different from these, as new tasks are constantly being
added to Polaris.
```

A quick way to just get the task(s) you want is:
```bash
$ polaris list | grep my_overflow
  94: ocean/planar/my_overflow/default
```

If the tasks doesn't show up, you probably missed a step (adding the
`add_my_overflow_tasks()` call to the component or adding the `default` task
within that function).  If you get import, missing file, or syntax errors,
you'll need to fix those first.

If listing works out, it's time to set up your task:

```bash
$ polaris setup -n 94 -p e3sm_submodules/E3SM-Project/components/mpas-ocean \
     -w <work_dir>
```
See {ref}`dev-polaris-setup` for the details. If that works, you're ready to
do a test run.  If you get errors during setup, you have some debugging to do.

You can run the test with a job script or an interactive node.  For debugging,
the interactive node is usually more efficient. To run the task, open a
new terminal, go to the work directory, start an interactive session on
however many nodes you need (most often 1 when you're just debugging something
small) and for a long enough time that your debugging doesn't get interrupted,
e.g. on Chrysalis:
```bash
$ cd <work_dir>
$ srun -N 1 -t 2:00:00 --pty bash
```

Let's navigate into the task directory and see what it looks like:
```
$ cd ocean/planar/my_overflow/default
$ ls
init  job_script.sh  load_polaris_env.sh  my_overflow.cfg  task.pickle
```
If we open up `my_overflow.cfg` we can see that it contains our newly added
`[my_overflow]` section along with a bunch of other sections. Let's go to
the `[default]` section, where you will see `steps_to_run = init`.
This means that when we run our case, the meshshould be generated
if we didn't make any mistakes in setting up the step (fingers crossed!).

Then, on the interactive node, source the local link the load script and run:
```bash
$ source load_polaris_env.sh
$ polaris serial
```

(The `serial` in `polaris serial` is for "task serial" -- we have ambitions of
running in task parallel in the future.  Jobs may still run with MPI or Python
parallelism when launched with `polaris serial`.)

If you get errors, once again, you have some debugging to do. After fixing
bugs, it may sometimes be necessary to set up the test again before your
fix becomes available in the work directory (though many code changes should
take effect without you having to set up again).  It is typically usefule to
have at least two terminals open, one for editing code and setting up the
task and a second one (logged into an interactive job) for running and looking
at the results.

Now let's see what's in the `init` directory:
```
$ ls init
base_mesh.nc       job_script.sh        polaris_step_complete.log
culled_graph.info  load_polaris_env.sh  step.pickle
culled_mesh.nc     my_overflow.cfg

```
Our `base_mesh.nc` and `culled_mesh.nc` files are there.

One important aspect of this testing will be to change config options in the
work directory and make sure the task is modified in the expected way.  If
you change `lx` and `ly`, does the domain size change in the `culled_mesh.nc`
as expected?

```
$ ncdump -h init/culled_mesh.nc
netcdf culled_mesh {
dimensions:
	nEdges = 7248 ;
	nCells = 2400 ;
	nVertices = 4848 ;
	maxEdges = 6 ;
	TWO = 2 ;
	vertexDegree = 3 ;
	maxEdges2 = 12 ;
variables:
	double angleEdge(nEdges) ;
		angleEdge:long_name = "angle to edges" ;
	double areaCell(nCells) ;
		areaCell:long_name = "surface areas of cells" ;
...
```

If you want to rerun, you have to remove the following file first.  Otherwise,
Polaris just thinks the step has finished successuflly and won't rerun it.
```
$ rm init/polaris_step_complete.log
```

Then, you can modify the size of the domain or the resolution (e.g. `lx = 80`,
`ly = 400`):

```bash
$ vim my_overflow.cfg
```

and rerun the task:

```bash
$ polaris serial
```

As expected, the mesh now has 4 times as many cells:

```
$ $ ncdump -h init/culled_mesh.nc
netcdf culled_mesh {
dimensions:
	nEdges = 27692 ;
	nCells = 9200 ;
	nVertices = 18492 ;
	maxEdges = 6 ;
	TWO = 2 ;
	vertexDegree = 3 ;
	maxEdges2 = 12 ;
variables:
	double angleEdge(nEdges) ;
		angleEdge:long_name = "angle to edges" ;
	double areaCell(nCells) ;
		areaCell:long_name = "surface areas of cells" ;
...
```

---

← [Back to *Adding a First Task*](adding_first_task.md)

→ [Continue to *Fleshing out the `init` Step*](fleshing_out_step.md)
