#!/usr/bin/env bash

set -euo pipefail

usage() {
  echo "Usage: $0 --server-root /absolute/path/to/azerothcore [--update]"
}

server_root=""
allow_update=0
while (($# > 0)); do
  case "$1" in
    --server-root) server_root="${2:-}"; shift 2 ;;
    --update) allow_update=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

if [[ -z "$server_root" || "$server_root" != /* ]]; then
  echo "--server-root must be an absolute path" >&2
  exit 2
fi
if [[ ! -f "$server_root/modules/CMakeLists.txt" ]]; then
  echo "$server_root does not look like an AzerothCore source tree" >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir="$script_dir/module/mod-boa-rogue-heirlooms"
target_dir="$server_root/modules/mod-boa-rogue-heirlooms"

if [[ -e "$target_dir" && $allow_update -ne 1 ]]; then
  echo "$target_dir already exists; use --update to refresh it" >&2
  exit 1
fi

mkdir -p -- "$target_dir"
cp -a -- "$source_dir/." "$target_dir/"

patch_file="$script_dir/patches/0001-call-custom-scaling-hook-for-dbc-distributions.patch"
if git -C "$server_root" apply --check "$patch_file"; then
  git -C "$server_root" apply "$patch_file"
elif ! git -C "$server_root" apply --reverse --check "$patch_file"; then
  echo "core scaling hook patch is neither applicable nor already present" >&2
  exit 1
fi

echo "Installed module source at $target_dir"
echo "Installed or verified the bounded custom-scaling core hook patch."
echo "Reconfigure, rebuild, deploy the custom DBC, import SQL, and restart worldserver."
