#!/usr/bin/env bash
# Copy the staged tree into an inputdata directory, then set the permissions
# an inputdata directory expects.
#
# Run by hand from the assembly step's work directory:
#
#     ./sync_to_inputdata.sh /lcrc/group/e3sm/data/inputdata
#
# The destination must already exist: this is a copy into a directory someone
# else curates, not a place to create one.
#
# --ignore-existing means a file already on the destination is left alone, so
# a re-run adds what is new without overwriting what is there.  A staged file
# whose contents changed under an unchanged name will therefore NOT be
# updated; remove it from the destination first if that is what you want.
#
# --copy-links because the staged tree is symlinks into the step directories,
# and inputdata needs the files themselves.
#
# Only the paths this tree contributes are given permissions.  The destination
# is shared, often enormous, and walking it to chmod everything would touch
# files that have nothing to do with this mesh.

set -euo pipefail

if [ $# -ne 1 ]; then
    echo "usage: $(basename "$0") <dest_inputdata>" >&2
    exit 1
fi

dest=$1

if [ ! -d "${dest}" ]; then
    echo "error: destination inputdata directory does not exist: ${dest}" >&2
    echo "       create it first, or check the path" >&2
    exit 1
fi

# BASH_SOURCE is the path as invoked, not the resolved target, so for the
# symlink in the step's work directory this is that work directory -- where
# assembled_files is -- whatever the current directory happens to be.
# Resolving the link would land in the polaris package, which has no tree to
# sync.  A copy of this script therefore syncs the tree beside the copy.
work_dir=$(dirname "${BASH_SOURCE[0]}")
cd "${work_dir}/assembled_files"

if [ ! -d inputdata ]; then
    echo "error: no assembled_files/inputdata to sync; has the step run?" >&2
    exit 1
fi

echo "syncing to ${dest}"
rsync --verbose --ignore-existing --recursive --copy-links \
    inputdata/ "${dest}"

echo "setting permissions on what was synced"
cd inputdata

# directories: user and group read/write/execute, world read/execute
while IFS= read -r -d '' path; do
    target="${dest}/${path#./}"
    if [ -d "${target}" ]; then
        chmod 775 "${target}" || echo "warning: could not chmod ${target}" >&2
    fi
done < <(find . -mindepth 1 -type d -print0)

# files: user and group read/write, world read.  The staged tree is symlinks,
# so match everything that is not a directory rather than -type f.
while IFS= read -r -d '' path; do
    target="${dest}/${path#./}"
    if [ -f "${target}" ]; then
        chmod 664 "${target}" || echo "warning: could not chmod ${target}" >&2
    fi
done < <(find . -mindepth 1 ! -type d -print0)

echo "done"
