"""Apply the generated partition-table commands to sparse image files with the
real sgdisk and read the result back with sfdisk. No root needed: these are
plain files. This checks the most dangerous part of an install for real:
partitions we keep must come out byte-identical."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from linusetup.installer import disks as D
from linusetup.installer import plan as PL
from linusetup.installer.disks import MiB, GiB
from tests.helpers import cfg, hw, LUKS

HAVE_TOOLS = all(shutil.which(t) for t in ("sgdisk", "sfdisk", "truncate"))
FSTYPES = {D.ESP: "vfat", D.MS_DATA: "ntfs", D.WIN_RECOVERY: "ntfs"}


def sh(*argv):
    subprocess.run(argv, check=True, capture_output=True)


def read_disk(path):
    size = os.path.getsize(path)
    r = subprocess.run(["sfdisk", "-J", path], capture_output=True, text=True)
    d = D.Disk(path=path, name=os.path.basename(path), model="image", size=size)
    if r.returncode != 0:
        return d
    t = json.loads(r.stdout)["partitiontable"]
    d.pttype, d.log_sec = t["label"], t.get("sectorsize", 512)
    for p in t.get("partitions", []):
        num = int(p["node"][len(path):].lstrip("p"))
        typ = p["type"].upper()
        d.partitions.append(D.Partition(
            number=num, node=D.part_node(path, num), start=p["start"] * d.log_sec,
            size=p["size"] * d.log_sec, type_guid=typ, uuid=p.get("uuid", "").upper(),
            name=p.get("name", ""), fstype=FSTYPES.get(typ, "")))
    return d


def snapshot(d):
    return {p.number: (p.start, p.size, p.type_guid, p.uuid, p.name) for p in d.partitions}


@unittest.skipUnless(HAVE_TOOLS, "sgdisk/sfdisk not installed")
class ImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="linusetup-img-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def blank(self, name="disk.img", size="500G"):
        path = os.path.join(self.tmp, name)
        sh("truncate", "-s", size, path)
        return path

    def windows(self):
        path = self.blank()
        sh("sgdisk", "-n1:2048:+100M", "-t1:ef00", "-c1:EFI system partition",
           "-n2:0:+16M", "-t2:0c01", "-c2:Microsoft reserved partition",
           "-n3:0:+300G", "-t3:0700", "-c3:Basic data partition",
           "-n4:0:+1G", "-t4:2700", "-c4:Recovery", path)
        return path

    def apply(self, c, h=None):
        h = h or hw()
        disks = [read_disk(p) for p in sorted(set([c["disk"]["device"]] + c["disk"]["manual"]["wipe"]
                                                  + [n["disk"] for n in c["disk"]["manual"]["new"]]))
                 if p]
        plan = PL.build(c, h, disks)
        ran = 0
        for a in next(s for s in plan.steps if s.id == "disks").actions:
            if isinstance(a, PL.Cmd) and a.argv[0] == "sgdisk":
                subprocess.run(a.argv, check=True, capture_output=True)
                ran += 1
        self.assertGreater(ran, 0)
        return plan, read_disk(disks[0].path)

    # ----------------------------------------------------------------
    def test_wipe_uefi(self):
        path = self.blank()
        plan, after = self.apply(cfg(disk__device=path))
        p = {x.number: x for x in after.partitions}
        self.assertEqual(sorted(p), [1, 2])
        self.assertEqual((p[1].start, p[1].size, p[1].type_guid), (MiB, GiB, D.ESP))
        self.assertEqual(p[2].start, MiB + GiB)
        self.assertEqual(p[2].type_guid, D.LINUX_ROOT)
        self.assertEqual(p[2].end, plan.layout.create[1].end)

    def test_wipe_replaces_old_table(self):
        path = self.windows()
        plan, after = self.apply(cfg(disk__device=path))
        self.assertEqual(sorted(x.number for x in after.partitions), [1, 2])
        self.assertNotIn(D.MS_DATA, [x.type_guid for x in after.partitions])

    def test_wipe_bios(self):
        path = self.blank()
        plan, after = self.apply(cfg(disk__device=path), hw(uefi=False))
        p = {x.number: x for x in after.partitions}
        self.assertEqual((p[1].start, p[1].size, p[1].type_guid), (MiB, MiB, D.BIOS_BOOT))
        self.assertEqual(p[2].type_guid, D.LINUX_ROOT)

    def test_free_space_keeps_windows_identical(self):
        path = self.windows()
        before = snapshot(read_disk(path))
        plan, after = self.apply(cfg(disk__device=path, disk__scope="free"))
        now = snapshot(after)
        for n in (1, 2, 3, 4):
            self.assertEqual(now[n], before[n], f"partition {n} changed")
        self.assertEqual(sorted(now), [1, 2, 3, 4, 5])
        self.assertEqual(now[5][0], -(-(before[4][0] + before[4][1]) // MiB) * MiB)
        self.assertEqual(now[5][2], D.LINUX_ROOT)

    def test_free_space_encrypted(self):
        path = self.windows()
        before = snapshot(read_disk(path))
        plan, after = self.apply(cfg(disk__device=path, disk__scope="free",
                                     disk__encryption={"enabled": True, "passphrase": LUKS}))
        now = snapshot(after)
        self.assertEqual({n: now[n] for n in (1, 2, 3, 4)}, before)
        self.assertEqual((now[5][2], now[6][2]), (D.LINUX_FS, D.LINUX_LUKS))
        self.assertEqual(now[5][1], GiB)

    def test_shrink_windows(self):
        path = self.windows()
        before = snapshot(read_disk(path))
        plan, after = self.apply(cfg(disk__device=path, disk__scope="shrink",
                                     disk__shrink={"partition": D.part_node(path, 3), "free_gb": 100}))
        now = snapshot(after)
        s3, n3 = before[3], now[3]
        self.assertEqual((n3[0], n3[2], n3[3], n3[4]), (s3[0], s3[2], s3[3], s3[4]),
                         "shrunk partition must keep start, type, GUID and name")
        self.assertEqual(n3[1], s3[1] - 100 * GiB)
        self.assertEqual(now[4], before[4])
        self.assertEqual(now[1], before[1])
        self.assertEqual(now[2], before[2])
        new = [now[n] for n in now if n not in before]
        self.assertTrue(new)
        for start, size, *_ in new:
            self.assertGreaterEqual(start, n3[0] + n3[1])
            self.assertLessEqual(start + size, s3[0] + s3[1])

    def test_manual_delete_and_create(self):
        path = self.windows()
        before = snapshot(read_disk(path))
        free_start = (before[4][0] + before[4][1]) // MiB + 1
        c = cfg(disk__device="", disk__mode="manual", disk__manual={
            "wipe": [], "delete": [D.part_node(path, 4)],
            "existing": [{"device": D.part_node(path, 1), "mount": "/efi"}],
            "new": [{"disk": path, "start_mib": free_start, "size_mib": 40960, "fs": "ext4", "mount": "/"},
                    {"disk": path, "start_mib": free_start + 40960, "size_mib": 4096, "fs": "swap"}]})
        c["swap"]["mode"] = "none"
        plan, after = self.apply(c)
        now = snapshot(after)
        for n in (1, 2, 3):
            self.assertEqual(now[n], before[n])
        self.assertEqual(now[4][0], free_start * MiB)       # number 4 reused by the first new partition
        self.assertEqual(now[4][1], 40960 * MiB)
        self.assertEqual(now[5][2], D.LINUX_SWAP)


if __name__ == "__main__":
    unittest.main()
