# LinuSetup: decisions, verification and known risks

Built unattended. Read this before the first real install.

## What is verified, and how

Nothing here was run as root, so **no real install, ISO build or ISO boot happened
on the development machine**. Everything else was checked as directly as possible:

| Check | What it proves | Run it |
|---|---|---|
| Image tests (7) | The partition commands LinuSetup generates, applied by the **real `sgdisk`** to sparse disk images (blank, and a Windows-like ESP/MSR/NTFS/Recovery table), produce exactly the intended table. Partitions that are kept stay **byte-identical** (start, size, type, GUID, name); a shrunk Windows partition keeps its start, type, GUID and name. | `make test` |
| Layout tests (20) | Every guided scope (erase / free space / shrink) and manual-editor rule, including refusals: BitLocker, MBR, too small, overlap, encrypted `/` without `/boot`, BIOS without `bios_grub`. | `make test` |
| Plan matrix (300+ configs) | Every combination of firmware × filesystem × encryption × scope × swap × /home × boot loader builds a plan that keeps the ordering rules (partition → format → mount → pacstrap → chroot → unmount), never puts a secret in argv or logs, touches only the chosen disk, uses `sd-encrypt` iff `/` is encrypted, and completes as a dry run with monotonic progress. | `make test` |
| Package resolution | Every profile, every driver, every VM tool set, an "everything at once" set and **the live ISO's own package list** resolve with `pacman -Sp` against an empty local DB (= a fresh disk, what pacstrap sees), plus a version-aware conflict check (pacman -Sp does not detect conflicts itself). The checker is itself tested on a real conflict. | `make test` |
| Name tables | Console keymaps exist in kbd, XKB layouts/variants/options exist in xkb, locales exist in glibc. | `make test` |
| systemd units | Every unit any plan enables (24 distinct) is shipped, per the repos' file lists, by a package that same plan installs. A wrong name would otherwise only fail at the very last install step. | `make filesdb && make test` |
| API + CLI | Stale-disk refusal (fingerprints), validation, preview, config export strips every secret, `plan`/`check` commands. | `make test` |
| UI self-test (13 steps) | The real UI is clicked through, Easy and Advanced, including manual partitioning, a double-click race and a back/forward race, in **headless Firefox at 1280×800, 1024×768, 800×600** and in the **real pywebview/WebKitGTK window inside a headless cage compositor**. No JS errors, no horizontal overflow, Continue always on screen. | `make selftest` |
| Screenshots | Every screen rendered by WebKitGTK's own snapshot API (never a screen capture). | `make screens` |
| E2E runner | `tools/e2e.py` runs (as a permanent test) against a fake QEMU that plays the install banner, LUKS prompt, login and shell, and fails fast on a silent ISO; the e2e configs validate on matching virtual hardware; the dual-boot disk preparation really creates a FAT ESP. Unattended installs wait up to 3 minutes for the network instead of failing at once (tested with a fake clock). | `make test` |

**Not verified (needs your machine, `make iso` + `make e2e-all`):** the ISO build, the
live boot and cage on it, a real pacstrap, mkinitcpio/sd-encrypt at boot, systemd-boot and
GRUB actually booting, os-prober inside arch-chroot, ntfsresize on a real Windows volume,
the AUR helper build, Wi-Fi via iwctl. `make e2e-all` checks most of these automatically.

## Safety model

- **Dry run unless all of:** `/run/archiso` exists, running as root, `LINUSETUP_REAL=1`
  (only the ISO's autostart sets it), `LINUSETUP_DRY_RUN` not set. A unit test asserts a
  dry run never calls `subprocess`. Boot the ISO with `linusetup.dry` to rehearse safely.
- **Stale-table guard:** every disk's partition table is fingerprinted when shown; the
  install is refused if any disk it would touch changed since.
- **Plain-language confirmation** lists every wipe, delete, shrink, create and format, and
  requires typing the disk's name.
- **Disk listing** never offers the live medium, marks disks with mounted partitions or
  under 20 GB unusable, and the backend re-validates everything (the UI is not trusted).
- **Shrinking Windows:** refuses BitLocker; always runs `ntfsresize --no-action` first and
  never `--force` (a hibernated / Fast Startup volume fails with a clear message); keeps
  2 GB headroom above ntfsresize's minimum; rewrites the GPT entry with the same start,
  type GUID, unique GUID and name in one `sgdisk` call.
- **Reused Windows ESP** is mounted at `/efi` and never reformatted; GRUB is used (systemd-boot
  needs kernels on the ESP, which a 100 MB Windows ESP can't hold), and the removable
  fallback loader is only installed on an ESP LinuSetup created.
- **Secrets** (passwords, LUKS passphrase, Wi-Fi key) go to programs on stdin only, are
  scrubbed from logs/events, and are never written to exported configs.

## Notable technical findings

- **GPU vendor detection bug (fixed):** the vendor check matched "ati" inside "Intel Corpor*ati*on",
  so every Intel GPU was treated as AMD and would have got AMD drivers. Now whole-word matching on
  lspci's vendor field, with a regression test.

- **mkinitcpio 42 defaults to a systemd initramfs** (`base systemd … sd-vconsole …`) and
  ships microcode as a hook. LinuSetup always writes an explicit drop-in in
  `/etc/mkinitcpio.conf.d/`, adds `sd-encrypt` for encrypted `/`, drops `kms` for NVIDIA,
  and boot entries need no separate microcode initrd.
- **releng's `pacman.conf` has `[multilib]` commented out** and mkarchiso does not copy the
  profile's `pacman.conf` into the image, so `iso/build.sh` ships an edited copy via airootfs.
- **pywebview serves the page from its own local HTTP server**, not `file://`. The
  previous UI started talking to the wrong backend before pywebview was ready, which left
  a blank window. Found by running the self-test inside real WebKitGTK; fixed in `main.js`.
- `lsblk` reports partition `START` in 512-byte units on every disk; all positions are kept
  in bytes and converted with the disk's logical sector size for `sgdisk`.

## Features

Guided: erase disk, use free space next to other systems, shrink Windows · ext4/Btrfs/XFS/F2FS ·
Btrfs subvolumes, zstd/lzo, Snapper snapshots (+ grub-btrfs with GRUB) · separate /home ·
LUKS2 (sd-encrypt; extra encrypted volumes unlock with key files) · swap: zram, swap file
(incl. Btrfs), swap partition.
Manual: per-disk editor: erase to fresh GPT, delete, create in free space, reuse/format
existing partitions, any mount point, per-partition encryption, BIOS boot partitions, "suggest a layout".
Boot: systemd-boot or GRUB (UEFI and BIOS), os-prober, several kernels (linux, lts, zen,
hardened) with headers, kernel parameters, menu timeout.
System: 17 profiles (8 desktops, 7 window managers, server, minimal), 4 login screens + autologin, GPU and VM driver detection,
PipeWire, Bluetooth, printing, ufw/firewalld, SSH, NetworkManager or networkd+iwd (with Wi-Fi
credentials carried over), 44 software bundles in 6 categories, any repo package via live search, Flatpak +
Flathub, yay/paru, extra services, a custom post-install script, locales/keyboard (console +
X11/Wayland + KDE)/timezone/NTP, reflector mirrors by country or custom mirrors, parallel
downloads, multilib.
Effects: three animation levels (Minimal / Balanced / Full) picked from the GPU name lspci
reports (integrated, weak, mid, strong; VMs, under 4 GB RAM or 2 threads force Minimal), stepped
down when the measured frame rate is low, switchable from the header badge, forceable with
`linusetup.effects=` on the ISO. WebKit GPU compositing is now only disabled in VMs or without a
GPU render node (it was off everywhere, so every animation was painted by the CPU). Classifier
tested against 34 real pci.ids names.
UX: Easy (4 questions) and Advanced (9 sections, live validation per section) share one
review screen with every command visible; save/load configs; Wi-Fi from the installer;
unattended installs from QEMU fw_cfg; after-install restart/power-off.

**Left out on purpose** (roadmap, never shown in the UI): LVM/RAID, Secure Boot/UKI,
Limine, hibernation, an encrypted swap partition, resizing non-NTFS partitions, editing MBR
tables (erase converts to GPT), WPA-Enterprise Wi-Fi, custom repositories, a translated UI.

## Live-ISO risks (look here first)

1. **`make iso` failed with "invalid or corrupted package (PGP signature)"** for 29 packages,
   all reused from the host's `/var/cache/pacman/pkg` (the 528 freshly downloaded ones were fine).
   pacman, run non-interactively by mkarchiso, deleted them, so the cause is unknown: they were
   downloaded and verified days earlier; the rest of the cache, all boot-critical installed files
   and the kernel log were clean. Now: the build uses its own cache (`build/pkgcache`), downloads
   with curl, and `tools/verify_pkgcache.py` checks every file against the repo database and
   **moves** damaged ones to `build/quarantine/<time>/` with a REPORT.txt (zero-byte runs suggest
   a power cut or the disk; scattered changes suggest RAM). Fresh copies are then downloaded.
2. **cage fails with a seat/session error** → in `iso/build.sh` change
   `LIBSEAT_BACKEND=logind` to `seatd` (seatd is installed and enabled).
3. **Blank WebKit view** → both `WEBKIT_DISABLE_COMPOSITING_MODE` and
   `WEBKIT_DISABLE_DMABUF_RENDERER` are set; the UI also drops decorative effects when it
   measures under 28 fps. GUI log: `/var/log/linusetup-gui.log`.
4. **Debug escape hatch:** boot with `linusetup.shell` for a plain root shell.
5. **os-prober** sometimes finds nothing inside arch-chroot; the Done screen tells the user
   to run `grub-mkconfig` once after the first boot.
