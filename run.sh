#!/usr/bin/env sh
set -eu
export LD_PRELOAD="/usr/lib/libgtk4-layer-shell.so${LD_PRELOAD:+:$LD_PRELOAD}"
exec /usr/bin/python "$(dirname -- "$0")/kotozaytsy.py" "$@"
