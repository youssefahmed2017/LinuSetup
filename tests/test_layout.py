import unittest

from linusetup.installer import layout as L
from linusetup.installer.disks import MiB, GiB
from tests.helpers import cfg, hw, disks, disk, LUKS


def guided(**over):
    return L.guided(cfg(**over), hw(**over.pop("_hw", {})) if "_hw" in over else hw(), disks())


class Wipe(unittest.TestCase):
    def test_uefi_default(self):
        lay = L.guided(cfg(), hw(), disks())
        self.assertEqual(lay.wipe, ["/dev/sda"])
        self.assertEqual([(c.number, c.typecode) for c in lay.create], [(1, "ef00"), (2, "8304")])
        self.assertEqual(lay.create[0].start, MiB)
        self.assertEqual(lay.create[0].size, GiB)
        self.assertEqual(lay.create[1].start, lay.create[0].end)
        self.assertEqual(lay.create[1].end, disk("/dev/sda").usable_end)
        self.assertEqual(lay.esp.mount, "/boot")
        self.assertTrue(lay.esp_fresh)
        self.assertEqual(L.resolve_bootloader(cfg(), hw(), lay), "systemd-boot")
        self.assertFalse(lay.dual_boot)

    def test_bios_gets_bios_grub_and_grub(self):
        lay = L.guided(cfg(), hw(uefi=False), disks())
        self.assertEqual([c.typecode for c in lay.create], ["ef02", "8304"])
        self.assertEqual(lay.create[0].size, MiB)
        self.assertEqual(lay.bios_grub_disk, "/dev/sda")
        self.assertIsNone(lay.esp)
        self.assertEqual(L.resolve_bootloader(cfg(), hw(uefi=False), lay), "grub")
        with self.assertRaises(L.LayoutError):
            L.resolve_bootloader(cfg(bootloader__type="systemd-boot"), hw(uefi=False), lay)

    def test_encrypted_uefi(self):
        c = cfg(disk__encryption={"enabled": True, "passphrase": LUKS})
        lay = L.guided(c, hw(), disks())
        root = lay.root
        self.assertTrue(root.encrypt)
        self.assertEqual(root.mapper, "cryptroot")
        self.assertEqual(root.device, "/dev/mapper/cryptroot")
        self.assertEqual(lay.create[-1].typecode, "8309")
        self.assertFalse(lay.esp.encrypt)
        self.assertEqual(lay.by_mount("/boot"), lay.esp)

    def test_encrypted_bios_has_plain_boot(self):
        c = cfg(disk__encryption={"enabled": True, "passphrase": LUKS})
        lay = L.guided(c, hw(uefi=False), disks())
        self.assertEqual([c.typecode for c in lay.create], ["ef02", "8300", "8309"])
        self.assertEqual(lay.by_mount("/boot").fs, "ext4")
        self.assertFalse(lay.by_mount("/boot").encrypt)

    def test_separate_home(self):
        lay = L.guided(cfg(disk__home={"separate": True, "root_gb": 50}), hw(), disks())
        self.assertEqual(lay.root.node, "/dev/sda2")
        self.assertEqual(lay.create[1].size, 50 * GiB)
        self.assertEqual(lay.by_mount("/home").node, "/dev/sda3")
        with self.assertRaises(L.LayoutError):
            L.guided(cfg(disk__home={"separate": True, "root_gb": 8}), hw(), disks())
        with self.assertRaises(L.LayoutError):
            L.guided(cfg(disk__home={"separate": True, "root_gb": 5000}), hw(), disks())

    def test_swap_partition(self):
        lay = L.guided(cfg(swap={"mode": "partition", "size_gb": 8}), hw(), disks())
        sw = lay.by_mount("[SWAP]")
        self.assertEqual(sw.fs, "swap")
        self.assertEqual(next(c for c in lay.create if c.node == sw.node).size, 8 * GiB)
        with self.assertRaises(L.LayoutError):
            L.guided(cfg(swap={"mode": "partition", "size_gb": 8},
                         disk__encryption={"enabled": True, "passphrase": LUKS}), hw(), disks())

    def test_btrfs_subvolumes(self):
        lay = L.guided(cfg(disk__fs="btrfs", disk__btrfs={"subvolumes": True, "compress": "zstd",
                                                           "snapshots": True},
                           swap={"mode": "swapfile", "size_gb": 4}), hw(), disks())
        names = [n for n, _ in lay.root.subvols]
        self.assertEqual(names, ["@", "@home", "@log", "@pkg", "@snapshots", "@swap"])
        self.assertIn("compress=zstd", lay.root.options)

    def test_unusable_and_missing_disks(self):
        with self.assertRaises(L.LayoutError):
            L.guided(cfg(disk__device="/dev/sdc"), hw(), disks())
        with self.assertRaises(L.LayoutError):
            L.guided(cfg(disk__device="/dev/nope"), hw(), disks())


class AlongsideWindows(unittest.TestCase):
    def test_free_space_reuses_esp(self):
        lay = L.guided(cfg(disk__device="/dev/nvme0n1", disk__scope="free"), hw(), disks())
        self.assertEqual(lay.wipe, [])
        self.assertEqual(lay.delete, [])
        self.assertTrue(lay.dual_boot)
        self.assertEqual(lay.esp.node, "/dev/nvme0n1p1")
        self.assertEqual(lay.esp.mount, "/efi")
        self.assertFalse(lay.esp.format)
        self.assertEqual([c.number for c in lay.create], [5])
        rec = disk("/dev/nvme0n1").part(4)
        self.assertEqual(lay.create[0].start, -(-rec.end // MiB) * MiB)
        self.assertEqual(L.resolve_bootloader(cfg(), hw(), lay), "grub")
        with self.assertRaises(L.LayoutError):
            L.resolve_bootloader(cfg(bootloader__type="systemd-boot"), hw(), lay)

    def test_free_space_encrypted_adds_boot(self):
        lay = L.guided(cfg(disk__device="/dev/nvme0n1", disk__scope="free",
                           disk__encryption={"enabled": True, "passphrase": LUKS}), hw(), disks())
        self.assertEqual([(c.number, c.typecode) for c in lay.create], [(5, "8300"), (6, "8309")])
        self.assertEqual(lay.by_mount("/boot").node, "/dev/nvme0n1p5")

    def test_shrink(self):
        c = cfg(disk__device="/dev/nvme0n1", disk__scope="shrink",
                disk__shrink={"partition": "/dev/nvme0n1p3", "free_gb": 200, "min_bytes": 180 * GiB})
        lay = L.guided(c, hw(), disks())
        s = lay.shrink[0]
        p = disk("/dev/nvme0n1").part(3)
        self.assertEqual((s.number, s.start, s.uuid, s.type_guid), (3, p.start, p.uuid, p.type_guid))
        self.assertEqual(s.new_size, p.size - 200 * GiB)
        self.assertLess(s.fs_size, s.new_size)
        # new partitions land in the freed gap, before the recovery partition
        rec = disk("/dev/nvme0n1").part(4)
        self.assertTrue(all(p.start + s.new_size <= n.start and n.end <= rec.start for n in lay.create))
        self.assertEqual(lay.create[-1].end, rec.start)
        self.assertTrue(any(a["kind"] == "shrink" for a in lay.summary()))

    def test_shrink_guards(self):
        base = dict(disk__device="/dev/nvme0n1", disk__scope="shrink")
        for sh, msg in [({"partition": "", "free_gb": 100}, "Choose"),
                        ({"partition": "/dev/nvme0n1p1", "free_gb": 100}, "NTFS"),
                        ({"partition": "/dev/nvme0n1p3", "free_gb": 5}, "at least"),
                        ({"partition": "/dev/nvme0n1p3", "free_gb": 400, "min_bytes": 180 * GiB}, "Windows needs")]:
            with self.assertRaisesRegex(L.LayoutError, msg):
                L.guided(cfg(**base, disk__shrink=sh), hw(), disks())

    def test_bitlocker_refused(self):
        with self.assertRaisesRegex(L.LayoutError, "BitLocker"):
            L.guided(cfg(disk__device="/dev/sdb", disk__scope="shrink",
                         disk__shrink={"partition": "/dev/sdb3", "free_gb": 50}), hw(), disks())

    def test_free_space_next_to_bitlocker_leaves_it_alone(self):
        lay = L.guided(cfg(disk__device="/dev/sdb", disk__scope="free"), hw(), disks())
        self.assertEqual((lay.delete, lay.shrink, lay.wipe), ([], [], []))
        bl = disk("/dev/sdb").part(3)
        self.assertTrue(all(c.start >= bl.end for c in lay.create))

    def test_no_free_space_and_mbr(self):
        ds = disks()
        full = next(d for d in ds if d.path == "/dev/sdb")
        full.partitions[-1].size = full.usable_end - full.partitions[-1].start
        with self.assertRaisesRegex(L.LayoutError, "no free space"):
            L.guided(cfg(disk__device="/dev/sdb", disk__scope="free"), hw(), ds)
        with self.assertRaisesRegex(L.LayoutError, "GPT"):
            L.guided(cfg(disk__device="/dev/sda", disk__scope="free"), hw(), disks())


def man(**m):
    base = {"wipe": [], "delete": [], "new": [], "existing": []}
    base.update(m)
    return cfg(disk__mode="manual", disk__manual=base)


class Manual(unittest.TestCase):
    def test_reuse_esp_and_create_in_free_space(self):
        free = disk("/dev/nvme0n1").free_regions()[0]
        c = man(existing=[{"device": "/dev/nvme0n1p1", "mount": "/efi", "format": False}],
                new=[{"disk": "/dev/nvme0n1", "start_mib": free[0] // MiB, "size_mib": 100 * 1024,
                      "fs": "btrfs", "mount": "/"}])
        lay = L.manual(c, hw(), disks())
        self.assertEqual(lay.create[0].number, 5)
        self.assertEqual(lay.root.subvols[0], ("@", "/"))
        self.assertEqual(L.resolve_bootloader(c, hw(), lay), "grub")

    def test_wipe_and_layout(self):
        c = man(wipe=["/dev/sda"], new=[
            {"disk": "/dev/sda", "start_mib": 1, "size_mib": 512, "fs": "vfat", "mount": "/boot"},
            {"disk": "/dev/sda", "start_mib": 513, "size_mib": 40960, "fs": "ext4", "mount": "/"},
            {"disk": "/dev/sda", "start_mib": 41473, "size_mib": 100000, "fs": "xfs", "mount": "/home",
             "encrypt": True},
        ])
        c["disk"]["encryption"]["passphrase"] = LUKS
        lay = L.manual(c, hw(), disks())
        self.assertEqual([x.number for x in lay.create], [1, 2, 3])
        self.assertEqual(lay.by_mount("/home").mapper, "crypthome")
        self.assertEqual(L.resolve_bootloader(c, hw(), lay), "systemd-boot")

    def test_delete_then_reuse_numbers(self):
        c = man(delete=["/dev/nvme0n1p4"], existing=[{"device": "/dev/nvme0n1p1", "mount": "/efi"}],
                new=[{"disk": "/dev/nvme0n1", "start_mib": 600000, "size_mib": 50000, "fs": "ext4", "mount": "/"}])
        lay = L.manual(c, hw(), disks())
        self.assertEqual(lay.delete, [("/dev/nvme0n1", 4, "/dev/nvme0n1p4")])
        self.assertEqual(lay.create[0].number, 4)

    def test_errors(self):
        free = disk("/dev/nvme0n1").free_regions()[0][0] // MiB
        esp = [{"device": "/dev/nvme0n1p1", "mount": "/efi"}]
        cases = [
            (man(existing=esp), "mounted at /"),
            (man(new=[{"disk": "/dev/nvme0n1", "start_mib": 1, "size_mib": 50000, "fs": "ext4", "mount": "/"}],
                 existing=esp), "free space"),
            (man(existing=esp, new=[
                {"disk": "/dev/nvme0n1", "start_mib": free, "size_mib": 50000, "fs": "ext4", "mount": "/"},
                {"disk": "/dev/nvme0n1", "start_mib": free + 1000, "size_mib": 50000, "fs": "ext4", "mount": "/home"}]),
             "overlap"),
            (man(existing=esp, new=[
                {"disk": "/dev/nvme0n1", "start_mib": free, "size_mib": 50000, "fs": "ext4", "mount": "/"},
                {"disk": "/dev/nvme0n1", "start_mib": free + 60000, "size_mib": 5000, "fs": "ext4", "mount": "/"}]),
             "Two partitions"),
            (man(new=[{"disk": "/dev/nvme0n1", "start_mib": free, "size_mib": 50000, "fs": "ext4", "mount": "/"}]),
             "EFI system partition"),
            (man(existing=[{"device": "/dev/nvme0n1p1", "mount": "/efi"}],
                 new=[{"disk": "/dev/nvme0n1", "start_mib": free, "size_mib": 50000, "fs": "ext4", "mount": "/",
                       "encrypt": True}]), "separate, unencrypted /boot"),
            (man(existing=[{"device": "/dev/sdb3", "mount": "/data"}]), "BitLocker"),
            (man(new=[{"disk": "/dev/sda", "start_mib": 1, "size_mib": 50000, "fs": "ext4", "mount": "/"}]),
             "no GPT"),
        ]
        for c, msg in cases:
            with self.assertRaisesRegex(L.LayoutError, msg):
                L.manual(c, hw(), disks())

    def test_bios_needs_bios_grub(self):
        c = man(wipe=["/dev/sda"], new=[{"disk": "/dev/sda", "start_mib": 1, "size_mib": 50000, "fs": "ext4", "mount": "/"}])
        with self.assertRaisesRegex(L.LayoutError, "BIOS boot"):
            L.manual(c, hw(uefi=False), disks())
        c = man(wipe=["/dev/sda"], new=[
            {"disk": "/dev/sda", "start_mib": 1, "size_mib": 1, "fs": "bios_grub"},
            {"disk": "/dev/sda", "start_mib": 2, "size_mib": 50000, "fs": "ext4", "mount": "/"}])
        lay = L.manual(c, hw(uefi=False), disks())
        self.assertEqual(lay.bios_grub_disk, "/dev/sda")


if __name__ == "__main__":
    unittest.main()
