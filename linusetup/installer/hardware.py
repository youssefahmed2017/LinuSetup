"""Read-only hardware and disk detection. Never modifies anything."""
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field, asdict
from pathlib import Path

LIVE_MARKER = Path("/run/archiso")


@dataclass
class Hardware:
    uefi: bool = True
    cpu_vendor: str = "unknown"          # intel | amd | unknown
    gpus: list = field(default_factory=list)   # subset of nvidia | amd | intel
    virt: str = ""                       # "" on bare metal, else e.g. "kvm"
    ram_gb: float = 0.0


def _run(argv, timeout=8):
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def detect_hardware() -> Hardware:
    hw = Hardware()
    hw.uefi = Path("/sys/firmware/efi").exists()
    try:
        cpuinfo = Path("/proc/cpuinfo").read_text()
        if "GenuineIntel" in cpuinfo:
            hw.cpu_vendor = "intel"
        elif "AuthenticAMD" in cpuinfo:
            hw.cpu_vendor = "amd"
    except OSError:
        pass
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                hw.ram_gb = round(int(line.split()[1]) / 1048576, 1)
                break
    except (OSError, ValueError):
        pass
    virt = _run(["systemd-detect-virt"]).strip()
    hw.virt = "" if virt in ("", "none") else virt
    for line in _run(["lspci", "-nn"]).splitlines():
        if not re.search(r"VGA|3D controller|Display controller", line):
            continue
        low = line.lower()
        for vendor, needle in (("nvidia", "nvidia"), ("amd", "amd"), ("amd", "ati "),
                               ("intel", "intel")):
            if needle in low and vendor not in hw.gpus:
                hw.gpus.append(vendor)
    return hw


def is_live() -> bool:
    return LIVE_MARKER.exists()


def is_online(host="archlinux.org", port=443, timeout=3) -> bool:
    import socket
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


@dataclass
class Disk:
    path: str
    name: str
    size_bytes: int
    model: str
    transport: str
    rotational: bool
    removable: bool
    contents: list          # fstypes of existing partitions, e.g. ["ntfs", "ext4"]
    usable: bool = True
    reason: str = ""        # why it is not usable

    def to_dict(self):
        d = asdict(self)
        d["size_gb"] = round(self.size_bytes / 1e9)
        return d


def _mountpoints(node):
    mps = node.get("mountpoints") or [node.get("mountpoint")]
    found = [m for m in mps if m]
    for child in node.get("children") or []:
        found.extend(_mountpoints(child))
    return found


def _fstypes(node):
    types = []
    for child in node.get("children") or []:
        if child.get("fstype"):
            types.append(child["fstype"])
        types.extend(_fstypes(child))
    return types


def list_disks() -> list:
    """Whole disks only. Loop, optical, zram and the live medium are excluded;
    a disk with any mounted partition is returned but marked unusable."""
    if not shutil.which("lsblk"):
        return []
    raw = _run(["lsblk", "-J", "-b", "-o",
                "NAME,PATH,SIZE,MODEL,TYPE,RM,TRAN,ROTA,FSTYPE,MOUNTPOINTS"])
    if not raw:
        return []
    try:
        nodes = json.loads(raw).get("blockdevices", [])
    except json.JSONDecodeError:
        return []
    disks = []
    for n in nodes:
        if n.get("type") != "disk" or re.match(r"(loop|sr|zram|ram|fd)", n.get("name", "")):
            continue
        mounts = _mountpoints(n)
        d = Disk(
            path=n["path"], name=n["name"], size_bytes=int(n.get("size") or 0),
            model=(n.get("model") or "Unknown disk").strip(),
            transport=n.get("tran") or "", rotational=bool(n.get("rota")),
            removable=bool(n.get("rm")), contents=sorted(set(_fstypes(n))),
        )
        if any(m.startswith("/run/archiso") for m in mounts):
            continue  # the installer medium itself: never offer it
        if mounts:
            d.usable, d.reason = False, "In use (mounted)"
        elif d.size_bytes < 20 * 10**9:
            d.usable, d.reason = False, "Too small (needs 20 GB)"
        disks.append(d)
    return disks
