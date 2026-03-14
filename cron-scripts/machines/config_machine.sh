#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Parse command-line arguments ---
usage() {
  echo "Usage: $(basename "$0") [-m|--machine MACHINE_NAME] [-h|--help]"
  echo "  -m, --machine   Override the auto-detected machine name"
  echo "  -h, --help      Show this help message"
  exit "${1:-0}"
}

CLI_MACHINE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--machine)
      CLI_MACHINE="$2"
      shift 2
      ;;
    -h|--help)
      usage 0
      ;;
    *)
      echo "ERROR: Unknown option '$1'" >&2
      usage 1
      ;;
  esac
done

# --- Get a stable hostname / FQDN (try multiple methods) ---
get_fqdn() {
  local fqdn=""
  fqdn="$(hostname -f 2>/dev/null || true)"
  if [[ -z "$fqdn" || "$fqdn" == "(none)" ]]; then
    fqdn="$(hostname --fqdn 2>/dev/null || true)"
  fi
  if [[ -z "$fqdn" || "$fqdn" == "(none)" ]]; then
    fqdn="$(hostname 2>/dev/null || true)"
  fi
  echo "$fqdn"
}

FQDN="$(get_fqdn)"

# --- Determine CRONJOB_MACHINE ---
if [[ -n "$CLI_MACHINE" ]]; then
  # Command-line argument takes highest priority
  CRONJOB_MACHINE="$CLI_MACHINE"
else
  # Fall back to FQDN-based detection
  CRONJOB_MACHINE="unknown"
  case "$FQDN" in
    *.frontier.olcf.ornl.gov)
      CRONJOB_MACHINE="frontier"
      ;;
    *.polaris.alcf.anl.gov)
      CRONJOB_MACHINE="polaris"
      ;;
    *.perlmutter.nersc.gov)
      CRONJOB_MACHINE="pm-gpu"
      ;;
    *.lcrc.anl.gov)
      CRONJOB_MACHINE="chrysalis"
      ;;
  esac
fi

export CRONJOB_MACHINE
echo "FQDN=$FQDN"
echo "CRONJOB_MACHINE=$CRONJOB_MACHINE"

source "${SCRIPT_DIR}/config_${CRONJOB_MACHINE}.sh"
