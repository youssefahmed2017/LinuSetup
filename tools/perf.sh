#!/usr/bin/env bash
# Frame-time measurement in WebKitGTK (headless cage) while the pointer sweeps
# over cards. Prints p50/p95/max frame time in ms. Usage: tools/perf.sh [effects|lite]
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODE="${1:-effects}"
OUT="$(mktemp -d)"
cd "$ROOT"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export XDG_RUNTIME_DIR="$(mktemp -d)"
unset WAYLAND_DISPLAY DISPLAY
PORT=$((20000 + RANDOM % 20000))
/usr/bin/python -m linusetup serve --port "$PORT" --report "$OUT/perf.json" --speed 0.02 --quiet &
SRV=$!
sleep 0.8
Q="shot=perf"; [[ $MODE == lite ]] && Q="lite%26shot=perf"
timeout 120 cage -s -- /usr/bin/python "$ROOT/tools/snap.py" "http://127.0.0.1:$PORT/__frame?w=1280&h=800&q=$Q" "$OUT/perf.png" >/dev/null 2>&1
kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null
cat "$OUT/perf.json" 2>/dev/null || echo "no result"
echo
rm -rf "$OUT"
