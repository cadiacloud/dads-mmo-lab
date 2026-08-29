#!/usr/bin/env bash

set -euo pipefail

usage() {
  echo "Usage: $0 --server-root /absolute/path/to/azerothcore [--update]"
}

server_root=""
allow_update=0

while (($# > 0)); do
  case "$1" in
    --server-root)
      server_root="${2:-}"
      shift 2
      ;;
    --update)
      allow_update=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "$server_root" || "$server_root" != /* ]]; then
  echo "--server-root must be an absolute path" >&2
  exit 2
fi

if [[ ! -d "$server_root/modules/mod-playerbots" ]]; then
  echo "mod-playerbots was not found under $server_root/modules" >&2
  exit 1
fi

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source_dir="$script_dir/module/mod-cadia-player-director"
target_dir="$server_root/modules/mod-cadia-player-director"

if [[ -e "$target_dir" && $allow_update -ne 1 ]]; then
  echo "$target_dir already exists; use --update to refresh it" >&2
  exit 1
fi

mkdir -p -- "$target_dir"
cp -a -- "$source_dir/." "$target_dir/"

echo "Installed module source at $target_dir"
echo "Initialize the synthetic schema, rebuild worldserver, and perform a controlled restart."
