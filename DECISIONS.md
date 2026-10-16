# LinuSetup: decisions and status (v0.1)

Written while building unattended. Read this first if something misbehaves.

## What was verified, and what was NOT

Verified on the dev machine (no sudo, no ISO build, no VM boot possible there):

- `make test`: 13 unit tests pass (plan building, validation, dry-run runner,
  real-mode guard, and **every package name resolved against the host's pacman
  repos, including multilib**).
- `/usr/bin/python -c "import webview, gi"` works; `python -m linusetup --windowed
  --dry-run` opens and runs 10 s with no errors on stderr.
- All six UI screens rendered in headless Firefox (mock backend) and inspected.
- `bash -n iso/build.sh`, `make -n` for every target, `node --check` on the JS.

**Never run:** `make iso`, the ISO boot, `cage` inside the ISO, any real
partitioning or `pacstrap`, the installed-system boot, BIOS/GRUB path, the
pywebview<->Python event bridge inside the live window (only the mock was
exercised end to end). Expect first-boot issues there; see "Live-ISO risks".

## Safety: the backend cannot touch this machine's disks

- Real execution requires ALL of: `/run/archiso` exists, running as root,
  `LINUSETUP_REAL=1`, and `LINUSETUP_DRY_RUN` not set (`runner.real_mode_allowed`).
  Only the ISO's `.zlogin` sets `LINUSETUP_REAL=1`. On any normal machine the app
  is dry-run: it builds and logs the full command plan and executes nothing.
- A unit test asserts dry-run never calls `subprocess` and that real mode is
  refused when the live marker is absent.
- Disk list excludes loop/optical/zram devices and the live medium, marks disks
  with mounted partitions or < 20 GB as unusable, and the backend re-validates the
  chosen disk against that list (the UI is not trusted).
- Destructive step needs a typed confirmation of the device name (e.g. `vda`).
- Boot the ISO with `linusetup.dry` on the kernel command line to rehearse the
  whole UI inside the VM without any changes.

## Scope

- **Erase-whole-disk only.** "Install alongside Windows" is shown on NTFS disks
  as "coming soon" and does nothing: automated NTFS resizing untested and
  unattended is the one feature that could destroy someone's data.
- KDE Plasma only (minimal). ext4 only (Btrfs + snapshots is a good v0.2).
- Layout: GPT. UEFI: 1 GiB ESP at `/boot` + ext4 root, **systemd-boot**.
  BIOS: 1 MiB `bios_grub` + ext4 root, **GRUB**. Chosen by `/sys/firmware/efi`.
- Needs internet (pacstrap from mirrors). No Wi-Fi UI yet: wired only.
  The welcome screen shows connectivity.
- Locale fixed to `en_US.UTF-8`; keyboard layout chosen applies to the console
  (`vconsole.conf`) only, not yet to the Plasma session.

## Installed system choices

- Microcode (`intel-ucode`/`amd-ucode`) detected from `/proc/cpuinfo`.
- GPU drivers from `lspci`: nvidia -> `nvidia-open`, amd/intel -> mesa + vulkan.
- Services enabled: NetworkManager, sddm, bluetooth, systemd-timesyncd (+ docker
  for the Coding preset). Without NetworkManager/sddm the system would boot to a
  TTY with no network.
- User in `wheel` (+ `docker`), `/etc/sudoers.d/10-wheel`, root account locked,
  passwords set via `chpasswd` over stdin (never in argv or logs).
- `genfstab -U`, hostname, hosts, locale, timezone, `hwclock --systohc`.

## Gaming preset and multilib (finding)

`/usr/share/archiso/configs/releng/pacman.conf` has `[multilib]` **commented
out**, and `pacstrap` uses the *live* system's `/etc/pacman.conf`. mkarchiso
(checked in `/usr/bin/mkarchiso`) uses the profile's `pacman.conf` only to
*build* the image; it is **not** copied into it, so editing the profile copy
alone would leave the live system without multilib and `pacstrap` would fail
with `target not found: steam`. `iso/build.sh` therefore enables multilib in the
profile copy (aborting if the sed fails) **and** ships that file as
`airootfs/etc/pacman.conf`. The plan also enables it in the target's
`pacman.conf` when a preset needs it. (Not yet confirmed inside a booted ISO:
check `grep -A1 '^\[multilib\]' /etc/pacman.conf` there if Gaming fails.)

Also checked: `sddm` depends on `xorg-server`, so the installed login screen
has the X server it needs.
Steam's `lib32-vulkan-driver` dependency has several providers and `pacstrap`
runs non-interactively, so the plan always lists explicit 32-bit Vulkan packages
(per detected GPU, or a mesa/radeon fallback in VMs) to avoid a random pick.

## UI

Draft B ("big cards") with animations. Constraints chosen for a software-rendered
VM: **only `transform`/`opacity` animations**, no `backdrop-filter`, no large
blurs, no web fonts or CDNs (works offline over `file://`), inline SVG icons
(the ISO has no emoji font by default; `noto-fonts` is installed, icons are SVG
anyway). `prefers-reduced-motion` is honoured, and the page auto-switches to a
"lite" mode (no tilt/glow/floating dots) if it measures < 28 fps in its first
second (force with `?lite`).
Mouse features: click ripple, hover tilt with a moving highlight, cursor glow,
custom right-click menu on preset cards (lists packages), no native context
menu. **F2** toggles a pointer debug overlay (position + last button), useful
when testing input in QEMU.
Dev hooks (browser only): `index.html?mock&still&screen=disk`.

## Live-ISO risks (look here first)

1. **cage fails with a session/seat error as root.** `seatd` is installed and
   enabled in the image; `.zlogin` sets `LIBSEAT_BACKEND=logind`. If cage
   complains, change it to `seatd` in `iso/build.sh`.
2. **Blank/black WebKit view in a GL-less VM.** Mitigated with
   `WEBKIT_DISABLE_COMPOSITING_MODE=1` and `WEBKIT_DISABLE_DMABUF_RENDERER=1`
   (both strings confirmed present in the installed webkit2gtk 2.52 library).
3. **Pointer invisible/offset.** `WLR_NO_HARDWARE_CURSORS=1` + QEMU `usb-tablet`
   (absolute pointer). Press F2 in the app to see what coordinates it receives.
4. **Debugging a dead kiosk.** Boot with `linusetup.shell` on the kernel command
   line to skip the autostart and get the normal root shell; the app log is
   `/tmp/linusetup.log`. Run `cd /opt && python -m linusetup --windowed` from a
   shell to retry.
5. **pacstrap progress** is parsed from pacman's `(n/total)` lines; if the format
   differs the bar just jumps at step boundaries (cosmetic).
6. `bootctl install` inside arch-chroot needs efivars; if it warns in the VM,
   the fallback path `EFI/BOOT/BOOTX64.EFI` is still installed.

## Next steps (suggested order)

1. Run it in the VM (README), fix whatever the risks above turn up.
2. Wi-Fi picker (iwd/NetworkManager) on the welcome screen.
3. Btrfs + snapper option; apply keyboard layout to Plasma.
4. Alongside-Windows (needs resize with `ntfsresize`/`parted`, tested on throwaway images first).
5. Offline package cache in the ISO.
