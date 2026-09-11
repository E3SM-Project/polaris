#!/usr/bin/env bash
#
# Nightly driver for the Polaris cron jobs.  A crontab entry, installed by
# install.sh from crontab.template, runs this script from the Polaris clone
# it maintains:
#
#   cronjob.sh -m <machine>
#
# It brings the clone up to date with the tracked branch, initializes the
# submodules the nightly tasks need, and hands over to launch_all.sh.
#
# Environment (set by the crontab):
#   POLARIS_CRON_ROOT     the directory the nightly jobs work in
#   POLARIS_CRON_REMOTE   the Polaris remote (default: E3SM-Project/polaris)
#   POLARIS_CRON_BRANCH   the branch to track (default: main)
#
# The whole script is a function called on the last line.  It lives in the
# clone it rewrites, and bash reads scripts incrementally, so an unwrapped
# script could execute the wrong bytes after git reset --hard replaces it.

main() {
    set -eo pipefail

    local here
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local polaris_root
    polaris_root="$(cd "${here}/../.." && pwd)"

    local machine=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -m | --machine)
                machine="$2"
                shift 2
                ;;
            *)
                echo "ERROR: unknown option '$1'" >&2
                echo "Usage: $(basename "${BASH_SOURCE[0]}") -m MACHINE" >&2
                exit 1
                ;;
        esac
    done
    if [[ -z "${machine}" ]]; then
        echo "ERROR: -m MACHINE is required" >&2
        exit 1
    fi

    : "${POLARIS_CRON_ROOT:?POLARIS_CRON_ROOT must be set}"
    local remote="${POLARIS_CRON_REMOTE:-https://github.com/E3SM-Project/polaris.git}"
    local branch="${POLARIS_CRON_BRANCH:-main}"

    if [[ ! -d "${polaris_root}/.git" ]]; then
        echo "ERROR: ${polaris_root} is not a git clone; run install.sh" >&2
        exit 1
    fi

    cd "${polaris_root}"
    git remote set-url origin "${remote}"
    git fetch --quiet origin "${branch}"
    # -f discards local edits; ignored files (the deployed environment, the
    # load scripts) are left alone
    git checkout --quiet -f -B "${branch}" FETCH_HEAD
    git submodule --quiet update --init --recursive jigsaw-python
    git submodule --quiet update --init e3sm_submodules/Omega

    export POLARIS_ROOT="${polaris_root}"
    exec bash "${polaris_root}/cron-scripts/launch_all.sh" -m "${machine}"
}

main "$@"
