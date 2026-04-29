#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_NAME="$(basename "${BASH_SOURCE[0]}")"

# --- Parse command-line arguments ---
CLI_MACHINE=""
CLI_MINIFORGE3_HOME=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--machine)
      CLI_MACHINE="$2"
      shift 2
      ;;
    -f|--miniforge3)
      CLI_MINIFORGE3_HOME="$2"
      shift 2
      ;;
    *)
      echo "ERROR: Unknown option '$1'" >&2
      echo "Usage: $SCRIPT_NAME [-m|--machine MACHINE_NAME]" \
           "[--miniforge3 PATH]"
      exit 1
      ;;
  esac
done

# If user supplied a Miniforge3 install path, export it so downstream
# task scripts use it instead of installing their own copy.
if [[ -n "$CLI_MINIFORGE3_HOME" ]]; then
    export MINIFORGE3_HOME="$CLI_MINIFORGE3_HOME"
fi

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

LOCKFILE="${TMPDIR:-/tmp}/${USER:?USER must be set}_cronjob.lock"
exec 9>"$LOCKFILE"
if ! flock -n 9; then
    echo "[$(date)] launch_all.sh is already running, exiting."
    exit 0
fi

if [[ ! -d "$POLARIS_CRON_ROOT" ]]; then
    echo "ERROR: POLARIS_CRON_ROOT does not exist: $POLARIS_CRON_ROOT" >&2
    exit 1
fi

echo "Removing: outputs from previous tasks"
rm -rf -- "$POLARIS_CRON_ROOT/tasks"

# Run all launch*.sh scripts under immediate subdirectories of $HERE/tasks
while IFS= read -r script; do
    /bin/bash "$script"
done < <(
    find "$HERE/tasks" -mindepth 2 -maxdepth 2 \
        -type f -name 'launch*.sh' | sort
)

echo "[$(date)] Finished $SCRIPT_NAME"
