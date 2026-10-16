"""Stands in for qemu-system-x86_64 in tests of tools/e2e.py. Plays a live ISO
(install phase) or an installed system (boot phase) on the 'serial console'.
  fake_qemu.py install|boot|silent  [luks-passphrase]"""
import sys
import time

phase = sys.argv[1]
luks = sys.argv[2] if len(sys.argv) > 2 else ""


def out(s):
    sys.stdout.write(s)
    sys.stdout.flush()


def readline():
    buf = ""
    while True:
        ch = sys.stdin.read(1)
        if not ch:
            sys.exit(0)
        out(ch)                      # terminal echo
        if ch == "\r":
            return buf
        buf += ch


if phase == "silent":
    time.sleep(30)
    sys.exit(0)
if phase == "install":
    out("LinuSetup: unattended install (config from QEMU fw_cfg)\r\n=== [1/9] Getting ready\r\n")
    time.sleep(0.3)
    out("LINUSETUP-SUCCESS\r\n")
    sys.exit(0)
if luks:
    out("\x1b[0mBooting...\r\nPlease enter passphrase for disk QEMU (cryptroot): ")
    if readline() != luks:
        sys.exit(3)
out("\r\n\r\nArch Linux (ttyS0)\r\n\r\ne2e-btrfs login: ")
user = readline()
out("\r\nPassword: ")
pw = readline()
if (user, pw) != ("tester", "e2e-Passw0rd"):
    out("\r\nLogin incorrect\r\n")
    sys.exit(4)
out("\r\n[tester@e2e-btrfs ~]$ ")
cmd = readline()
if "E2E-$((40+2))-BEGIN" not in cmd:
    sys.exit(5)
out("\r\nE2E-42-BEGIN\r\ne2e-btrfs\r\nbtrfs\r\nrunning\r\nSUDO-OK\r\nE2E-43-END\r\n[tester@e2e-btrfs ~]$ ")
readline()
out("\r\n[sudo] password: ")
readline()
out("\r\nPowering off\r\n")
