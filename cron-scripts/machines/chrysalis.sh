# shellcheck shell=bash
# Shell environment for the nightly cron jobs on chrysalis, sourced by
# launch_all.sh.  Cron starts with almost no environment, so this provides
# what deploy.py and the tasks need before any Polaris environment exists.

# shellcheck disable=SC1091
source /etc/bashrc
module load python
