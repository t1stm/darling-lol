#!/bin/sh
set -eu
repo=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$repo"
python3 scripts/configure.py >/dev/null
if [ -d build/venv/bin ]; then PATH="$repo/build/venv/bin:$PATH"; export PATH; fi
runner="build/runtime/tools/run-riot-client.sh"
cmd="sh $runner"

if [ "${RCLOL_GAMEMODE:-auto}" != "0" ] && command -v gamemoderun >/dev/null 2>&1; then
  cmd="gamemoderun $cmd"
fi

if [ "${RCLOL_GPU:-auto}" != "intel" ] && [ -z "${__NV_PRIME_RENDER_OFFLOAD:-}" ] && command -v prime-run >/dev/null 2>&1; then
  cmd="prime-run $cmd"
fi

exec $cmd

