#!/bin/sh
# Headless Mesen CE test runner (Linux build). Mesen binary is not tracked.
# usage: MESEN=/path/to/Mesen tools/emu/run_headless.sh ROM SCRIPT.lua
# Needs ~/.config/MesenCE/settings.json with Lua io enabled:
#   {"Debug":{"ScriptWindow":{"AllowIoOsAccess":true}}}
set -e
: "${MESEN:?set MESEN to the Mesen binary}"
CFG="$HOME/.config/MesenCE/settings.json"
[ -f "$CFG" ] || { mkdir -p "$(dirname "$CFG")"; echo '{"Debug":{"ScriptWindow":{"AllowIoOsAccess":true}}}' > "$CFG"; }
if [ -z "$DISPLAY" ]; then exec xvfb-run -a "$MESEN" --testrunner "$1" "$2"; fi
exec "$MESEN" --testrunner "$1" "$2"
