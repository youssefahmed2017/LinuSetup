"""Everything the installer reads from the machine, behind one interface so the
UI can be developed against fixtures. Nothing in here changes the disks."""
import os
import re
import shutil
import socket
import subprocess
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path

from . import disks as D

LIVE_MARKER = Path("/run/archiso")
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


@dataclass
class Hardware:
    uefi: bool = True
    cpu_vendor: str = "unknown"            # intel | amd | unknown
    cpu_model: str = ""
    gpus: list = field(default_factory=list)   # [(vendor, description)]
    virt: str = ""                         # "" on bare metal, else systemd-detect-virt id
    ram_gb: float = 0.0
    wifi: list = field(default_factory=list)   # wireless interface names
    cpu_cores: int = 0
    render_node: bool = True               # /dev/dri/renderD* exists (GPU acceleration possible)

    def gpu_vendors(self):
        return sorted({v for v, _ in self.gpus})

    def to_dict(self):
        d = asdict(self)
        d["gpus"] = [dict(vendor=v, name=n) for v, n in self.gpus]
        return d


def gpu_vendor(vendor_field):
    """lspci vendor name -> nvidia | amd | intel | other. Whole words only:
    "Intel Corporation" contains "ati", which must not mean AMD/ATI."""
    v = vendor_field.lower()
    if re.search(r"\bnvidia\b", v):
        return "nvidia"
    if re.search(r"\b(advanced micro devices|amd|ati)\b", v):
        return "amd"
    if re.search(r"\bintel\b", v):
        return "intel"
    return "other"


def _run(argv, timeout=10, **kw):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, **kw)
        return r.returncode, r.stdout, r.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, "", str(e)


class RealSystem:
    fixture = False

    def is_live(self):
        return LIVE_MARKER.exists()

    def hardware(self):
        hw = Hardware(uefi=Path("/sys/firmware/efi").exists(), cpu_cores=os.cpu_count() or 0,
                      render_node=any(Path("/dev/dri").glob("renderD*")))
        try:
            info = Path("/proc/cpuinfo").read_text()
            hw.cpu_vendor = ("intel" if "GenuineIntel" in info
                             else "amd" if "AuthenticAMD" in info else "unknown")
            m = re.search(r"^model name\s*:\s*(.+)$", info, re.M)
            hw.cpu_model = m.group(1).strip() if m else ""
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    hw.ram_gb = round(int(line.split()[1]) / 1048576, 1)
        except (OSError, ValueError):
            pass
        rc, out, _ = _run(["systemd-detect-virt"])
        hw.virt = "" if out.strip() in ("", "none") else out.strip()
        rc, out, _ = _run(["lspci", "-mm"])
        for line in out.splitlines():
            fields = re.findall(r'"([^"]*)"', line)
            if len(fields) >= 3 and re.search(r"VGA|3D|Display", fields[0]):
                hw.gpus.append((gpu_vendor(fields[1]), f"{fields[1]} {fields[2]}"))
        net = Path("/sys/class/net")
        if net.exists():
            hw.wifi = sorted(p.name for p in net.iterdir() if (p / "wireless").exists())
        return hw

    def disks(self):
        return D.scan()

    def online(self, host="archlinux.org", port=443, timeout=3):
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    def ntfs_info(self, node):
        """Smallest size the NTFS volume can be shrunk to, via ntfsresize --info.
        Fails (with ntfsresize's reason) on hibernated / Fast Startup volumes."""
        if not shutil.which("ntfsresize"):
            return {"ok": False, "error": "ntfsresize is not available."}
        rc, out, err = _run(["ntfsresize", "--info", "--no-progress-bar", node], timeout=120)
        m = re.search(r"You might resize at (\d+) bytes", out)
        if rc == 0 and m:
            return {"ok": True, "min_bytes": int(m.group(1))}
        text = (err or out).strip().splitlines()
        return {"ok": False, "error": text[-1] if text else "ntfsresize failed."}

    # --- Wi-Fi through iwd (what the Arch ISO ships) ---------------------
    def wifi_scan(self, iface):
        _run(["iwctl", "station", iface, "scan"], timeout=15)
        time.sleep(3)
        rc, out, err = _run(["iwctl", "station", iface, "get-networks"], timeout=15)
        nets = []
        for raw in ANSI.sub("", out).splitlines():
            line = raw.rstrip()
            m = re.match(r"^\s*(>)?\s*(.+?)\s{2,}(psk|open|8021x|wep|sae|owe)\s+(\*+)\s*$", line)
            if m:
                nets.append(dict(ssid=m.group(2).strip(), security=m.group(3),
                                 signal=len(m.group(4)), connected=bool(m.group(1))))
        return nets

    def wifi_connect(self, iface, ssid, psk):
        if psk:
            safe = re.fullmatch(r"[A-Za-z0-9 _-]+", ssid)
            fname = ssid if safe else "=" + ssid.encode().hex()
            d = Path("/var/lib/iwd")
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{fname}.psk").write_text(f"[Security]\nPassphrase={psk}\n")
            os.chmod(d / f"{fname}.psk", 0o600)
        rc, out, err = _run(["iwctl", "station", iface, "connect", ssid], timeout=40)
        for _ in range(20):
            if self.online(timeout=2):
                return {"ok": True}
            time.sleep(1)
        return {"ok": False, "error": ANSI.sub("", err or out).strip() or "Could not connect."}

    def search_packages(self, query, limit=40):
        rc, out, _ = _run(["pacman", "-Ss", "--", query], timeout=20)
        res, lines = [], out.splitlines()
        for i, line in enumerate(lines):
            m = re.match(r"^(\S+)/(\S+) (\S+)", line)
            if m:
                desc = lines[i + 1].strip() if i + 1 < len(lines) else ""
                res.append(dict(repo=m.group(1), name=m.group(2), version=m.group(3), desc=desc))
        res.sort(key=lambda r: (r["name"] != query, not r["name"].startswith(query), r["name"]))
        return res[:limit]


def tool_paths():
    """Binaries a real install needs in the live system."""
    return ("sgdisk", "wipefs", "partprobe", "udevadm", "mkfs.ext4", "mkfs.fat", "mkswap",
            "cryptsetup", "pacstrap", "arch-chroot", "genfstab", "blkid", "pacman")
