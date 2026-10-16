"""Every combination of the main options builds a plan that obeys the ordering
and safety invariants, and runs to completion as a dry run."""
import itertools
import unittest
from unittest import mock

from linusetup.installer import plan as PL
from linusetup.installer import runner as R
from linusetup.installer.layout import LayoutError
from tests.helpers import cfg, hw, disks, PW, ROOTPW, LUKS

SECRETS = (PW, ROOTPW, LUKS)


def commands(plan):
    out = []
    for s in plan.steps:
        for a in s.actions + s.always:
            out.append((s.id, a))
    return out


def matrix():
    for uefi, fs, enc, scope, swap, home, boot in itertools.product(
            (True, False), ("ext4", "btrfs", "xfs", "f2fs"), (False, True), ("wipe", "free"),
            ("zram", "swapfile", "partition", "none"), (False, True), ("auto", "grub")):
        if swap == "swapfile" and fs == "f2fs":
            continue
        over = dict(disk__fs=fs, disk__scope=scope, swap={"mode": swap, "size_gb": 2},
                    disk__home={"separate": home, "root_gb": 40}, bootloader__type=boot,
                    disk__encryption={"enabled": enc, "passphrase": LUKS if enc else ""},
                    disk__btrfs={"subvolumes": True, "compress": "zstd", "snapshots": fs == "btrfs"},
                    root={"password": ROOTPW, "lock": False},
                    kernels=["linux", "linux-lts"] if home else ["linux"])
        if scope == "free":
            over["disk__device"] = "/dev/nvme0n1"
        yield uefi, over


class PlanMatrix(unittest.TestCase):
    def test_matrix(self):
        built = refused = 0
        for uefi, over in matrix():
            with self.subTest(uefi=uefi, **{k: str(v) for k, v in over.items()}):
                c = cfg(**over)
                try:
                    plan = PL.build(c, hw(uefi=uefi), disks())
                except LayoutError as e:
                    refused += 1
                    # the only refusals expected in this matrix:
                    self.assertTrue("swap partition can't be combined with encryption" in str(e)
                                    or ("GPT" in str(e)) or "systemd-boot" in str(e), str(e))
                    continue
                built += 1
                self.check_invariants(plan, c, uefi)
        self.assertGreater(built, 300)

    def check_invariants(self, plan, c, uefi):
        cmds = commands(plan)
        argv = [(sid, a.argv) for sid, a in cmds if isinstance(a, PL.Cmd)]
        idx = {}
        for n, (sid, av) in enumerate(argv):
            key = "pacstrap" if "pacstrap" in av[:4] else av[0] if av[0] != "arch-chroot" else "chroot"
            idx.setdefault(key, []).append(n)
        first = lambda k: idx[k][0]
        last = lambda k: idx[k][-1]
        # ordering
        self.assertLess(last("sgdisk"), first("pacstrap"))
        mkfs = [n for n, (_, av) in enumerate(argv)
                if av[0].startswith("mkfs") or (av[0] == "mkswap" and "--file" not in av)]
        mounts = idx["mount"]
        self.assertLess(max(mkfs, default=0), max(mounts))
        self.assertLess(max(mounts), first("pacstrap"))
        self.assertLess(first("pacstrap"), first("chroot"))
        self.assertLess(first("pacstrap"), first("genfstab"))
        self.assertEqual(argv[-1][1][:1], ["umount"] if not plan.layout.encrypted() else ["cryptsetup"])
        if plan.layout.encrypted():
            self.assertLess(first("cryptsetup"), min(mkfs))
        # secrets only via stdin or secret writes
        for sid, a in cmds:
            text = " ".join(a.argv) if isinstance(a, PL.Cmd) else (a.path if isinstance(a, PL.Write) else "")
            for s in SECRETS:
                self.assertNotIn(s, text)
            if isinstance(a, PL.Write) and isinstance(a.content, str) and not a.secret:
                for s in SECRETS:
                    self.assertNotIn(s, a.content)
        # writes go to the target, except the live mirror list
        for sid, a in cmds:
            if isinstance(a, PL.Write):
                self.assertTrue(a.path.startswith("/mnt/") or a.path == "/etc/pacman.d/mirrorlist", a.path)
        # exactly one boot loader, matching the firmware
        chroots = [av for _, av in argv if av[0] == "arch-chroot"]
        boots = [av[2] for av in chroots if av[2] in ("bootctl", "grub-install")]
        self.assertTrue(boots)
        self.assertEqual(len(set(boots)), 1)
        if not uefi:
            self.assertEqual(boots, ["grub-install"])
        # only the chosen disk is partitioned
        for _, av in argv:
            if av[0] in ("sgdisk", "wipefs", "partprobe"):
                self.assertTrue(av[-1].startswith(c["disk"]["device"]), av)
        # the initramfs knows about encryption iff / is encrypted
        hooks = next(a.content for _, a in cmds if isinstance(a, PL.Write) and "mkinitcpio.conf.d" in a.path)
        self.assertEqual("sd-encrypt" in hooks, plan.layout.root.encrypt)

    def test_dry_run_of_every_plan_completes(self):
        for n, (uefi, over) in enumerate(matrix()):
            if n % 7:       # a spread sample keeps this fast
                continue
            try:
                plan = PL.build(cfg(**over), hw(uefi=uefi), disks())
            except LayoutError:
                continue
            events = []
            with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run:
                R.Runner(plan, events.append, dry_run=True, secrets=SECRETS, speed=0).run()
            popen.assert_not_called()
            run.assert_not_called()
            self.assertEqual(events[-1]["type"], "done", events[-3:])
            prog = [e["value"] for e in events if e["type"] == "progress"]
            self.assertEqual(prog, sorted(prog))
            self.assertAlmostEqual(prog[-1], 1.0)
            dump = str(events)
            for s in SECRETS:
                self.assertNotIn(s, dump)


class Specifics(unittest.TestCase):
    def find(self, plan, pred):
        return [a for _, a in commands(plan) if pred(a)]

    def test_systemd_boot_entries_use_luks_and_subvol(self):
        c = cfg(disk__fs="btrfs", disk__encryption={"enabled": True, "passphrase": LUKS},
                kernel_params="quiet splash")
        plan = PL.build(c, hw(), disks())
        entry = next(a for _, a in commands(plan) if isinstance(a, PL.Write) and a.path.endswith("arch-linux.conf"))
        text = entry.content(R.Runner(plan, lambda e: None, dry_run=True, speed=0))
        self.assertIn("rd.luks.name=dry-run-", text)
        self.assertIn("root=/dev/mapper/cryptroot", text)
        self.assertIn("rootflags=subvol=@", text)
        self.assertIn("quiet splash", text)
        self.assertNotIn("ucode", text)       # microcode is an mkinitcpio hook now

    def test_grub_dual_boot_enables_os_prober(self):
        plan = PL.build(cfg(disk__device="/dev/nvme0n1", disk__scope="free"), hw(), disks())
        grub = next(a for _, a in commands(plan) if isinstance(a, PL.Write) and a.path.endswith("default/grub"))
        text = grub.content(R.Runner(plan, lambda e: None, dry_run=True, speed=0))
        self.assertIn("GRUB_DISABLE_OS_PROBER=false", text)
        self.assertIn("os-prober", plan.selection.packages)
        inst = [a.argv for _, a in commands(plan) if isinstance(a, PL.Cmd) and "grub-install" in a.argv]
        self.assertEqual(len(inst), 1, "never install the removable fallback over a shared Windows ESP")
        self.assertIn("--efi-directory=/efi", inst[0])

    def test_nvidia_drops_kms_and_uses_dkms_for_extra_kernels(self):
        h = hw(gpus=[("nvidia", "RTX 4070")])
        plan = PL.build(cfg(kernels=["linux", "linux-zen"]), h, disks())
        self.assertIn("nvidia-open-dkms", plan.selection.packages)
        self.assertIn("linux-zen-headers", plan.selection.packages)
        hooks = next(a.content for _, a in commands(plan) if isinstance(a, PL.Write) and "mkinitcpio.conf.d" in a.path)
        self.assertNotIn(" kms ", hooks)
        plan = PL.build(cfg(), h, disks())
        self.assertIn("nvidia-open", plan.selection.packages)

    def test_gaming_enables_multilib_everywhere(self):
        plan = PL.build(cfg(software=["steam"]), hw(), disks())
        self.assertTrue(plan.selection.multilib)
        self.assertIn("lib32-vulkan-radeon", plan.selection.packages)
        seds = [a.argv[-1] for _, a in commands(plan) if isinstance(a, PL.Cmd) and a.argv[0] == "sed"
                and "multilib" in " ".join(a.argv)]
        self.assertEqual(sorted(seds), ["/etc/pacman.conf", "/mnt/etc/pacman.conf"])

    def test_users_groups_autologin(self):
        c = cfg(software=["docker"], profiles=["xfce"])
        c["users"][0]["autologin"] = True
        plan = PL.build(c, hw(), disks())
        useradd = next(a.argv for _, a in commands(plan) if isinstance(a, PL.Cmd) and "useradd" in a.argv)
        self.assertIn("wheel,docker,autologin", useradd)
        self.assertTrue(self.find(plan, lambda a: isinstance(a, PL.Write) and "lightdm.conf.d" in a.path))
        chpw = next(a for _, a in commands(plan) if isinstance(a, PL.Cmd) and "chpasswd" in a.argv)
        self.assertEqual(chpw.stdin, f"sam:{PW}\n")

    def test_shrink_commands(self):
        c = cfg(disk__device="/dev/nvme0n1", disk__scope="shrink",
                disk__shrink={"partition": "/dev/nvme0n1p3", "free_gb": 150})
        plan = PL.build(c, hw(), disks())
        argv = [a.argv for _, a in commands(plan) if isinstance(a, PL.Cmd) and a.argv[0] == "ntfsresize"]
        self.assertEqual(argv[0][1], "--no-action", "always dry-run ntfsresize first")
        self.assertNotIn("--force", sum(argv, []))
        self.assertNotIn("-f", sum(argv, []))

    def test_aur_and_custom_cleanup_always_runs(self):
        c = cfg(aur_helper="yay", custom_commands="echo hi")
        plan = PL.build(c, hw(), disks())
        aur = next(s for s in plan.steps if s.id == "aur")
        self.assertEqual(aur.always[0].argv[:2], ["rm", "-f"])
        custom = next(s for s in plan.steps if s.id == "custom")
        self.assertTrue(custom.actions[1].optional)


class LocalMirror(unittest.TestCase):
    def test_proxy_used_for_install_and_removed_from_target(self):
        m = "http://10.0.2.2:8081"
        plan = PL.build(cfg(), hw(), disks(), local_mirror=m)
        cmds = [(s.id, a.argv) for s in plan.steps for a in s.actions if isinstance(a, PL.Cmd)]
        ins = [i for i, (_, av) in enumerate(cmds) if av[:2] == ["sed", "-i"] and av[2].startswith("1i Server = " + m)]
        strip = [i for i, (_, av) in enumerate(cmds) if av[0] == "sed" and av[-1] == "/mnt/etc/pacman.d/mirrorlist"]
        pacstrap = next(i for i, (_, av) in enumerate(cmds) if "pacstrap" in av[:4])
        self.assertEqual(len(ins), 1)
        self.assertEqual(len(strip), 1)
        self.assertLess(ins[0], pacstrap)
        self.assertGreater(strip[0], pacstrap)
        # after reflector, so the ranking doesn't push the proxy out
        reflector = next(i for i, (_, av) in enumerate(cmds) if "reflector" in av)
        self.assertGreater(ins[0], reflector)

    def test_no_proxy_by_default(self):
        plan = PL.build(cfg(), hw(), disks())
        self.assertFalse(any("10.0.2.2" in " ".join(a.argv) for s in plan.steps for a in s.actions if isinstance(a, PL.Cmd)))


class PacmanProgressTests(unittest.TestCase):
    def test_downloads_move_the_bar_and_only_installs_finish_it(self):
        t = R.PacmanProgress()
        seen = [t.feed(l) for l in [
            "Packages (4) a-1-1  b-1-1  c-1-1  d-1-1", ":: Retrieving packages...",
            " a-1-1-x86_64 downloading...", " a-1-1-x86_64.pkg.tar.zst.sig downloading...",
            " b-1-1-x86_64 downloading...", "(4/4) checking keys in keyring", "(4/4) checking package integrity",
            "(1/4) installing a", "(4/4) installing d"]]
        self.assertGreater(seen[2], 0)                       # first download moves the bar
        self.assertEqual(seen[3], seen[2])                   # .sig files don't count
        self.assertLess(seen[6], R.PacmanProgress.DOWNLOAD_SHARE + 1e-9)   # "(4/4) checking" is not "done"
        self.assertEqual(seen, sorted(seen))
        self.assertAlmostEqual(seen[-1], 1.0)

    def test_pacstrap_uses_it(self):
        plan = PL.build(cfg(), hw(), disks())
        pacstrap = next(a for s in plan.steps for a in s.actions if isinstance(a, PL.Cmd) and "pacstrap" in a.argv[:4])
        self.assertEqual(pacstrap.progress, "pacman")
        self.assertEqual(pacstrap.argv[:3], ["stdbuf", "-oL", "-eL"])


class RunnerBehaviour(unittest.TestCase):
    def test_optional_failure_warns_and_always_runs(self):
        plan = PL.build(cfg(aur_helper="yay"), hw(), disks())
        calls = []

        def fake_cmd(self, c, on_frac):
            calls.append(c.argv)
            if "makepkg" in " ".join(c.argv):
                raise R.InstallError("AUR down")
        events = []
        with mock.patch.object(R.Runner, "_cmd", fake_cmd):
            R.Runner(plan, events.append, dry_run=True, speed=0).run()
        self.assertEqual(events[-1]["type"], "done")
        self.assertTrue(any("AUR down" in w for w in events[-1]["warnings"]))
        self.assertIn(["rm", "-f", "/mnt/etc/sudoers.d/99-linusetup-aur"], calls)

    def test_required_failure_stops_and_reports(self):
        plan = PL.build(cfg(), hw(), disks())

        def fake_cmd(self, c, on_frac):
            if "pacstrap" in c.argv[:4]:
                raise R.InstallError("mirror exploded")
        events = []
        with mock.patch.object(R.Runner, "_cmd", fake_cmd):
            R.Runner(plan, events.append, dry_run=True, speed=0).run()
        self.assertEqual(events[-1]["type"], "error")
        self.assertIn("mirror exploded", events[-1]["message"])
        self.assertEqual(events[-1]["step"], "Installing Arch Linux")
        self.assertFalse(any(e["type"] == "step" and e["id"] == "configure" for e in events))

    def test_real_mode_is_blocked_off_the_iso(self):
        with mock.patch.dict("os.environ", {"LINUSETUP_REAL": "1"}):
            with mock.patch.object(R, "LIVE_MARKER") as m:
                m.exists.return_value = False
                self.assertFalse(R.real_mode_allowed())

    def test_scrub(self):
        r = R.Runner(None, lambda e: None, secrets=[PW])
        self.assertEqual(r.scrub(f"x {PW} y"), "x •••••• y")


if __name__ == "__main__":
    unittest.main()
