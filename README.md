# LinuSetup

A friendly, mouse-first graphical installer for Arch Linux with its own live ISO.
UI: pywebview on **WebKitGTK** (no Chromium) inside a `cage` Wayland kiosk.
Engine: plain Python that builds a command plan and runs it (dry-run by default).

See [DECISIONS.md](DECISIONS.md) for scope, safety design and known risks.

## Run commands in a normal terminal

Use `/usr/bin/python`, not the project `.venv` (it cannot see system `gi`/`webview`).
Install once: `sudo pacman -S --needed python-pywebview python-gobject webkit2gtk-4.1 archiso qemu-desktop edk2-ovmf cage`

```bash
make test      # engine unit tests (13)
make dev       # real window on your desktop, ALWAYS dry-run on your machine
make preview   # open the UI in your browser with a mock backend (design iteration)

make iso       # build the live ISO into out/ (asks for your sudo password)
make vm        # boot it in QEMU, UEFI, with an empty 30 GB virtual target disk
make vm-boot   # after installing: boot the installed system from the virtual disk
make vm-bios   # same as vm, legacy BIOS (exercises the GRUB path)
make vm-reset  # throw away the virtual disk to install again
```

### First run in the VM, step by step

1. `make iso`, then `make vm`. The installer should appear full screen.
2. Press **F2** to show the pointer overlay: move/click/right-click, check it follows the mouse.
3. To rehearse safely first, add `linusetup.dry` to the kernel command line
   (press `e` in the boot menu); the whole flow runs without changing anything.
4. Walk the wizard, type the disk name to confirm, watch the install, then
   `make vm-boot` to boot what you installed.

If the screen stays on a text console, see "Live-ISO risks" in DECISIONS.md
(boot with `linusetup.shell` to get a shell; log at `/tmp/linusetup.log`).

## Layout

```
linusetup/
  app.py              pywebview window + js_api (no install logic)
  installer/          pure engine, no UI imports
    hardware.py       read-only detection: UEFI, CPU, GPU, disks, network
    presets.py        packages per use-case + GPU drivers
    config.py         user input + validation
    plan.py           config + hardware -> ordered steps (pure)
    runner.py         executes a plan; dry-run unless on the live ISO
  ui/                 index.html, css/app.css, js/app.js (offline, no CDN)
iso/build.sh          releng profile + overlay -> ISO
design/               the three early design drafts
tests/                unit tests
```
