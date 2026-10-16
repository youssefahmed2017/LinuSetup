#!/usr/bin/env bash
# Build the LinuSetup live ISO: stock archiso "releng" profile + our overlay.
# Usage: sudo ./iso/build.sh        (output: ./out/*.iso)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
WORK="$ROOT/build"
PROFILE="$WORK/profile"
SRC=/usr/share/archiso/configs/releng

[[ $EUID -eq 0 ]] || { echo "Run as root: sudo $0"; exit 1; }
[[ -d $SRC ]] || { echo "archiso not installed (pacman -S archiso)"; exit 1; }

rm -rf "$PROFILE" "$WORK/work"
rm -f "$ROOT"/out/*.iso    # filenames contain the build date; never leave a stale one for `make vm`
mkdir -p "$WORK" "$ROOT/out"
cp -r "$SRC" "$PROFILE"

# --- 1. pacman.conf: enable [multilib] (releng ships it commented out). The
#        live system's pacman.conf is what pacstrap uses, and Steam lives there.
#        mkarchiso only uses the profile's pacman.conf to BUILD the image; it is not
#        copied into it. So the edited file must also be shipped via airootfs.
sed -i '/^#\[multilib\]/,/^#Include/ s/^#//' "$PROFILE/pacman.conf"
grep -q '^\[multilib\]' "$PROFILE/pacman.conf" || { echo "failed to enable multilib"; exit 1; }
install -Dm644 "$PROFILE/pacman.conf" "$PROFILE/airootfs/etc/pacman.conf"

# --- 2. packages: Wayland kiosk + pywebview on WebKitGTK (no Chromium).
cat >> "$PROFILE/packages.x86_64" <<'EOF'
cage
seatd
python
python-pywebview
python-gobject
webkit2gtk-4.1
noto-fonts
ttf-dejavu
xorg-xwayland
mesa
pciutils
gptfdisk
EOF
# dosfstools, e2fsprogs, arch-install-scripts, grub, efibootmgr are already in releng.

# --- 3. the app
mkdir -p "$PROFILE/airootfs/opt"
cp -r "$ROOT/linusetup" "$PROFILE/airootfs/opt/linusetup"
find "$PROFILE/airootfs/opt/linusetup" -name __pycache__ -prune -exec rm -rf {} +

# --- 4. seatd for cage (cage as root on tty1 normally works through logind;
#        seatd is the fallback, see DECISIONS.md "Live-ISO risks").
mkdir -p "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants"
ln -sf /usr/lib/systemd/system/seatd.service \
    "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/seatd.service"

# --- 5. autostart on tty1. Real install mode is opt-in via LINUSETUP_REAL=1
#        and additionally requires /run/archiso and root (see runner.py).
cat >> "$PROFILE/airootfs/root/.zlogin" <<'EOF'

# LinuSetup: on tty1, run the installer in a single-app Wayland kiosk.
# Debug escape hatch: add `linusetup.shell` to the kernel command line to skip it.
if [[ -z "${WAYLAND_DISPLAY:-}" && "$(tty)" == /dev/tty1 ]] \
   && ! grep -q 'linusetup.shell' /proc/cmdline; then
    export XDG_RUNTIME_DIR=/run/user/0
    mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
    export LIBSEAT_BACKEND=logind          # try seatd instead if cage reports a session error
    export WLR_NO_HARDWARE_CURSORS=1       # software cursor: reliable in VMs
    export WEBKIT_DISABLE_COMPOSITING_MODE=1
    export WEBKIT_DISABLE_DMABUF_RENDERER=1
    export LINUSETUP_REAL=1
    # `linusetup.dry` on the kernel command line forces a safe, no-changes run.
    grep -q 'linusetup.dry' /proc/cmdline && export LINUSETUP_DRY_RUN=1
    cd /opt && cage -s -- python -m linusetup > /tmp/linusetup.log 2>&1
    echo "LinuSetup exited. Log: /tmp/linusetup.log  (run 'cd /opt && python -m linusetup' to retry)"
fi
EOF

# --- 6. build
mkarchiso -v -w "$WORK/work" -o "$ROOT/out" "$PROFILE"
# Hand the output back to the invoking user so `make vm`/`make clean` need no root.
if [[ -n "${SUDO_UID:-}" ]]; then chown "$SUDO_UID:${SUDO_GID:-$SUDO_UID}" "$ROOT/out" "$ROOT"/out/*.iso; fi
echo "ISO ready:"; ls -lh "$ROOT"/out/*.iso
