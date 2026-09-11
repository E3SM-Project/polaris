#!/usr/bin/env bash
#
# Install (or update) the crontab entry for the Polaris nightly jobs on this
# machine, cloning Polaris under the cron root if it is not there yet.
#
#   install.sh -m MACHINE --cron-root PATH [options]
#
# The entry is rendered from crontab.template, or scrontab.template on
# machines whose cron config says scheduler = scrontab, and kept between
# BEGIN/END marker lines that name the machine, so reinstalling replaces only
# that machine's block and leaves the rest of the user's crontab alone,
# including the blocks for other machines that share it (pm-cpu and pm-gpu).

set -eo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
begin_marker="# BEGIN polaris cron-scripts"
end_marker="# END polaris cron-scripts"

# one value from an INI-style cron config, or nothing
cfg_get() {
    local section="[$1]" key="$2" file="$3"
    awk -F' *= *' -v s="${section}" -v k="${key}" \
        '$0 == s { f = 1; next } /^\[/ { f = 0 } f && $1 == k { print $2; exit }' \
        "${file}"
}

usage() {
    cat <<USAGE
Usage: $(basename "${BASH_SOURCE[0]}") -m MACHINE --cron-root PATH [options]

  -m, --machine MACHINE   the machine name (a file cron-scripts/machines/
                          MACHINE.cfg must exist)
  --cron-root PATH        the directory the nightly jobs work in; Polaris is
                          cloned to PATH/polaris if it is not there already
  --mailto ADDRESS        where cron mails failures
                          (default: xylarstorm@gmail.com)
  --account ACCOUNT       the account for the scrontab job, on machines whose
                          cron config says scheduler = scrontab (default: the
                          account in the cron config)
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
account=""
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
        --account)
            account="$2"
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

# crontab, or Slurm's scrontab where the login nodes have no cron
config="${here}/../machines/${machine}.cfg"
scheduler="$(cfg_get cron scheduler "${config}")"
scheduler="${scheduler:-crontab}"
case "${scheduler}" in
    crontab | scrontab) ;;
    *)
        echo "ERROR: unknown scheduler '${scheduler}' in ${config}" >&2
        exit 1
        ;;
esac
template="${here}/${scheduler}.template"
if [[ "${scheduler}" == scrontab ]]; then
    if [[ -z "${account}" ]]; then
        account="$(cfg_get cron account "${config}")"
    fi
    if [[ -z "${account}" ]]; then
        echo "ERROR: scrontab needs an account: pass --account or set" \
            "account in ${config}" >&2
        exit 1
    fi
fi

block="$(sed \
    -e "s|@MAILTO@|${mailto}|g" \
    -e "s|@ACCOUNT@|${account}|g" \
    -e "s|@CRON_ROOT@|${cron_root}|g" \
    -e "s|@REMOTE@|${remote}|g" \
    -e "s|@BRANCH@|${branch}|g" \
    -e "s|@MACHINE@|${machine}|g" \
    "${template}")"

# the existing crontab, with any earlier managed block for this machine
# removed.  scrontab -l reports an empty crontab on stdout and exits 0, so
# that line has to be dropped rather than installed.
existing="$("${scheduler}" -l 2>/dev/null | grep -v '^no crontab for ' || true)"
kept="$(printf '%s\n' "${existing}" |
    sed "/^${begin_marker} ${machine}\( \|$\)/,/^${end_marker} ${machine}$/d")"

# Polaris entries outside any managed block, other machines' blocks included
unmanaged="$(printf '%s\n' "${kept}" |
    sed "/^${begin_marker}/,/^${end_marker}/d")"
if printf '%s\n' "${unmanaged}" | grep -q -E 'cronjob|launch_all'; then
    echo "The existing crontab has Polaris cron entries outside the" \
        "managed block:" >&2
    printf '%s\n' "${unmanaged}" | grep -E 'cronjob|launch_all' >&2
    if [[ "${force}" != true ]]; then
        echo "Remove them, or pass --force to install alongside them." >&2
        exit 1
    fi
fi

new_crontab="$(printf '%s\n%s\n' "${kept}" "${block}" | sed '/./,$!d')"

echo "${scheduler} to install:"
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

printf '%s\n' "${new_crontab}" | "${scheduler}" -
echo "Installed.  Check with: ${scheduler} -l"
