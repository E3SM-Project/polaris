#!/usr/bin/env bash
#
# Entry point for the nightly jobs on one machine:
#
#   launch_all.sh -m <machine>
#
# The driver (driver/cronjob.sh) runs this after bringing the clone up to
# date.  It sets up the machine's shell environment, takes a lock so two
# nights cannot overlap, and hands over to nightly.py, which does the rest.
#
# Environment:
#   POLARIS_CRON_ROOT   the directory the nightly jobs work in (required)
#   POLARIS_ROOT        the Polaris clone (default: the one this script is in)

main() {
    set -eo pipefail

    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    local machine=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -m | --machine)
                machine="$2"
                shift 2
                ;;
            *)
                break
                ;;
        esac
    done
    if [[ -z "${machine}" ]]; then
        echo "ERROR: -m MACHINE is required" >&2
        echo "Usage: $(basename "${BASH_SOURCE[0]}") -m MACHINE" \
            "[nightly.py options]" >&2
        exit 1
    fi
    if [[ ! -f "${here}/machines/${machine}.sh" ]]; then
        echo "ERROR: no cron environment for '${machine}':" \
            "expected ${here}/machines/${machine}.sh" >&2
        exit 1
    fi

    : "${POLARIS_CRON_ROOT:?POLARIS_CRON_ROOT must be set}"
    mkdir -p "${POLARIS_CRON_ROOT}"
    export POLARIS_ROOT="${POLARIS_ROOT:-$(cd "${here}/.." && pwd)}"

    # shellcheck disable=SC1090
    source "${here}/machines/${machine}.sh"

    # under scrontab this is itself a Slurm job, and what it exports would
    # be inherited by every sbatch below (SLURM_MEM_PER_CPU makes srun refuse
    # a full node) and make omega_ctest.py think it is on a compute node
    unset "${!SLURM_@}"

    # the lock is inherited by nightly.py through the exec and released
    # when it exits
    exec 9>"${POLARIS_CRON_ROOT}/.launch_all.lock"
    if ! flock -n 9; then
        echo "ERROR: the nightly jobs are already running on ${machine}" \
            "(${POLARIS_CRON_ROOT}/.launch_all.lock is held)" >&2
        exit 1
    fi

    # further options, such as --site for a test run, go to nightly.py
    exec python3 "${here}/nightly.py" -m "${machine}" "$@"
}

main "$@"
