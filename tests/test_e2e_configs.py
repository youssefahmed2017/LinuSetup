"""The end-to-end configs (tests/e2e/*.json) must validate and build a plan on
matching virtual hardware, so `make e2e` failures are about the system, not typos."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from linusetup.installer import config as CFG
from linusetup.installer import disks as D
from linusetup.installer import plan as PL
from linusetup.installer import validate as V
from linusetup.installer.disks import MiB, GiB
from tests.helpers import hw

E2E = Path(__file__).parent / "e2e"
ROOT = Path(__file__).parent.parent


def vda(dualboot):
    d = D.Disk(path="/dev/vda", name="vda", model="QEMU disk", size=(60 if dualboot else 40) * GiB,
               pttype="gpt" if dualboot else "")
    if dualboot:
        p = lambda n, s, sz, g, fs: D.Partition(n, f"/dev/vda{n}", s * MiB, sz * MiB, g, f"uuid-{n}", "", fs)
        d.partitions = [p(1, 1, 260, D.ESP, "vfat"), p(2, 261, 16, D.MSR, ""), p(3, 277, 20480, D.MS_DATA, "")]
    return d


class E2EConfigs(unittest.TestCase):
    def test_configs_validate_and_plan(self):
        files = sorted(E2E.glob("*.json"))
        self.assertGreaterEqual(len(files), 5)
        for f in files:
            with self.subTest(config=f.name):
                raw = json.loads(f.read_text())
                opts = raw.get("_e2e", {})
                cfg = CFG.normalize(raw)
                h = hw(uefi=not opts.get("bios"), virt="kvm", gpus=[])
                disks = [vda(opts.get("prepare") == "dualboot")]
                res = V.check(cfg, h, disks, online=True, real=True)
                self.assertEqual(res["errors"], [], f.name)
                plan = PL.build(cfg, h, disks)
                self.assertIn("console=ttyS0,115200", " ".join(
                    str(a.content) if isinstance(a, PL.Write) and isinstance(a.content, str) else ""
                    for s in plan.steps for a in s.actions) + cfg["kernel_params"])
                if opts.get("prepare") == "dualboot":
                    self.assertTrue(plan.layout.dual_boot)
                    self.assertEqual(plan.bootloader, "grub")

    def load_runner(self):
        spec = importlib.util.spec_from_file_location("e2e", ROOT / "tools" / "e2e.py")
        e2e = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(e2e)
        return e2e

    @unittest.skipUnless(shutil.which("qemu-img") and Path("/usr/share/edk2/x64/OVMF_VARS.4m.fd").exists(), "qemu/ovmf missing")
    def test_runner_against_fake_qemu(self):
        """The serial-console logic: banner, success marker, LUKS prompt, login, checks, verdict."""
        import sys
        from unittest import mock
        e2e = self.load_runner()
        fake = str(Path(__file__).parent / "fake_qemu.py")
        with tempfile.TemporaryDirectory() as tmp:
            iso = Path(tmp) / "x.iso"
            iso.touch()
            def run(phase_install, phase_boot="boot", extra=()):
                e2e.qemu = lambda disk, fmt, bios, vars_fd, iso=None, fwcfg=None: \
                    [sys.executable, fake, phase_install if iso else phase_boot, "e2e-luks-pass"]
                argv = ["e2e.py", str(E2E / "btrfs-luks.json"), "--iso", str(iso), "--quiet", *extra]
                with mock.patch.object(sys, "argv", argv), mock.patch.object(e2e, "ROOT", Path(tmp)):
                    return e2e.main()
            self.assertEqual(run("install"), 0)
            res = json.loads((Path(tmp) / "build/e2e/btrfs-luks/result.json").read_text())
            self.assertTrue(res["luks_prompt"])
            self.assertEqual((res["hostname"], res["rootfs"], res["state"], res["sudo"]), ("e2e-btrfs", "btrfs", "running", True))
            self.assertEqual(run("silent", extra=["--banner-timeout", "3"]), 1)

    @unittest.skipUnless(all(shutil.which(t) for t in ("sgdisk", "mkfs.fat", "blkid")), "tools missing")
    def test_dualboot_disk_preparation(self):
        e2e = self.load_runner()
        with tempfile.TemporaryDirectory() as tmp:
            disk, fmt = e2e.prepare_disk(Path(tmp), "dualboot")
            self.assertEqual(fmt, "raw")
            table = json.loads(subprocess.run(["sfdisk", "-J", str(disk)], capture_output=True, text=True).stdout)
            parts = table["partitiontable"]["partitions"]
            self.assertEqual([p["type"].upper() for p in parts], [D.ESP, D.MSR, D.MS_DATA])
            probe = subprocess.run(["blkid", "-p", "-O", str(parts[0]["start"] * 512), "-o", "export", str(disk)],
                                   capture_output=True, text=True).stdout
            self.assertIn("TYPE=vfat", probe, "the ESP must really be FAT so it can be mounted and reused")


if __name__ == "__main__":
    unittest.main()
