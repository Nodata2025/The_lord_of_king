#!/bin/sh
# Build -> IPS -> content check -> dist/ with the version from VERSION.
# usage: LOK_FONT=Galmuri11-Condensed.ttf tools/release.sh ROM [suffix]   (suffix default: -dev)
set -e
ROM="$1"; SUF="${2--dev}"
ROOT=$(cd "$(dirname "$0")/.." && pwd); cd "$ROOT"
V=$(cat VERSION)
NAME="LordOfKing_KR_v${V}${SUF}.ips"
python3 -I tools/build.py "$ROM" build/lok_ko.nes > build/report.txt
python3 -I tools/make_ips.py "$ROM" build/lok_ko.nes "dist/$NAME"
python3 -I tools/check_patch.py "$ROM" "dist/$NAME"
python3 -I tools/dist_readme.py "$NAME" build/lok_ko.nes.json
echo "dist/$NAME"
