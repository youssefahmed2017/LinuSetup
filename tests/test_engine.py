import shutil
import subprocess
import unittest
import zoneinfo
from unittest import mock

from linusetup.installer import presets as P
from linusetup.installer.config import InstallConfig, validate
from linusetup.installer.hardware import Hardware
from linusetup.installer.plan import Cmd, Write, build_plan, package_list, part_path
from linusetup.installer import runner as R

TZ = zoneinfo.available_timezones()


def cfg(**kw):
    base = dict(disk="/dev/vda", presets=["gaming", "coding"], username="sam",
                hostname="box", password="hunter22", timezone="UTC", keymap="us",
                fullname="Sam")
    base.update(kw)
    return InstallConfig(**base)


def hw(**kw):
    base = dict(uefi=True, cpu_vendor="amd", gpus=["amd"])
    base.update(kw)
    return Hardware(**base)


class PlanTests(unittest.TestCase):
    def test_part_path(self):
        self.assertEqual(part_path("/dev/sda", 2), "/dev/sda2")
        self.assertEqual(part_path("/dev/vda", 1), "/dev/vda1")
        self.assertEqual(part_path("/dev/nvme0n1", 2), "/dev/nvme0n1p2")
        self.assertEqual(part_path("/dev/mmcblk0", 1), "/dev/mmcblk0p1")

    def test_only_selected_disk_is_touched(self):
        for step in build_plan(cfg(), hw()):
            for a in step.actions:
                if isinstance(a, Cmd) and a.argv[0] in ("wipefs", "sgdisk", "partprobe", "grub-install"):
                    self.assertIn("/dev/vda", a.argv)
                if isinstance(a, Cmd) and a.argv[0].startswith("mkfs"):
                    self.assertTrue(a.argv[-1].startswith("/dev/vda"))

    def test_password_never_in_argv_or_plain_logs(self):
        for step in build_plan(cfg(), hw()):
            for a in step.actions:
                if isinstance(a, Cmd):
                    self.assertNotIn("hunter22", " ".join(a.argv))

    def test_uefi_vs_bios_bootloader(self):
        uefi = [a.argv for s in build_plan(cfg(), hw(uefi=True)) for a in s.actions if isinstance(a, Cmd)]
        bios = [a.argv for s in build_plan(cfg(), hw(uefi=False)) for a in s.actions if isinstance(a, Cmd)]
        self.assertTrue(any("bootctl" in a for a in uefi))
        self.assertFalse(any("grub-install" in a for a in uefi))
        self.assertTrue(any("grub-install" in a for a in bios))
        self.assertFalse(any(a[0] == "mkfs.fat" for a in bios))

    def test_microcode_and_services(self):
        pk, _ = package_list(cfg(), hw(cpu_vendor="intel"))
        self.assertIn("intel-ucode", pk)
        pk, _ = package_list(cfg(), hw(cpu_vendor="amd"))
        self.assertIn("amd-ucode", pk)
        enable = next(a.argv for s in build_plan(cfg(), hw()) for a in s.actions
                      if isinstance(a, Cmd) and "enable" in a.argv)
        for svc in ("NetworkManager", "sddm", "docker"):
            self.assertIn(svc, enable)

    def test_gaming_enables_multilib_and_has_vulkan_provider(self):
        pk, multilib = package_list(cfg(), hw(gpus=[]))
        self.assertTrue(multilib)
        self.assertIn("lib32-vulkan-radeon", pk)
        pk, multilib = package_list(cfg(presets=["coding"]), hw(gpus=[]))
        self.assertFalse(multilib)
        self.assertFalse(any(p.startswith("lib32-") for p in pk))

    def test_no_duplicate_packages(self):
        pk, _ = package_list(cfg(presets=list(P.PRESETS)), hw(gpus=["amd", "intel"]))
        self.assertEqual(len(pk), len(set(pk)))


class ValidationTests(unittest.TestCase):
    def check(self, **kw):
        validate(cfg(**kw), ["/dev/vda"], P.PRESETS.keys(), TZ)

    def test_ok(self):
        self.check()

    def test_rejects_bad_input(self):
        for bad in (dict(disk="/dev/sda"), dict(username="Root"), dict(username="root"),
                    dict(username="a b"), dict(hostname="-x"), dict(password="abc"),
                    dict(timezone="Mars/Base"), dict(keymap="klingon"),
                    dict(presets=["nope"]), dict(fullname="a:b"), dict(password="a\nb12")):
            with self.assertRaises(ValueError, msg=str(bad)):
                self.check(**bad)


class RunnerTests(unittest.TestCase):
    def test_real_mode_is_blocked_on_this_machine(self):
        # No /run/archiso here, so this must be False regardless of env vars.
        with mock.patch.dict("os.environ", {"LINUSETUP_REAL": "1"}):
            with mock.patch.object(R, "is_live", return_value=False):
                self.assertFalse(R.real_mode_allowed())

    def test_dry_run_executes_nothing(self):
        events = []
        with mock.patch("time.sleep"), mock.patch("subprocess.Popen") as popen, \
                mock.patch("subprocess.run") as run:
            R.Runner(build_plan(cfg(), hw()), events.append, dry_run=True).run()
        popen.assert_not_called()
        run.assert_not_called()
        self.assertEqual(events[-1], {"type": "done", "dry_run": True})
        progress = [e["value"] for e in events if e["type"] == "progress"]
        self.assertEqual(progress, sorted(progress))
        self.assertAlmostEqual(progress[-1], 1.0)
        self.assertNotIn("hunter22", str(events))

    def test_failure_is_reported_not_raised(self):
        events = []
        plan = build_plan(cfg(), hw())
        with mock.patch("time.sleep"), mock.patch.object(
                R.Runner, "_write", side_effect=R.InstallError("boom")):
            R.Runner(plan, events.append, dry_run=True).run()
        self.assertEqual(events[-1]["type"], "error")


@unittest.skipUnless(shutil.which("pacman"), "pacman not available")
class PackageNameTests(unittest.TestCase):
    def test_all_package_names_exist_in_repos(self):
        every = set(P.BASE_PACKAGES + P.DESKTOP_PACKAGES + P.FALLBACK_VULKAN
                    + P.FALLBACK_32BIT_VULKAN + ("grub", "efibootmgr", "intel-ucode", "amd-ucode"))
        for pr in P.PRESETS.values():
            every |= set(pr.packages)
        for base, lib32 in P.GPU_PACKAGES.values():
            every |= set(base) | set(lib32)
        res = subprocess.run(["pacman", "-Si", *sorted(every)], capture_output=True, text=True)
        missing = [l for l in res.stderr.splitlines() if "not found" in l]
        self.assertEqual(missing, [], "\n".join(missing))


if __name__ == "__main__":
    unittest.main()
