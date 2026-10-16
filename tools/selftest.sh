#!/usr/bin/env bash
# Run the in-page UI self-test headlessly against the fixture backend.
#   tools/selftest.sh [firefox|webkit] [WIDTHxHEIGHT]
# firefox: headless Firefox + the dev server.
# webkit:  the real pywebview/WebKitGTK window inside a headless cage compositor.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="${1:-firefox}"
SIZE="${2:-1280x800}"
W="${SIZE%x*}"; H="${SIZE#*x}"
OUT="${SELFTEST_DIR:-$ROOT/build/selftest}"
mkdir -p "$OUT"
FX="${FX:-auto}"
REPORT="$OUT/report-$ENGINE-$SIZE-$FX.json"
rm -f "$REPORT"
cd "$ROOT"

if [[ $ENGINE == firefox ]]; then
    PORT=$((20000 + RANDOM % 20000))
    /usr/bin/python -m linusetup serve --port "$PORT" --report "$REPORT" --exit-after-report --speed 0.02 --quiet &
    SRV=$!
    sleep 1
    PROFILE="$(mktemp -d)"
    timeout 240 firefox --headless --no-remote --profile "$PROFILE" --window-size 1600,1000 \
        "http://127.0.0.1:$PORT/__frame?w=$W&h=$H&q=selftest$([[ $FX != auto ]] && echo "%26fx=$FX")" >/dev/null 2>&1 &
    FF=$!
    for _ in $(seq 240); do [[ -s $REPORT ]] && break; sleep 1; done
    kill "$FF" "$SRV" 2>/dev/null; wait 2>/dev/null
    rm -rf "$PROFILE"
else
    export LINUSETUP_SELFTEST=1 LINUSETUP_SELFTEST_REPORT="$REPORT" LINUSETUP_SELFTEST_EXIT=1 LINUSETUP_SPEED=0.02
    [[ $FX != auto ]] && export LINUSETUP_EFFECTS="$FX"
    export WLR_BACKENDS=headless WLR_RENDERER=pixman WLR_HEADLESS_OUTPUTS=1 WLR_LIBINPUT_NO_DEVICES=1
    export XDG_RUNTIME_DIR="$(mktemp -d)" WEBKIT_DISABLE_COMPOSITING_MODE=1 WEBKIT_DISABLE_DMABUF_RENDERER=1
    unset WAYLAND_DISPLAY DISPLAY
    timeout 240 cage -s -- sh -c "wlr-randr --output HEADLESS-1 --custom-mode ${W}x${H} 2>/dev/null; \
        /usr/bin/python -m linusetup --fixtures --windowed" >"$OUT/webkit-$SIZE.log" 2>&1
fi

if [[ -s $REPORT ]]; then
    /usr/bin/python - "$REPORT" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
print(f"UI self-test ({r['size']}, effects {r.get('fx', '?')}): {r['passed']} passed, {r['failed']} failed")
for t in r["results"]:
    print(("  ok   " if t["ok"] else "  FAIL ") + t["name"] + ("" if t["ok"] else f"  -> {t['error']} [screen {t.get('screen')}]"))
for e in r["errors"]:
    print("  JS error: " + e)
for l in r["layout"]:
    print(f"  layout [{l['screen']}]: {l['problem']}")
sys.exit(1 if r["failed"] or r["errors"] else 0)
EOF
else
    echo "No report produced ($ENGINE $SIZE). See $OUT."
    exit 2
fi
