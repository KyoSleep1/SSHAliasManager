#!/bin/sh

project_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd) || exit 1
exec python3 "$project_dir/ssh_aliases.py" "$@"
