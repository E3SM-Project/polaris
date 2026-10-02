# shellcheck shell=bash
# Shell environment for the nightly cron jobs on pm-gpu, sourced by
# launch_all.sh.  Cron starts with almost no environment, so this provides
# what deploy.py and the tasks need before any Polaris environment exists.

module load cray-python
