# Nightly cron jobs

Nightly testing of Omega on the supported machines, reported to the
[Omega CDash project](https://my.cdash.org/index.php?project=omega).
Two tasks run each night for each compiler:

| task | what it tests | CDash group | build name |
|---|---|---|---|
| `omega_cdash` | the CTests of Omega `develop` | `Omega_Nightly_CTests` | `unitest-develop-<compiler>` |
| `polaris_cdash` | the `omega_nightly` suite against the Omega submodule pinned in Polaris | `Polaris_Omega_Nightly_Tests` | `Baseline_<compiler>` |

CDash files a build into a group by rules on its name, set on the CDash
side, so the build names above must not change without changing the rules.
No baseline is compared by `polaris_cdash` despite its build name; see
[#770](https://github.com/E3SM-Project/polaris/issues/770).

## Layout

```
cron-scripts/
├── driver/
│   ├── cronjob.sh          # what the crontab runs: update the clone, launch
│   ├── crontab.template    # the crontab entry, rendered by install.sh
│   └── install.sh          # clone Polaris and install the crontab entry
├── launch_all.sh           # machine environment, lock, then nightly.py
├── nightly.py              # deploy and run the tasks for each compiler
├── machines/
│   ├── <machine>.cfg       # the compilers and Omega architectures to test
│   └── <machine>.sh        # the shell environment cron lacks
└── tasks/
    ├── omega_cdash.py
    ├── polaris_cdash.py
    ├── cdash.py            # Test.xml from a suite run
    └── common.py
```

## How a night runs

1. cron runs `driver/cronjob.sh -m <machine>` from the Polaris clone under
   the cron root.  It fetches and resets the clone to the tracked branch,
   initializes `jigsaw-python` and `e3sm_submodules/Omega`, and runs
   `launch_all.sh`.
2. `launch_all.sh` sources `machines/<machine>.sh`, takes a lock so two
   nights cannot overlap, and runs `nightly.py`.
3. `nightly.py` reads `machines/<machine>.cfg`.  For each compiler it runs
   `./deploy.py` (with `--recreate` for the first, so there is one fresh
   environment a night), then each task with that compiler's load script
   sourced.  Output goes to `<cron root>/logs/<date>/`, one file per step,
   and old dates are pruned.  Nothing is printed unless something failed,
   so that the mail cron sends carries only failures.
4. `omega_cdash.py` keeps `<cron root>/omega_develop` at the tip of Omega
   `develop` and runs
   [`utils/omega/ctest/omega_ctest.py`](../utils/omega/ctest/README.md)
   with `--dashboard --submit --cdash_submit`, which builds Omega on the
   login node, submits the job that runs the CTests, and submits the
   results to CDash from that job.
5. `polaris_cdash.py` builds the Omega submodule the same way with
   `--build_only`, sets up the `omega_nightly` suite against that build,
   submits the job `polaris suite` wrote and waits for it, writes the task
   results as `Test.xml` beside the recorded build, and submits both.

Work directories are under `<cron root>/tasks/<task>/<compiler>/`.  The
Omega checkout, the pixi cache (`<cron root>/pixi_cache`, kept off `/tmp`
because that is memory on Perlmutter login nodes) and the CTest meshes in
the Polaris database persist between nights; the builds and the suite
directory are made fresh.

## Installing on a machine

From any checkout of Polaris:

```bash
./cron-scripts/driver/install.sh -m chrysalis \
    --cron-root /lcrc/group/e3sm/<user>/scratch/cron
```

This clones Polaris to `<cron root>/polaris` if it is not there and installs
the crontab entry from `driver/crontab.template` between marker lines, so
running it again replaces only that entry.  `--dry-run` shows the crontab
without installing it.  `--mailto` sets where failures are mailed,
`--remote` and `--branch` what the clone tracks; the defaults are
`E3SM-Project/polaris` `main`.

Cron gives a job almost no environment.  `machines/<machine>.sh` provides
what `deploy.py` needs before any Polaris environment exists (a Python 3.8
or newer, `module`, and on Aurora the path to `qsub`); everything after
that comes from the load script `deploy.py` writes.

## Adding a machine

1. Make sure the machine is set up for Polaris and Omega (see the
   [Developer's Guide](https://docs.e3sm.org/polaris/main/developers_guide/machines/index.html)).
2. Add `machines/<machine>.cfg` listing each compiler to test and the
   `OMEGA_ARCH` to build with it.  The tasks check the compilers against
   `docs/developers_guide/supported_machines.yaml` and refuse ones it does
   not list for Omega on that machine.
3. Add `machines/<machine>.sh` with the module loads and paths cron needs.
4. Run `install.sh` as above.

## Running by hand

`nightly.py --dry_run` logs every command a night would run without running
any of them:

```bash
POLARIS_CRON_ROOT=/path/to/cron_root python3 cron-scripts/nightly.py \
    -m chrysalis --dry_run
```

A single task can be run under a load script, which is what `nightly.py`
does:

```bash
source load_polaris_chrysalis_intel_openmpi.sh
python cron-scripts/tasks/omega_cdash.py \
    --cron_root /path/to/cron_root --arch SERIAL --model Experimental
```

`--model Experimental` keeps a hand run out of the nightly groups on CDash.

A whole night can be run by hand from a cron root of your own, without a
crontab, by calling the driver directly.  `--site` gives the CDash rows a
site name of their own, so they sit beside the nightly rows for the machine
rather than replacing them:

```bash
export POLARIS_CRON_ROOT=/path/to/cron_root
bash "$POLARIS_CRON_ROOT/polaris/cron-scripts/driver/cronjob.sh" \
    -m chrysalis --site chrysalis-test
```

## What is not covered

A machine that stops reporting is silent: cron mails failures, but nothing
runs when a job never starts, and CDash does not notify anyone about a
missing build.  Checking the dashboard for missing rows has to happen
somewhere else, such as a scheduled GitHub Actions job.
