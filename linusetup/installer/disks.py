"""Disk and partition-table model. Read-only.

All positions are bytes. New partitions are placed on 1 MiB boundaries.
"""
import hashlib
import json
import re
import subprocess
from dataclasses import dataclass, field, asdict

MiB = 1024 * 1024
GiB = 1024 * MiB

# GPT partition type GUIDs (upper case, as lsblk reports them lower case).
ESP = "C12A7328-F81F-11D2-BA4B-00A0C93EC93B"
BIOS_BOOT = "21686148-6449-6E6F-744E-656564454649"
MSR = "E3C9E316-0B5C-4DB8-817D-F92DF00215AE"
MS_DATA = "EBD0A0A2-B9E5-4433-87C0-68B6B72699C7"
WIN_RECOVERY = "DE94BBA4-06D1-4D40-A16A-BFD50179D6AC"
LINUX_FS = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"
LINUX_SWAP = "0657FD6D-A4AB-43C4-84E5-0933C84B4F4F"
LINUX_ROOT = "4F68BCE3-E8CD-4DB1-96E7-FBCAF984B709"
LINUX_HOME = "933AC7E1-2EB4-4F13-B844-0E14E2AEF915"
LINUX_LUKS = "CA7D7CCB-63ED-4C53-861C-1742536059CC"

# sgdisk short type codes for partitions we create
TYPECODE = {"esp": "ef00", "bios": "ef02", "linux": "8300", "swap": "8200",
            "root": "8304", "home": "8302", "luks": "8309"}

KIND_BY_GUID = {ESP: "esp", BIOS_BOOT: "bios", MSR: "msr", MS_DATA: "windows",
                WIN_RECOVERY: "recovery", LINUX_FS: "linux", LINUX_SWAP: "swap",
                LINUX_ROOT: "linux", LINUX_HOME: "linux", LINUX_LUKS: "luks"}


@dataclass
class Partition:
    number: int
    node: str
    start: int
    size: int
    type_guid: str = ""
    uuid: str = ""
    name: str = ""
    fstype: str = ""
    label: str = ""
    mounted: bool = False

    @property
    def end(self):
        return self.start + self.size

    @property
    def kind(self):
        if self.fstype == "BitLocker":
            return "bitlocker"
        k = KIND_BY_GUID.get(self.type_guid.upper(), "other")
        if k == "windows" and self.fstype not in ("ntfs", ""):
            return "data"
        return k

    def to_dict(self):
        d = asdict(self)
        d.update(kind=self.kind, end=self.end)
        return d


@dataclass
class Disk:
    path: str
    name: str
    model: str
    size: int
    transport: str = ""
    rotational: bool = False
    removable: bool = False
    log_sec: int = 512
    pttype: str = ""            # gpt | dos | "" (no table)
    partitions: list = field(default_factory=list)
    usable: bool = True
    reason: str = ""

    def part(self, number_or_node):
        for p in self.partitions:
            if p.number == number_or_node or p.node == number_or_node:
                return p
        return None

    @property
    def usable_start(self):
        return MiB

    @property
    def usable_end(self):
        # Leave 1 MiB at the end: room for the backup GPT on any sector size.
        return (self.size - MiB) // MiB * MiB

    def free_regions(self, partitions=None, min_size=16 * MiB):
        """Gaps between partitions, shrunk inward to whole MiB."""
        parts = sorted(self.partitions if partitions is None else partitions,
                       key=lambda p: p.start)
        regions, cursor = [], self.usable_start
        for p in parts + [None]:
            limit = self.usable_end if p is None else p.start
            start = -(-cursor // MiB) * MiB
            end = limit // MiB * MiB
            if end - start >= min_size:
                regions.append((start, end))
            if p is not None:
                cursor = max(cursor, p.end)
        return regions

    def has_windows(self):
        return any(p.kind in ("windows", "bitlocker") for p in self.partitions)

    def fingerprint(self):
        key = [self.pttype, self.size] + sorted(
            (p.number, p.start, p.size, p.type_guid.upper(), p.uuid.lower())
            for p in self.partitions)
        return hashlib.sha1(json.dumps(key).encode()).hexdigest()[:16]

    def to_dict(self):
        return dict(
            path=self.path, name=self.name, model=self.model, size=self.size,
            transport=self.transport, rotational=self.rotational, removable=self.removable,
            log_sec=self.log_sec, pttype=self.pttype, usable=self.usable, reason=self.reason,
            partitions=[p.to_dict() for p in sorted(self.partitions, key=lambda p: p.start)],
            free=[dict(start=s, end=e, size=e - s) for s, e in self.free_regions()],
            fingerprint=self.fingerprint(), has_windows=self.has_windows())


def part_node(disk_path, number):
    """/dev/sda + 2 -> /dev/sda2 ; /dev/nvme0n1 + 2 -> /dev/nvme0n1p2"""
    return f"{disk_path}p{number}" if disk_path[-1].isdigit() else f"{disk_path}{number}"


LSBLK_COLS = ("NAME,PATH,TYPE,SIZE,START,PARTN,PARTTYPE,PARTUUID,PARTLABEL,FSTYPE,LABEL,"
              "MOUNTPOINTS,MODEL,TRAN,RM,ROTA,PTTYPE,LOG-SEC")


def _mounted(node):
    mps = node.get("mountpoints") or [node.get("mountpoint")]
    if any(mps):
        return True
    return any(_mounted(c) for c in node.get("children") or [])


def _all_mounts(node):
    out = [m for m in (node.get("mountpoints") or [node.get("mountpoint")]) if m]
    for c in node.get("children") or []:
        out += _all_mounts(c)
    return out


def parse_lsblk(data, min_size=20 * GiB):
    """lsblk -J -b output -> [Disk]. The live medium is left out entirely."""
    disks = []
    for n in data.get("blockdevices", []):
        if n.get("type") != "disk" or re.match(r"(loop|sr|zram|ram|fd)", n.get("name", "")):
            continue
        mounts = _all_mounts(n)
        if any(m.startswith("/run/archiso") for m in mounts):
            continue
        d = Disk(path=n["path"], name=n["name"], model=(n.get("model") or "Disk").strip(),
                 size=int(n.get("size") or 0), transport=n.get("tran") or "",
                 rotational=bool(n.get("rota")), removable=bool(n.get("rm")),
                 log_sec=int(n.get("log-sec") or 512), pttype=n.get("pttype") or "")
        for c in n.get("children") or []:
            if c.get("type") != "part":
                continue
            num = c.get("partn")
            if num is None:
                m = re.search(r"(\d+)$", c["name"])
                num = int(m.group(1)) if m else 0
            d.partitions.append(Partition(
                number=int(num), node=c["path"], start=int(c.get("start") or 0) * 512,
                size=int(c.get("size") or 0), type_guid=(c.get("parttype") or "").upper(),
                uuid=c.get("partuuid") or "", name=c.get("partlabel") or "",
                fstype=c.get("fstype") or "", label=c.get("label") or "", mounted=_mounted(c)))
        if mounts:
            d.usable, d.reason = False, "In use (something on it is mounted)"
        elif d.size < min_size:
            d.usable, d.reason = False, "Too small (needs at least 20 GB)"
        disks.append(d)
    return disks


def scan():
    try:
        out = subprocess.run(["lsblk", "-J", "-b", "-o", LSBLK_COLS],
                             capture_output=True, text=True, timeout=10)
        return parse_lsblk(json.loads(out.stdout)) if out.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return []
