#!/usr/bin/env bash
# Screenshot every main screen with WebKitGTK in a headless compositor.
#   tools/screens.sh [WIDTHxHEIGHT] [screen ...]   -> build/screens/*.png
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SIZE="${1:-1280x800}"; shift || true
W="${SIZE%x*}"; H="${SIZE#*x}"
OUT="${SCREENS_DIR:-$ROOT/build/screens}"
SHOTS=("$@")
[[ ${#SHOTS[@]} -gt 0 ]] || SHOTS=(welcome mode uses desktop disk you review confirm install done hub sec-disk sec-desktop sec-software sec-users)
mkdir -p "$OUT"
cd "$ROOT"
export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_LIBINPUT_NO_DEVICES=1
export XDG_RUNTIME_DIR="$(mktemp -d)" WEBKIT_DISABLE_COMPOSITING_MODE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
unset WAYLAND_DISPLAY DISPLAY
for shot in "${SHOTS[@]}"; do
    PORT=$((20000 + RANDOM % 20000))
    speed=0.02; [[ $shot == install ]] && speed=1
    /usr/bin/python -m linusetup serve --port "$PORT" --speed "$speed" --quiet &
    SRV=$!
    sleep 0.8
    timeout 150 cage -s -- /usr/bin/python "$ROOT/tools/snap.py" \
        "http://127.0.0.1:$PORT/__frame?w=$W&h=$H&q=lite%26shot=$shot" "$OUT/$shot-$SIZE.png" >/dev/null 2>&1
    kill "$SRV" 2>/dev/null; wait "$SRV" 2>/dev/null
    [[ -s "$OUT/$shot-$SIZE.png" ]] && echo "ok   $shot" || echo "FAIL $shot"
done
