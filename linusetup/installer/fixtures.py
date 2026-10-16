"""A pretend machine for UI development, screenshots and tests. Deterministic.

Disks:
  nvme0n1  1 TB  Windows 11 (ESP, MSR, C:, Recovery) with ~400 GB free at the end
  sda      1 TB  brand new, no partition table
  sdb    256 GB  BitLocker-encrypted Windows (shrinking must be refused)
  sdc     16 GB  USB stick (too small)
"""
import time

from . import disks as D
from .system import Hardware

GB = 10 ** 9
MiB, GiB = D.MiB, D.GiB


def _p(disk, n, start_mib, size_mib, guid, fstype="", label="", name="", uuid=None):
    return D.Partition(number=n, node=D.part_node(disk, n), start=start_mib * MiB,
                       size=size_mib * MiB, type_guid=guid, fstype=fstype, label=label,
                       name=name, uuid=uuid or f"00000000-0000-4000-8000-{n:04d}{sum(map(ord, disk)):08d}")


def fixture_disks():
    nv = "/dev/nvme0n1"
    win = D.Disk(path=nv, name="nvme0n1", model="Samsung SSD 990 PRO 1TB", size=1000 * GB,
                 transport="nvme", log_sec=512, pttype="gpt", partitions=[
                     _p(nv, 1, 1, 100, D.ESP, "vfat", "", "EFI system partition"),
                     _p(nv, 2, 101, 16, D.MSR, "", "", "Microsoft reserved partition"),
                     _p(nv, 3, 117, 512000, D.MS_DATA, "ntfs", "Windows", "Basic data partition"),
                     _p(nv, 4, 512117, 1024, D.WIN_RECOVERY, "ntfs", "", "Recovery"),
                 ])
    new = D.Disk(path="/dev/sda", name="sda", model="WD Blue SN580 1TB", size=1000 * GB,
                 transport="sata", rotational=False)
    sb = "/dev/sdb"
    bl = D.Disk(path=sb, name="sdb", model="Kingston A400 256GB", size=256 * GB, transport="sata",
                pttype="gpt", partitions=[
                    _p(sb, 1, 1, 260, D.ESP, "vfat"),
                    _p(sb, 2, 261, 16, D.MSR),
                    _p(sb, 3, 277, 200000, D.MS_DATA, "BitLocker", "", "Basic data partition"),
                ])
    usb = D.Disk(path="/dev/sdc", name="sdc", model="SanDisk Ultra", size=16 * GB,
                 transport="usb", removable=True, pttype="dos", usable=False,
                 reason="Too small (needs at least 20 GB)",
                 partitions=[_p("/dev/sdc", 1, 1, 15000, "", "exfat", "SANDISK")])
    return [win, new, bl, usb]


class FixtureSystem:
    fixture = True

    def __init__(self, online=True, uefi=True, virt=""):
        self._online, self._uefi, self._virt = online, uefi, virt

    def is_live(self):
        return False

    def hardware(self):
        return Hardware(uefi=self._uefi, cpu_vendor="amd", cpu_model="AMD Ryzen 7 7840U",
                        gpus=[("amd", "Advanced Micro Devices, Inc. [AMD/ATI] Phoenix1 [Radeon 780M]")],
                        virt=self._virt, ram_gb=31.2, wifi=["wlan0"], cpu_cores=16)

    def disks(self):
        return fixture_disks()

    def online(self, **_):
        return self._online

    def ntfs_info(self, node):
        if node.endswith("p3"):
            return {"ok": True, "min_bytes": 180 * GiB}
        if node.endswith("p4"):
            return {"ok": True, "min_bytes": 600 * MiB}
        return {"ok": False, "error": "This is not an NTFS volume ntfsresize can resize."}

    def wifi_scan(self, iface):
        time.sleep(0.6)
        return [dict(ssid="Home-5G", security="psk", signal=4, connected=False),
                dict(ssid="Cafe Guest", security="open", signal=2, connected=False),
                dict(ssid="Neighbours", security="psk", signal=1, connected=False)]

    def wifi_connect(self, iface, ssid, psk):
        time.sleep(1.0)
        if ssid == "Home-5G" and psk != "password123":
            return {"ok": False, "error": "Wrong password (fixture password is password123)."}
        self._online = True
        return {"ok": True}

    def search_packages(self, query, limit=40):
        pool = [("extra", "htop", "Interactive process viewer"),
                ("extra", "neofetch", "System info"), ("extra", "kitty", "GPU terminal"),
                ("extra", "gparted", "Partition editor"), ("extra", "kdeconnect", "Phone integration"),
                ("extra", "steam", "Valve's game platform"), ("extra", "spotify-launcher", "Spotify")]
        q = query.lower()
        return [dict(repo=r, name=n, version="1.0-1", desc=d) for r, n, d in pool if q in n][:limit]
