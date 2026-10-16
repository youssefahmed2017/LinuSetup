"""Disk choices -> an exact Layout: what to wipe, delete, shrink and create,
and what gets formatted and mounted where. Pure: reads Disk models only.

This is where data can be lost, so every rule is explicit and tested, including
by applying the generated partition operations to real image files.
"""
from dataclasses import dataclass, field, replace

from . import disks as D
from .disks import MiB, GiB

ROOT_MIN = 16 * GiB
HOME_MIN = 4 * GiB
ESP_SIZE = 1 * GiB
BOOT_SIZE = 1 * GiB
SHRINK_MARGIN = 2 * GiB          # keep this much free inside a shrunk Windows volume
MAPPER = {"/": "cryptroot", "/home": "crypthome"}


class LayoutError(ValueError):
    """A user-facing explanation of why the requested layout is impossible."""


@dataclass
class NewPart:
    disk: str
    number: int
    start: int
    end: int
    typecode: str
    name: str

    @property
    def node(self):
        return D.part_node(self.disk, self.number)

    @property
    def size(self):
        return self.end - self.start


@dataclass
class Shrink:
    disk: str
    number: int
    node: str
    start: int
    old_size: int
    new_size: int          # new partition size
    fs_size: int           # ntfsresize target, a little smaller than the partition
    type_guid: str
    uuid: str
    name: str
    log_sec: int = 512


@dataclass
class Volume:
    node: str
    mount: str             # "/", "/boot", "[SWAP]", "" for bios_grub
    fs: str                # ext4 btrfs xfs f2fs vfat swap bios_grub | "" = keep existing
    format: bool
    label: str = ""
    encrypt: bool = False
    mapper: str = ""
    subvols: list = field(default_factory=list)    # [(name, mountpoint)]
    options: str = ""
    new: bool = True

    @property
    def device(self):
        return f"/dev/mapper/{self.mapper}" if self.encrypt else self.node


@dataclass
class Layout:
    wipe: list = field(default_factory=list)
    delete: list = field(default_factory=list)       # [(disk, number, node)]
    shrink: list = field(default_factory=list)       # [Shrink]
    create: list = field(default_factory=list)       # [NewPart]
    volumes: list = field(default_factory=list)      # [Volume]
    bios_grub_disk: str = ""
    dual_boot: bool = False

    def by_mount(self, mount):
        return next((v for v in self.volumes if v.mount == mount), None)

    @property
    def root(self):
        return self.by_mount("/")

    @property
    def esp(self):
        return next((v for v in self.volumes if v.fs == "vfat" and v.mount in ("/boot", "/efi")), None)

    @property
    def esp_fresh(self):
        e = self.esp
        return bool(e and e.new)

    def mount_order(self):
        vols = [v for v in self.volumes if v.mount.startswith("/")]
        return sorted(vols, key=lambda v: (v.mount != "/", v.mount.count("/"), v.mount))

    def encrypted(self):
        return [v for v in self.volumes if v.encrypt]

    def touched_disks(self):
        out = list(self.wipe)
        for d in [x[0] for x in self.delete] + [s.disk for s in self.shrink] + [c.disk for c in self.create]:
            if d not in out:
                out.append(d)
        return out

    def summary(self):
        """Every destructive action, in plain language, for the confirmation dialog."""
        out = []
        for d in self.wipe:
            out.append(dict(kind="wipe", text=f"Erase everything on {d}"))
        for d, n, node in self.delete:
            out.append(dict(kind="delete", text=f"Delete partition {node}"))
        for s in self.shrink:
            out.append(dict(kind="shrink", text=f"Shrink {s.node} from {gb(s.old_size)} to {gb(s.new_size)}"))
        for c in self.create:
            out.append(dict(kind="create", text=f"Create {c.node} ({gb(c.size)}, {c.name})"))
        for v in self.volumes:
            if v.format and v.fs not in ("bios_grub",):
                what = f"Format {v.node} as {v.fs}" + (" (encrypted)" if v.encrypt else "")
                out.append(dict(kind="format", text=what + (f", mounted at {v.mount}" if v.mount.startswith("/") else "")))
            elif not v.format and v.mount:
                out.append(dict(kind="keep", text=f"Use {v.node} at {v.mount} without formatting"))
        return out

    def preview(self, disks):
        """Per touched disk: resulting partitions, for drawing the 'after' bar."""
        out = {}
        for path in self.touched_disks():
            disk = next((d for d in disks if d.path == path), None)
            if not disk:
                continue
            rows = []
            if path not in self.wipe:
                gone = {n for d, n, _ in self.delete if d == path}
                for p in disk.partitions:
                    if p.number in gone:
                        continue
                    s = next((x for x in self.shrink if x.node == p.node), None)
                    rows.append(dict(node=p.node, start=p.start, size=s.new_size if s else p.size,
                                     kind=p.kind, label=p.label or p.name, new=False,
                                     mount=next((v.mount for v in self.volumes if v.node == p.node), "")))
            for c in self.create:
                if c.disk == path:
                    v = next((v for v in self.volumes if v.node == c.node), None)
                    rows.append(dict(node=c.node, start=c.start, size=c.size, kind="new",
                                     label=c.name, new=True, mount=v.mount if v else "",
                                     fs=v.fs if v else "", encrypt=v.encrypt if v else False))
            out[path] = dict(size=disk.size, partitions=sorted(rows, key=lambda r: r["start"]))
        return out


def gb(n):
    return f"{n / 1e9:.1f} GB" if n < 1e12 else f"{n / 1e12:.2f} TB"


def _btrfs_subvols(cfg, separate_home):
    b = cfg["disk"]["btrfs"]
    if not b.get("subvolumes", True):
        return []
    sv = [("@", "/")]
    if not separate_home:
        sv.append(("@home", "/home"))
    sv += [("@log", "/var/log"), ("@pkg", "/var/cache/pacman/pkg")]
    if b.get("snapshots"):
        sv.append(("@snapshots", "/.snapshots"))
    if cfg["swap"]["mode"] == "swapfile":
        sv.append(("@swap", "/swap"))
    return sv


def _mount_options(cfg, fs):
    if fs == "btrfs":
        c = cfg["disk"]["btrfs"].get("compress", "zstd")
        return ",".join(x for x in ["noatime", f"compress={c}" if c and c != "none" else ""] if x)
    if fs == "vfat":
        return "umask=0077"
    return ""


class _Numbers:
    def __init__(self, used):
        self.used = set(used)

    def take(self):
        n = 1
        while n in self.used:
            n += 1
        self.used.add(n)
        return n


# ---------------------------------------------------------------- guided

def guided(cfg, hw, disks):
    g = cfg["disk"]
    disk = next((d for d in disks if d.path == g["device"]), None)
    if disk is None:
        raise LayoutError("Choose the disk to install on.")
    if not disk.usable:
        raise LayoutError(f"{disk.path} can't be used: {disk.reason}")
    scope, fs = g["scope"], g["fs"]
    enc = g["encryption"]["enabled"]
    swap = cfg["swap"]
    lay = Layout()

    if scope == "wipe":
        lay.wipe = [disk.path]
        numbers, existing = _Numbers(()), []
        region = (disk.usable_start, disk.usable_end)
    else:
        if disk.pttype != "gpt":
            raise LayoutError("This disk has an old-style (MBR) partition table. "
                              "LinuSetup can only install next to other systems on GPT disks. "
                              "Choose 'Erase disk' or another disk.")
        existing = list(disk.partitions)
        numbers = _Numbers(p.number for p in existing)
        if scope == "free":
            regions = disk.free_regions()
            if not regions:
                raise LayoutError("There is no free space on this disk.")
            region = max(regions, key=lambda r: r[1] - r[0])
        elif scope == "shrink":
            region = _plan_shrink(cfg, disk, lay, existing)
        else:
            raise LayoutError(f"Unknown disk option '{scope}'.")
    lay.dual_boot = scope != "wipe" and disk.has_windows()

    cursor, end = region

    def take(size, code, name):
        nonlocal cursor
        stop = end if size is None else cursor + size
        if stop > end:
            raise LayoutError(f"Not enough space: the {name} partition does not fit "
                              f"({gb(end - cursor)} left).")
        np = NewPart(disk.path, numbers.take(), cursor, stop, D.TYPECODE[code], name)
        lay.create.append(np)
        cursor = stop
        return np.node

    # --- boot pieces
    if hw.uefi:
        esp = next((p for p in existing if p.kind == "esp"), None)
        if esp:
            lay.volumes.append(Volume(esp.node, "/efi", "vfat", False, new=False,
                                      options=_mount_options(cfg, "vfat")))
        else:
            lay.volumes.append(Volume(take(ESP_SIZE, "esp", "EFI system"), "/boot", "vfat", True,
                                      label="ESP", options=_mount_options(cfg, "vfat")))
        if enc and esp:
            lay.volumes.append(Volume(take(BOOT_SIZE, "linux", "boot"), "/boot", "ext4", True, label="boot"))
    else:
        if not any(p.kind == "bios" for p in existing):
            take(1 * MiB, "bios", "BIOS boot")
            lay.volumes.append(Volume(lay.create[-1].node, "", "bios_grub", False))
        lay.bios_grub_disk = disk.path
        if enc:
            lay.volumes.append(Volume(take(BOOT_SIZE, "linux", "boot"), "/boot", "ext4", True, label="boot"))

    # --- swap partition
    if swap["mode"] == "partition":
        if enc:
            raise LayoutError("A swap partition can't be combined with encryption. "
                              "Use zram or a swap file instead.")
        size = int(float(swap["size_gb"]) * GiB) // MiB * MiB
        if size < 256 * MiB:
            raise LayoutError("The swap partition must be at least 0.25 GB.")
        lay.volumes.append(Volume(take(size, "swap", "swap"), "[SWAP]", "swap", True, label="swap"))

    # --- root (+ home)
    sep = g["home"]["separate"]
    left = end - cursor
    if sep:
        root_size = int(float(g["home"]["root_gb"]) * GiB) // MiB * MiB
        if root_size < ROOT_MIN:
            raise LayoutError(f"The system partition needs at least {gb(ROOT_MIN)}.")
        if left - root_size < HOME_MIN:
            raise LayoutError(f"Not enough space left for /home ({gb(max(0, left - root_size))}).")
    elif left < ROOT_MIN:
        raise LayoutError(f"Not enough space: Arch needs at least {gb(ROOT_MIN)} "
                          f"and only {gb(max(left, 0))} is available.")
    code_root, code_home = ("luks", "luks") if enc else ("root", "home")
    root_node = take(root_size if sep else None, code_root, "root")
    lay.volumes.append(Volume(root_node, "/", fs, True, label="arch", encrypt=enc,
                              mapper=MAPPER["/"] if enc else "",
                              subvols=_btrfs_subvols(cfg, sep) if fs == "btrfs" else [],
                              options=_mount_options(cfg, fs)))
    if sep:
        lay.volumes.append(Volume(take(None, code_home, "home"), "/home", fs, True, label="home",
                                  encrypt=enc, mapper=MAPPER["/home"] if enc else "",
                                  options=_mount_options(cfg, fs)))
    return lay


def _plan_shrink(cfg, disk, lay, existing):
    sh = cfg["disk"]["shrink"]
    p = disk.part(sh.get("partition") or "")
    if p is None:
        raise LayoutError("Choose the Windows partition to shrink.")
    if p.kind == "bitlocker":
        raise LayoutError(f"{p.node} is encrypted with BitLocker, which can't be resized from Linux. "
                          "Shrink it from Windows (Disk Management), then choose 'Use free space'.")
    if p.fstype != "ntfs":
        raise LayoutError(f"Only Windows (NTFS) partitions can be shrunk; {p.node} is "
                          f"{p.fstype or 'unformatted'}.")
    if p.mounted:
        raise LayoutError(f"{p.node} is mounted. Unmount it first.")
    free = int(float(sh.get("free_gb") or 0) * GiB) // MiB * MiB
    if free < ROOT_MIN + 2 * GiB:
        raise LayoutError(f"Free up at least {gb(ROOT_MIN + 2 * GiB)} for Arch Linux.")
    new_size = (p.size - free) // MiB * MiB
    min_bytes = sh.get("min_bytes")
    if min_bytes and new_size < int(min_bytes) + SHRINK_MARGIN:
        raise LayoutError(f"Windows needs at least {gb(int(min_bytes) + SHRINK_MARGIN)} on {p.node} "
                          f"(its files plus some room). Free up less space.")
    if new_size < 8 * GiB:
        raise LayoutError("That would leave Windows with too little space.")
    lay.shrink.append(Shrink(disk=disk.path, number=p.number, node=p.node, start=p.start,
                             old_size=p.size, new_size=new_size, fs_size=new_size - MiB,
                             type_guid=p.type_guid, uuid=p.uuid, name=p.name,
                             log_sec=disk.log_sec))
    after = [replace(q, size=new_size) if q is p else q for q in existing]
    gap_start = -(-(p.start + new_size) // MiB) * MiB
    region = next((r for r in disk.free_regions(after) if r[0] == gap_start), None)
    if region is None:
        raise LayoutError("Could not find the space freed by shrinking.")
    return region


# ---------------------------------------------------------------- manual

MANUAL_FS = ("ext4", "btrfs", "xfs", "f2fs", "vfat", "swap", "bios_grub")


def manual(cfg, hw, disks):
    m = cfg["disk"]["manual"]
    by_path = {d.path: d for d in disks}
    lay = Layout()
    for path in m.get("wipe", []):
        d = by_path.get(path)
        if d is None:
            raise LayoutError(f"Disk {path} not found.")
        if not d.usable:
            raise LayoutError(f"{path} can't be used: {d.reason}")
        lay.wipe.append(path)

    def find_part(node):
        for d in disks:
            for p in d.partitions:
                if p.node == node:
                    return d, p
        return None, None

    deleted = set()
    for node in m.get("delete", []):
        d, p = find_part(node)
        if p is None:
            raise LayoutError(f"Partition {node} not found.")
        if d.path in lay.wipe:
            continue
        if p.mounted or not d.usable:
            raise LayoutError(f"{node} is on a disk that is in use and can't be deleted.")
        if d.pttype != "gpt":
            raise LayoutError(f"{d.path} has an MBR partition table; only erasing the whole disk is supported.")
        lay.delete.append((d.path, p.number, node))
        deleted.add(node)

    mounts = {}

    def add_volume(v):
        if v.mount and v.mount != "[SWAP]":
            if not v.mount.startswith("/") or " " in v.mount or "//" in v.mount:
                raise LayoutError(f"'{v.mount}' is not a valid mount point.")
            if v.mount in mounts:
                raise LayoutError(f"Two partitions are set to mount at {v.mount}.")
            mounts[v.mount] = v
        lay.volumes.append(v)

    for e in m.get("existing", []):
        d, p = find_part(e.get("device", ""))
        if p is None or e["device"] in deleted or (d and d.path in lay.wipe):
            raise LayoutError(f"Partition {e.get('device')} is not available.")
        if not d.usable and p.mounted:
            raise LayoutError(f"{p.node} is mounted.")
        if p.kind == "bitlocker":
            raise LayoutError(f"{p.node} is BitLocker-encrypted and can't be used.")
        fmt = bool(e.get("format"))
        fs = e.get("fs", "") if fmt else ""
        if fmt and fs not in MANUAL_FS[:-1]:
            raise LayoutError(f"Choose a filesystem for {p.node}.")
        if e.get("encrypt") and not fmt:
            raise LayoutError(f"{p.node} must be formatted to be encrypted.")
        mount = "[SWAP]" if fs == "swap" or (not fmt and p.fstype == "swap") else e.get("mount", "")
        if not mount:
            raise LayoutError(f"Choose where {p.node} is mounted.")
        if not fmt and mount in ("/boot", "/efi") and p.fstype not in ("vfat", "ext4", "xfs", "btrfs"):
            raise LayoutError(f"{p.node} can't be used as {mount} without formatting it.")
        enc = bool(e.get("encrypt"))
        add_volume(Volume(p.node, mount, fs if fmt else ("vfat" if p.fstype == "vfat" and mount in ("/boot", "/efi") else ""),
                          fmt, label=e.get("label", ""), encrypt=enc,
                          mapper=_mapper_name(mount, enc, lay), new=False,
                          options=_mount_options(cfg, fs or p.fstype),
                          subvols=_btrfs_subvols(cfg, "/home" in [x.get("mount") for x in m.get("existing", []) + m.get("new", [])])
                          if fmt and fs == "btrfs" and mount == "/" else []))

    numbers = {}
    for path in {n.get("disk") for n in m.get("new", [])}:
        d = by_path.get(path)
        if d is None:
            raise LayoutError(f"Disk {path} not found.")
        if path not in lay.wipe and d.pttype != "gpt":
            raise LayoutError(f"{path} has no GPT partition table. Erase it first to create partitions.")
        if not d.usable:
            raise LayoutError(f"{path} can't be used: {d.reason}")
        keep = [] if path in lay.wipe else [p for p in d.partitions if p.node not in deleted]
        numbers[path] = (_Numbers(p.number for p in keep),
                         d.free_regions(keep) if path not in lay.wipe else [(d.usable_start, d.usable_end)])

    placed = []
    for n in m.get("new", []):
        path = n.get("disk")
        nums, regions = numbers[path]
        start = int(n.get("start_mib", 0)) * MiB
        size = int(n.get("size_mib", 0)) * MiB
        fs = n.get("fs", "")
        if fs not in MANUAL_FS:
            raise LayoutError("Choose a filesystem for every new partition.")
        if size < MiB:
            raise LayoutError("A new partition is too small.")
        stop = start + size
        if not any(r[0] <= start and stop <= r[1] for r in regions):
            raise LayoutError(f"A new partition on {path} doesn't fit in free space.")
        if any(o[0] == path and start < o[2] and o[1] < stop for o in placed):
            raise LayoutError(f"Two new partitions on {path} overlap.")
        placed.append((path, start, stop))
        enc = bool(n.get("encrypt"))
        code = {"vfat": "esp", "swap": "swap", "bios_grub": "bios"}.get(fs, "luks" if enc else "linux")
        np = NewPart(path, nums.take(), start, stop, D.TYPECODE[code], n.get("label") or code)
        lay.create.append(np)
        if fs == "bios_grub":
            lay.volumes.append(Volume(np.node, "", "bios_grub", False))
            continue
        mount = "[SWAP]" if fs == "swap" else n.get("mount", "")
        if not mount:
            raise LayoutError(f"Choose where the new {fs} partition is mounted.")
        if fs in ("vfat", "swap") and enc:
            raise LayoutError("Boot and swap partitions can't be encrypted here.")
        add_volume(Volume(np.node, mount, fs, True, label=n.get("label", ""), encrypt=enc,
                          mapper=_mapper_name(mount, enc, lay),
                          options=_mount_options(cfg, fs),
                          subvols=_btrfs_subvols(cfg, "/home" in [x.get("mount") for x in m.get("existing", []) + m.get("new", [])])
                          if fs == "btrfs" and mount == "/" else []))
    lay.create.sort(key=lambda c: (c.disk, c.start))

    # --- whole-layout rules
    root = lay.root
    if root is None:
        raise LayoutError("One partition must be mounted at / (the system).")
    if not root.format:
        raise LayoutError("The / partition must be formatted.")
    esp = next((v for v in lay.volumes if v.mount in ("/boot", "/efi") and (v.fs == "vfat")), None)
    if hw.uefi and esp is None:
        raise LayoutError("UEFI needs an EFI system partition (FAT32) mounted at /boot or /efi.")
    if hw.uefi and esp.mount == "/efi" and "/boot" in mounts and mounts["/boot"].fs == "vfat":
        raise LayoutError("Mount only one FAT partition for booting.")
    if root.encrypt and not mounts.get("/boot"):
        raise LayoutError("An encrypted / needs a separate, unencrypted /boot partition "
                          "(the EFI partition at /boot works).")
    if mounts.get("/boot") and mounts["/boot"].encrypt:
        raise LayoutError("/boot can't be encrypted.")
    if not hw.uefi:
        boot_vol = mounts.get("/boot") or root
        bdisk = _disk_of(boot_vol.node, disks)
        has_bios = any(v.fs == "bios_grub" and _disk_of(v.node, disks) == bdisk for v in lay.volumes) or \
            (bdisk not in lay.wipe and any(p.kind == "bios" and p.node not in deleted
                                            for p in by_path[bdisk].partitions))
        if not has_bios:
            raise LayoutError(f"BIOS boot needs a 1 MB 'BIOS boot' partition on {bdisk}.")
        lay.bios_grub_disk = bdisk
    lay.dual_boot = any(by_path[p].has_windows() for p in {_disk_of(v.node, disks) for v in lay.volumes}
                        if p in by_path and p not in lay.wipe)
    return lay


def _mapper_name(mount, enc, lay):
    if not enc:
        return ""
    if mount in MAPPER:
        return MAPPER[mount]
    return "crypt" + (mount.strip("/").replace("/", "-") or "root")


def _disk_of(node, disks):
    for d in disks:
        if node.startswith(d.path) and (node == d.path or d.part(node) is not None
                                        or node[len(d.path):].lstrip("p").isdigit()):
            return d.path
    return ""


def resolve(cfg, hw, disks):
    mode = cfg["disk"]["mode"]
    if mode == "guided":
        return guided(cfg, hw, disks)
    if mode == "manual":
        return manual(cfg, hw, disks)
    raise LayoutError(f"Unknown disk mode '{mode}'.")


def resolve_bootloader(cfg, hw, lay):
    want = cfg["bootloader"]["type"]
    if not hw.uefi:
        if want == "systemd-boot":
            raise LayoutError("systemd-boot needs UEFI. This computer booted in legacy BIOS mode; use GRUB.")
        return "grub"
    esp = lay.esp
    esp_at_boot = bool(esp and esp.mount == "/boot")
    if want == "systemd-boot" and not esp_at_boot:
        raise LayoutError("systemd-boot needs the EFI partition mounted at /boot. "
                          "When reusing a small Windows EFI partition, use GRUB.")
    if want == "auto":
        return "systemd-boot" if esp_at_boot and not lay.dual_boot else "grub"
    if want not in ("systemd-boot", "grub"):
        raise LayoutError(f"Unknown boot loader '{want}'.")
    return want
