#!/usr/bin/env bash
# Build the LinuSetup live ISO: stock archiso "releng" profile + our overlay.
# Usage: sudo ./iso/build.sh [--release]       (output: ./out/*.iso)
#   default    zstd squashfs: several times faster to build, slightly bigger ISO (testing)
#   --release  xz squashfs: smallest ISO, slow to build (publishing)
set -euo pipefail
RELEASE=0
[[ "${1:-}" == --release ]] && RELEASE=1

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

# --- 0a. branding: this is LinuSetup, built on Arch Linux, not an official Arch ISO.
VERSION=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$ROOT/linusetup/__init__.py")
sed -i -e 's|^iso_name=.*|iso_name="linusetup"|' \
       -e "s|^iso_label=.*|iso_label=\"LINUSETUP_${VERSION//./}\"|" \
       -e 's|^iso_publisher=.*|iso_publisher="LinuSetup <https://github.com/youssefahmed2017/LinuSetup>"|' \
       -e 's|^iso_application=.*|iso_application="LinuSetup: graphical Arch Linux installer"|' \
       -e "s|^iso_version=.*|iso_version=\"$VERSION\"|" "$PROFILE/profiledef.sh"
grep -rl "Arch Linux install medium" "$PROFILE"/efiboot "$PROFILE"/syslinux "$PROFILE"/grub \
    | xargs -r sed -i 's/Arch Linux install medium/LinuSetup Arch Linux installer/g'

# --- 0. squashfs compression. releng uses xz with BOTH the x86 and arm64 BCJ filters,
#        i.e. every block is compressed twice; arm64 is useless on an x86_64 image.
if [[ $RELEASE == 1 ]]; then
    COMP="('-comp' 'xz' '-Xbcj' 'x86' '-b' '1M' '-Xdict-size' '1M')"
else
    COMP="('-comp' 'zstd' '-Xcompression-level' '15' '-b' '1M')"
fi
sed -i "s|^airootfs_image_tool_options=.*|airootfs_image_tool_options=$COMP|" "$PROFILE/profiledef.sh"
grep -q "^airootfs_image_tool_options=$COMP" "$PROFILE/profiledef.sh" || { echo "failed to set compression"; exit 1; }

# --- 1. pacman.conf: enable [multilib] (releng ships it commented out). pacstrap
#        uses the LIVE system's /etc/pacman.conf, and Steam/Wine live in multilib.
#        mkarchiso only uses the profile's pacman.conf to BUILD the image; it is not
#        copied into it, so the edited file must also be shipped via airootfs.
sed -i '/^#\[multilib\]/,/^#Include/ s/^#//' "$PROFILE/pacman.conf"
grep -q '^\[multilib\]' "$PROFILE/pacman.conf" || { echo "failed to enable multilib"; exit 1; }
install -Dm644 "$PROFILE/pacman.conf" "$PROFILE/airootfs/etc/pacman.conf"

# --- 1b. a package cache of our own (build/pkgcache, kept between builds).
#        By default mkarchiso reuses the host's /var/cache/pacman/pkg, and one
#        corrupted file there fails the whole build with "invalid or corrupted
#        package (PGP signature)". Set after the airootfs copy above, so the
#        live system keeps the normal cache path.
mkdir -p "$WORK/pkgcache"
sed -i "s|^#\?CacheDir.*|CacheDir = $WORK/pkgcache/|" "$PROFILE/pacman.conf"
grep -q '^CacheDir' "$PROFILE/pacman.conf" || sed -i "/^\[options\]/a CacheDir = $WORK/pkgcache/" "$PROFILE/pacman.conf"

# --- 2. packages: the Wayland kiosk + pywebview on WebKitGTK (no Chromium) and
#        every tool the installer runs. Most tools are already in releng.
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
ntfs-3g
EOF

# --- 2b. download and verify every package ourselves, before mkarchiso.
#        pacman run non-interactively (as mkarchiso does) answers "Do you want to
#        delete it?" with yes, destroying the evidence. Here pacman only computes
#        the list; curl fetches; tools/verify_pkgcache.py checks each file against
#        the repo database and MOVES damaged ones to build/quarantine/ with a report.
DLDB="$WORK/dldb"
rm -rf "$DLDB"; mkdir -p "$DLDB/local"
pacman --config "$PROFILE/pacman.conf" --dbpath "$DLDB" --logfile /dev/null -Sy
mapfile -t PKGS < <(grep -vE '^\s*(#|$)' "$PROFILE/packages.x86_64")
fetch() {
    pacman --config "$PROFILE/pacman.conf" --dbpath "$DLDB" --logfile /dev/null --noconfirm -Sp "${PKGS[@]}" \
        | grep -E '^(https?|ftp)://' > "$WORK/urls.txt" || true
    echo "Downloading $(wc -l < "$WORK/urls.txt") packages into $WORK/pkgcache..."
    (cd "$WORK/pkgcache" && xargs -a "$WORK/urls.txt" -r -P 6 -n 1 sh -c \
        'f=$(printf "%b" "$(basename "$1" | sed "s/%/\\\\x/g")"); curl -fsSL --connect-timeout 20 --speed-limit 2048 --speed-time 30 --retry 4 --retry-delay 2 --retry-all-errors -o "$f.part" "$1" && mv "$f.part" "$f" || echo "download failed: $1"' _)
}
verify() {
    /usr/bin/python -I "$ROOT/tools/verify_pkgcache.py" "$WORK/pkgcache" --dbpath "$DLDB" --quarantine "$WORK/quarantine"
}
fetch
if ! verify; then
    echo "Damaged packages were quarantined (not deleted). Downloading fresh copies..."
    fetch
    verify || { echo "Still damaged after a fresh download: see $WORK/quarantine/*/REPORT.txt"; exit 1; }
fi

# --- 3. the app
mkdir -p "$PROFILE/airootfs/opt"
cp -r "$ROOT/linusetup" "$PROFILE/airootfs/opt/linusetup"
find "$PROFILE/airootfs/opt/linusetup" -name __pycache__ -prune -exec rm -rf {} +
rm -f "$PROFILE/airootfs/opt/linusetup/ui/js/selftest.js" "$PROFILE/airootfs/opt/linusetup/ui/js/tour.js"

# --- 4. seatd for cage (cage as root on tty1 normally works through logind;
#        seatd is the fallback, see DECISIONS.md "Live-ISO risks").
mkdir -p "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants"
ln -sf /usr/lib/systemd/system/seatd.service \
    "$PROFILE/airootfs/etc/systemd/system/multi-user.target.wants/seatd.service"

# --- 5. autostart on tty1.
#   * QEMU passed a config via fw_cfg  -> unattended install, log to serial, power off
#   * otherwise                         -> the GUI in a single-app Wayland kiosk
# Real install mode is opt-in via LINUSETUP_REAL=1 and also needs /run/archiso and root.
cat >> "$PROFILE/airootfs/root/.zlogin" <<'EOF'

# ---------------------------------------------------------------- LinuSetup
# Kernel command line switches: linusetup.shell (skip the installer),
# linusetup.dry (rehearse everything without changing anything),
# linusetup.effects=minimal|balanced|full (animation level).
if [[ -z "${WAYLAND_DISPLAY:-}" && "$(tty)" == /dev/tty1 ]] && ! grep -q 'linusetup.shell' /proc/cmdline; then
    export LINUSETUP_REAL=1
    grep -q 'linusetup.dry' /proc/cmdline && export LINUSETUP_DRY_RUN=1
    modprobe qemu_fw_cfg 2>/dev/null
    # Test VMs: `make vm` passes a caching package mirror on the host (tools/pkgproxy.py).
    mirror_cfg=/sys/firmware/qemu_fw_cfg/by_name/opt/linusetup/mirror/raw
    if [[ -r $mirror_cfg ]]; then
        export LINUSETUP_LOCAL_MIRROR="$(cat "$mirror_cfg")"
        sed -i "1i Server = $LINUSETUP_LOCAL_MIRROR/\$repo/os/\$arch" /etc/pacman.d/mirrorlist
    fi
    if [[ -e /sys/firmware/qemu_fw_cfg/by_name/opt/linusetup/config.json/raw ]]; then
        echo "LinuSetup: unattended install (config from QEMU fw_cfg)" | tee /dev/ttyS0
        (cd /opt && python -m linusetup auto --fw-cfg) 2>&1 | tee /var/log/linusetup-auto.log > /dev/ttyS0
        sync; sleep 3; poweroff
    else
        export XDG_RUNTIME_DIR=/run/user/0
        mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
        export LIBSEAT_BACKEND=logind          # try "seatd" if cage reports a session error
        export WLR_NO_HARDWARE_CURSORS=1       # software cursor: reliable in VMs
        # WebKit rendering mode and the animation level are picked by LinuSetup from the
        # hardware; force a level with linusetup.effects=minimal|balanced|full
        fx=$(grep -o 'linusetup.effects=[a-z]*' /proc/cmdline | cut -d= -f2)
        [[ -n "$fx" ]] && export LINUSETUP_EFFECTS="$fx"
        cd /opt && cage -s -- python -m linusetup > /var/log/linusetup-gui.log 2>&1
        echo "LinuSetup exited. Log: /var/log/linusetup-gui.log   Retry: cd /opt && python -m linusetup"
    fi
fi
EOF

# --- 6. build
mkarchiso -v -w "$WORK/work" -o "$ROOT/out" "$PROFILE"
# Hand the output back to the invoking user so `make vm`/`make clean` need no root.
if [[ -n "${SUDO_UID:-}" ]]; then chown "$SUDO_UID:${SUDO_GID:-$SUDO_UID}" "$ROOT/out" "$ROOT"/out/*.iso; fi
echo "ISO ready:"; ls -lh "$ROOT"/out/*.iso
