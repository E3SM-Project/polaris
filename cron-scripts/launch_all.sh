#!/usr/bin/env bash
set -eo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"

# --- Parse command-line arguments ---
CLI_MACHINE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--machine)
      CLI_MACHINE="$2"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown option '$1'" >&2
      echo "Usage: $SCRIPT_NAME [-m|--machine MACHINE_NAME]"
      exit 1
      ;;
  esac
done

echo "[$(date)] Starting $SCRIPT_NAME"

# set CRONJOB_BASEDIR and machine-specific variables
# pass -m through so config_machine.sh uses CLI override if provided
if [[ -n "$CLI_MACHINE" ]]; then
    source "${HERE}/machines/config_machine.sh" -m "$CLI_MACHINE"
else
    source "${HERE}/machines/config_machine.sh"
fi

export CRONJOB_LOGDIR="${CRONJOB_BASEDIR}/logs"
mkdir -p "$CRONJOB_LOGDIR"

export CRONJOB_DATE=$(date +"%d")
export CRONJOB_TIME=$(date +"%T")

LOCKFILE="/tmp/${USER}_cronjob.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "[$(date)] launch_all.sh is already running, exiting."
    exit 0
fi
#LOCKFILE="${HERE}/cronjob.lock"
#exec 9>"$LOCKFILE"
#if ! flock -n 9; then
#    echo "[$(date)] launch_all.sh is already running, exiting."
#    exit 0
#fi

# Run all launch*.sh scripts under immediate subdirectories of $HERE/tasks
while IFS= read -r script; do
    /bin/bash "$script"
done < <(
    find "$HERE/tasks" -mindepth 2 -maxdepth 2 \
        -type f -name 'launch*.sh' | sort
)

echo "[$(date)] Finished $SCRIPT_NAME"
