#!/usr/bin/env python3
"""End-to-end test of a real install, fully unattended, in QEMU.

  tools/e2e.py tests/e2e/ext4-uefi.json [--iso out/x.iso] [--keep]

1. Boots the LinuSetup ISO with the config passed through QEMU fw_cfg. The ISO
   sees it and runs `linusetup auto` (a real install onto the empty virtual
   disk), logging to the serial port, then powers off.
2. Boots the installed disk alone, types the LUKS passphrase on the serial
   console if asked, logs in as the first user and checks the result:
   hostname, root filesystem, sudo, failed systemd units.

Options for a config live under its "_e2e" key: {"bios": true,
"prepare": "dualboot", "expect_fs": "btrfs"}.
Everything runs headless (-display none); logs go to build/e2e/<name>/.
"""
import argparse
import json
import os
import re
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OVMF_CODE = Path("/usr/share/edk2/x64/OVMF_CODE.4m.fd")
OVMF_VARS = Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd")
ANSI = re.compile(rb"\x1b\[[0-9;?]*[A-Za-z]")


class Console:
    """A QEMU process with its serial port on stdio."""

    def __init__(self, argv, log_path, echo=True):
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, bufsize=0)
        self.log = open(log_path, "wb")
        self.buf, self.pos, self.echo = b"", 0, echo

    def expect(self, patterns, timeout):
        """Index of the first pattern seen after the last match, None on timeout, -1 if QEMU exited."""
        pats = [re.compile(p) if isinstance(p, bytes) else re.compile(p.encode()) for p in patterns]
        deadline = time.time() + timeout
        while True:
            clean = ANSI.sub(b"", self.buf[self.pos:])
            hits = [(m.end(), i) for i, p in enumerate(pats) for m in [p.search(clean)] if m]
            if hits:
                end, idx = min(hits)
                self.pos = len(self.buf)        # consume everything read so far
                return idx
            if time.time() > deadline:
                return None
            r, _, _ = select.select([self.p.stdout], [], [], 1.0)
            if r:
                chunk = os.read(self.p.stdout.fileno(), 65536)
                if not chunk:
                    return -1
                self.buf += chunk
                self.log.write(chunk)
                self.log.flush()
                if self.echo:
                    sys.stdout.buffer.write(chunk)
                    sys.stdout.flush()
            elif self.p.poll() is not None:
                return -1

    def text_since(self, start):
        return ANSI.sub(b"", self.buf[start:]).decode(errors="replace")

    def send(self, text, delay=0.05):
        for ch in text:                      # serial consoles drop fast bursts
            self.p.stdin.write(ch.encode())
            self.p.stdin.flush()
            time.sleep(delay)

    def wait_exit(self, timeout):
        try:
            return self.p.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill(self):
        if self.p.poll() is None:
            self.p.kill()
            self.p.wait()
        for f in (self.p.stdin, self.p.stdout, self.log):
            try:
                f.close()
            except OSError:
                pass


def qemu(disk, fmt, bios, vars_fd, iso=None, fwcfg=None):
    argv = ["qemu-system-x86_64", "-enable-kvm", "-cpu", "host", "-m", "4096", "-smp", "4",
            "-display", "none", "-serial", "stdio", "-monitor", "none", "-no-reboot",
            "-nic", "user,model=virtio-net-pci",
            "-drive", f"file={disk},if=virtio,format={fmt},cache=unsafe,discard=unmap"]
    if not bios:
        argv += ["-drive", f"if=pflash,format=raw,readonly=on,file={OVMF_CODE}",
                 "-drive", f"if=pflash,format=raw,file={vars_fd}"]
    if iso:
        argv += ["-cdrom", str(iso), "-boot", "d"]
    if fwcfg:
        argv += ["-fw_cfg", f"name=opt/linusetup/config.json,file={fwcfg}"]
    if iso and PROXY_PORT:
        argv += ["-fw_cfg", f"name=opt/linusetup/mirror,string=http://10.0.2.2:{PROXY_PORT}"]
    return argv


PROXY_PORT = None


def start_proxy(port=8082):
    """The caching mirror (tools/pkgproxy.py): repeat e2e runs don't re-download."""
    global PROXY_PORT
    (ROOT / "build").mkdir(parents=True, exist_ok=True)
    log = open(ROOT / "build" / "vmcache.log", "ab")
    p = subprocess.Popen([sys.executable, str(ROOT / "tools" / "pkgproxy.py"), "--port", str(port),
                          "--cache", str(ROOT / "build" / "vmcache"), "--seed", str(ROOT / "build" / "pkgcache")],
                         stdout=log, stderr=subprocess.STDOUT)
    time.sleep(1)
    PROXY_PORT = port if p.poll() is None else None
    _procs.append(p)
    return p


def prepare_disk(work, kind):
    """Create the target disk. 'dualboot' pre-partitions it like a Windows PC
    (formatted ESP, MSR, a 'Windows' partition) with free space left over."""
    if kind == "dualboot":
        disk = work / "disk.raw"
        subprocess.run(["truncate", "-s", "60G", disk], check=True)
        subprocess.run(["sgdisk", "-n1:2048:+260M", "-t1:ef00", "-c1:EFI system partition",
                        "-n2:0:+16M", "-t2:0c01", "-c2:Microsoft reserved partition",
                        "-n3:0:+20G", "-t3:0700", "-c3:Basic data partition", str(disk)],
                       check=True, capture_output=True)
        subprocess.run(["mkfs.fat", "-F", "32", "-n", "SYSTEM", "--offset", "2048", str(disk), str(260 * 1024)],
                       check=True, capture_output=True)
        return disk, "raw"
    disk = work / "disk.qcow2"
    subprocess.run(["qemu-img", "create", "-q", "-f", "qcow2", disk, "40G"], check=True)
    return disk, "qcow2"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("--iso")
    ap.add_argument("--keep", action="store_true", help="keep the disk image afterwards")
    ap.add_argument("--quiet", action="store_true", help="don't echo the serial console")
    ap.add_argument("--install-timeout", type=int, default=5400)
    ap.add_argument("--banner-timeout", type=int, default=420)
    ap.add_argument("--no-proxy", action="store_true", help="download from the internet, not the local cache")
    args = ap.parse_args()

    cfg_path = Path(args.config).resolve()
    cfg = json.loads(cfg_path.read_text())
    opts = cfg.get("_e2e", {})
    bios = bool(opts.get("bios"))
    name = cfg_path.stem
    iso = Path(args.iso) if args.iso else max((ROOT / "out").glob("*.iso"), key=os.path.getmtime, default=None)
    if not iso or not iso.exists():
        sys.exit("No ISO found. Run `make iso` first.")
    work = ROOT / "build" / "e2e" / name
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    disk, fmt = prepare_disk(work, opts.get("prepare"))
    proxy = start_proxy() if not args.no_proxy else None
    vars_fd = work / "OVMF_VARS.fd"
    if not bios:
        shutil.copy(OVMF_VARS, vars_fd)
    user = cfg["users"][0]
    t0 = time.time()
    result = {"config": name, "bios": bios, "iso": iso.name}

    # ---------------------------------------------------------------- install
    print(f"\n=== [{name}] installing from {iso.name} ({'BIOS' if bios else 'UEFI'})", flush=True)
    c = Console(qemu(disk, fmt, bios, vars_fd, iso=iso, fwcfg=cfg_path), work / "install.log", echo=not args.quiet)
    # The live ISO doesn't log to serial, so silence means it never reached the autostart.
    if c.expect([b"LinuSetup: unattended install"], args.banner_timeout) != 0:
        c.kill()
        print(f"\nE2E FAIL [{name}]: the ISO did not start the unattended install within "
              f"{args.banner_timeout}s. Run `make vm` to watch it boot. Log: {work / 'install.log'}")
        return 1
    hit = c.expect([b"LINUSETUP-SUCCESS", b"LINUSETUP-FAILED"], args.install_timeout)
    if hit != 0:
        c.kill()
        reason = {None: "timed out", -1: "QEMU exited before finishing", 1: "the installer reported a failure"}[hit]
        print(f"\nE2E FAIL [{name}]: install {reason}. Log: {work / 'install.log'}")
        return 1
    c.wait_exit(240)
    c.kill()
    result["install_minutes"] = round((time.time() - t0) / 60, 1)

    # ---------------------------------------------------------------- first boot
    print(f"\n=== [{name}] booting the installed system", flush=True)
    c = Console(qemu(disk, fmt, bios, vars_fd), work / "boot.log", echo=not args.quiet)
    luks = cfg.get("disk", {}).get("encryption", {}).get("passphrase")
    deadline = time.time() + 600
    while True:
        hit = c.expect([b"[Pp]assphrase for", b"login: *$", b"login:"], max(1, deadline - time.time()))
        if hit == 0:
            if not luks:
                break
            result["luks_prompt"] = True
            time.sleep(1)
            c.send(luks + "\r")
            continue
        break
    if hit not in (1, 2):
        c.kill()
        print(f"\nE2E FAIL [{name}]: no login prompt on the serial console. Log: {work / 'boot.log'}")
        return 1
    time.sleep(2)
    c.send(user["username"] + "\r")
    if c.expect([b"Password:"], 30) != 0:
        c.kill()
        print(f"\nE2E FAIL [{name}]: no password prompt")
        return 1
    c.send(user["password"] + "\r")
    if c.expect([rb"\$ *$", rb"\$ "], 60) is None:
        c.kill()
        print(f"\nE2E FAIL [{name}]: login as {user['username']} failed")
        return 1
    start = len(c.buf)
    pw = user["password"].replace("'", "'\\''")
    c.send("echo E2E-$((40+2))-BEGIN; cat /etc/hostname; findmnt -no FSTYPE /; "
           "timeout 180 systemctl is-system-running --wait; "
           "systemctl --failed --no-legend --plain | awk '{print \"FAILED-UNIT \" $1}'; "
           f"echo '{pw}' | sudo -S -p '' true && echo SUDO-OK; "
           "echo E2E-$((40+3))-END\r", delay=0.02)
    if c.expect([b"E2E-43-END"], 300) != 0:
        c.kill()
        print(f"\nE2E FAIL [{name}]: checks did not finish")
        return 1
    out = c.text_since(start)
    body = out.split("E2E-42-BEGIN", 1)[-1].split("E2E-43-END", 1)[0]
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    c.send("sudo -S poweroff\r")
    time.sleep(1)
    c.send(user["password"] + "\r")
    c.wait_exit(60)
    c.kill()

    want_host = cfg.get("hostname")
    want_fs = opts.get("expect_fs") or cfg.get("disk", {}).get("fs", "ext4")
    result.update(hostname=lines[0] if lines else "", rootfs=lines[1] if len(lines) > 1 else "",
                  state=lines[2] if len(lines) > 2 else "",
                  failed_units=[l.split()[1] for l in lines if l.startswith("FAILED-UNIT")],
                  sudo=any(l == "SUDO-OK" for l in lines))
    problems = []
    if result["hostname"] != want_host:
        problems.append(f"hostname is '{result['hostname']}', expected '{want_host}'")
    if result["rootfs"] != want_fs:
        problems.append(f"root filesystem is '{result['rootfs']}', expected '{want_fs}'")
    if not result["sudo"]:
        problems.append("sudo does not work for the first user")
    if result["state"] not in ("running", "degraded"):
        problems.append(f"system state is '{result['state']}'")
    result["problems"] = problems
    (work / "result.json").write_text(json.dumps(result, indent=2))
    if not args.keep:
        disk.unlink(missing_ok=True)
    print(f"\n=== [{name}] {'PASS' if not problems else 'FAIL'}  "
          f"(install {result['install_minutes']} min, state {result['state']}"
          f"{', failed units: ' + ', '.join(result['failed_units']) if result['failed_units'] else ''})")
    for p in problems:
        print("    - " + p)
    return 1 if problems else 0


def run():
    try:
        return main()
    finally:
        for p in list(_procs):
            p.terminate()


_procs = []

if __name__ == "__main__":
    sys.exit(run())
