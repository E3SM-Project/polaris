#!/usr/bin/env bash
#
# Install (or update) the crontab entry for the Polaris nightly jobs on this
# machine, cloning Polaris under the cron root if it is not there yet.
#
#   install.sh -m MACHINE --cron-root PATH [options]
#
# The entry is rendered from crontab.template and kept between BEGIN/END
# marker lines, so reinstalling replaces only that block and leaves the rest
# of the user's crontab alone.

set -eo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
template="${here}/crontab.template"
begin_marker="# BEGIN polaris cron-scripts"
end_marker="# END polaris cron-scripts"

usage() {
    cat <<USAGE
Usage: $(basename "${BASH_SOURCE[0]}") -m MACHINE --cron-root PATH [options]

  -m, --machine MACHINE   the machine name (a file cron-scripts/machines/
                          MACHINE.cfg must exist)
  --cron-root PATH        the directory the nightly jobs work in; Polaris is
                          cloned to PATH/polaris if it is not there already
  --mailto ADDRESS        where cron mails failures
                          (default: xylarstorm@gmail.com)
  --remote URL            the Polaris remote to track
                          (default: https://github.com/E3SM-Project/polaris.git)
  --branch NAME           the branch to track (default: main)
  --dry-run               print the crontab that would be installed and stop
  --force                 install even if the existing crontab has Polaris
                          cron entries outside the managed block
  -h, --help              show this help
USAGE
}

machine=""
cron_root=""
mailto="xylarstorm@gmail.com"
remote="https://github.com/E3SM-Project/polaris.git"
branch="main"
dry_run=false
force=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -m | --machine)
            machine="$2"
            shift 2
            ;;
        --cron-root)
            cron_root="$2"
            shift 2
            ;;
        --mailto)
            mailto="$2"
            shift 2
            ;;
        --remote)
            remote="$2"
            shift 2
            ;;
        --branch)
            branch="$2"
            shift 2
            ;;
        --dry-run)
            dry_run=true
            shift
            ;;
        --force)
            force=true
            shift
            ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "ERROR: unknown option '$1'" >&2
            usage >&2
            exit 1
            ;;
    esac
done

if [[ -z "${machine}" || -z "${cron_root}" ]]; then
    echo "ERROR: -m MACHINE and --cron-root PATH are both required" >&2
    usage >&2
    exit 1
fi
if [[ ! -f "${here}/../machines/${machine}.cfg" ]]; then
    echo "ERROR: no cron config for machine '${machine}':" \
        "expected cron-scripts/machines/${machine}.cfg" >&2
    exit 1
fi

cron_root="$(mkdir -p "${cron_root}" && cd "${cron_root}" && pwd)"
polaris_root="${cron_root}/polaris"

block="$(sed \
    -e "s|@MAILTO@|${mailto}|" \
    -e "s|@CRON_ROOT@|${cron_root}|" \
    -e "s|@REMOTE@|${remote}|" \
    -e "s|@BRANCH@|${branch}|" \
    -e "s|@MACHINE@|${machine}|" \
    "${template}")"

# the existing crontab, with any earlier managed block removed
existing="$(crontab -l 2>/dev/null || true)"
kept="$(printf '%s\n' "${existing}" |
    sed "/^${begin_marker}/,/^${end_marker}/d")"

if printf '%s\n' "${kept}" | grep -q -E 'cronjob\.sh|launch_all\.sh'; then
    echo "The existing crontab has Polaris cron entries outside the" \
        "managed block:" >&2
    printf '%s\n' "${kept}" | grep -E 'cronjob\.sh|launch_all\.sh' >&2
    if [[ "${force}" != true ]]; then
        echo "Remove them, or pass --force to install alongside them." >&2
        exit 1
    fi
fi

new_crontab="$(printf '%s\n%s\n' "${kept}" "${block}" | sed '/./,$!d')"

echo "Crontab to install:"
echo "-------------------"
printf '%s\n' "${new_crontab}"
echo "-------------------"

if [[ "${dry_run}" == true ]]; then
    exit 0
fi

if [[ ! -d "${polaris_root}/.git" ]]; then
    echo "Cloning ${remote} (${branch}) to ${polaris_root}"
    git clone --quiet -b "${branch}" "${remote}" "${polaris_root}"
fi

printf '%s\n' "${new_crontab}" | crontab -
echo "Installed.  Check with: crontab -l"
