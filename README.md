# LinuSetup

A graphical Arch Linux installer with its own live ISO. **Easy mode** asks four friendly
questions; **Advanced mode** exposes everything archinstall can do (and a manual partition
editor). Then you go touch grass while it installs.

- UI: pywebview on **WebKitGTK** (no Chromium) in a `cage` kiosk on the ISO. Mouse-first,
  animated, keyboard friendly, works from 800×600 up.
- Engine: plain Python. Builds the whole install as an explicit command plan (shown on the
  review screen), then runs it. Dry run everywhere except the live ISO.

See **[DECISIONS.md](DECISIONS.md)** for what was verified and how, the safety model, and known risks.

## Try it now (no ISO needed)

```bash
make demo       # the real window with pretend hardware: a Windows disk, a BitLocker disk...
make dev        # the real window reading THIS machine (always a dry run here)
make preview    # same UI in your browser: http://127.0.0.1:8765
```

Use `/usr/bin/python`, not the project `.venv` (it can't see the system `gi`/`webview`). Install once:

```bash
sudo pacman -S --needed python-pywebview python-gobject webkit2gtk-4.1 archiso qemu-desktop edk2-ovmf cage
```

## Build and test the ISO

```bash
make iso        # build out/*.iso (asks for sudo; fast zstd). RELEASE=1: small xz build
make vm         # boot it in QEMU (UEFI) with an empty 30 GB virtual disk; vm-bios for legacy BIOS.
                # Downloads go through a caching mirror on your PC (tools/pkgproxy.py, build/vmcache):
                # the first VM install downloads normally, every later one installs from disk.
make vm-boot    # boot what you installed
make e2e        # fully unattended: install tests/e2e/ext4-uefi.json, boot it, log in, check it
make e2e-all    # all five scenarios (ext4+systemd-boot, Btrfs+LUKS+snapshots, BIOS+GRUB+XFS,
                # dual boot next to a Windows-like disk, full KDE desktop)
```

`make e2e CONFIG=tests/e2e/btrfs-luks.json` runs one scenario. Logs and a `result.json`
land in `build/e2e/<name>/`. It types the LUKS passphrase and the login over the serial
console, then checks hostname, root filesystem, sudo and failed systemd units.

In the VM: press **F2** for a pointer overlay. Add `linusetup.dry` to the kernel command line to
rehearse without changes, or `linusetup.shell` for a plain shell.

## Develop

```bash
make test       # 69 tests: layout, real-sgdisk image tests, 300+ config plan matrix,
                # package resolution, API/CLI, e2e runner (1-2 minutes)
make filesdb    # once: download repo file lists so the systemd-unit test runs too
make selftest   # clicks through the whole UI headlessly: Firefox at 3 sizes + real WebKitGTK
make screens    # WebKitGTK screenshots of every screen -> build/screens/
python -m linusetup plan  my.json --fixtures   # print every command an install would run
python -m linusetup check my.json              # validate a saved config
```

## Layout

```
linusetup/
  app.py, api.py        pywebview window + the one API the UI talks to
  devserver.py          dev server: same API over HTTP, fixture hardware
  installer/            the engine (no UI imports)
    catalog.py          profiles, software, drivers, keyboards, mirrors
    config.py           the config document, defaults, secret stripping
    system.py           hardware, disks, Wi-Fi, package search (read-only)
    fixtures.py         pretend hardware for development and tests
    disks.py            partition-table model, free space, fingerprints
    layout.py           disk choices -> exact partition operations
    packages.py         config + hardware -> packages, services, groups
    plan.py             everything -> ordered commands
    validate.py         whole-config validation, grouped by UI section
    runner.py           executes a plan (dry run unless on the ISO)
  ui/                   index.html, css/app.css, js/*.js (no CDN, works offline)
iso/build.sh            releng + our overlay -> ISO
tools/                  e2e.py, selftest.sh, screens.sh, snap.py
tests/                  unit/image/package tests, e2e configs
design/                 the three early design drafts
```

## License

LinuSetup is free software under the [GNU General Public License v3.0 or later](LICENSE).
The ISO is built from official Arch Linux packages with archiso; it is not an official
Arch Linux release.
