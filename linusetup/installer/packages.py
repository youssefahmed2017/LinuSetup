"""Config + hardware + layout -> packages, services and groups. Pure."""
from dataclasses import dataclass, field

from . import catalog as C

GRAPHICAL_KINDS = ("desktop", "wm")
# sddm autologin needs a session name; only set it where it is known.
SDDM_SESSIONS = {"kde": "plasma", "hyprland": "hyprland", "sway": "sway", "lxqt": "lxqt"}


@dataclass
class Selection:
    packages: list = field(default_factory=list)
    services: list = field(default_factory=list)
    user_groups: list = field(default_factory=list)   # extra groups for every sudo user
    multilib: bool = False
    graphical: bool = False
    greeter: str = "none"
    drivers: list = field(default_factory=list)
    skel: list = field(default_factory=list)          # [(src, dest_rel, mode)]
    kms_hook: bool = True

    def add(self, *pkgs):
        for p in pkgs:
            if p and p not in self.packages:
                self.packages.append(p)

    def enable(self, *svcs):
        for s in svcs:
            if s and s not in self.services:
                self.services.append(s)


def resolve_drivers(cfg, hw):
    if cfg["graphics"] != "auto":
        return [cfg["graphics"]]
    out = []
    if hw.virt:
        out.append("vm")
    for v in hw.gpu_vendors():
        d = {"nvidia": "nvidia-open", "amd": "amd", "intel": "intel"}.get(v, "mesa")
        if d not in out:
            out.append(d)
    return out or ["mesa"]


def resolve_greeter(cfg):
    if cfg["greeter"] != "auto":
        return cfg["greeter"]
    for p in cfg["profiles"]:
        g = C.PROFILES.get(p, {}).get("greeter", "none")
        if g != "none":
            return g
    return "none"


def is_graphical(cfg):
    return any(C.PROFILES.get(p, {}).get("kind") in GRAPHICAL_KINDS for p in cfg["profiles"])


def needs_multilib(cfg):
    return bool(cfg["mirrors"]["multilib"]) or any(
        C.SOFTWARE_INDEX[s].get("needs_multilib") for s in cfg["software"] if s in C.SOFTWARE_INDEX)


def compute(cfg, hw, lay, bootloader):
    s = Selection()
    s.multilib = needs_multilib(cfg)
    s.graphical = is_graphical(cfg)
    s.greeter = resolve_greeter(cfg) if s.graphical else "none"

    s.add(*C.BASE)
    kernels = list(cfg["kernels"])
    s.add(*kernels)
    if hw.cpu_vendor in ("intel", "amd"):
        s.add(f"{hw.cpu_vendor}-ucode")

    # filesystems, encryption, boot
    for v in lay.volumes:
        s.add(*C.FS_PACKAGES.get(v.fs, ()))
    if hw.uefi:
        s.add("dosfstools")
    if lay.encrypted():
        s.add("cryptsetup")
    if bootloader == "grub":
        s.add("grub")
        if hw.uefi:
            s.add("efibootmgr")
        if cfg["bootloader"]["os_prober"] and lay.dual_boot:
            s.add("os-prober", "ntfs-3g")
    else:
        s.add("efibootmgr")
        s.enable("systemd-boot-update.service")

    # network
    _, pk, sv = C.NETWORK[cfg["network"]["manager"]]
    s.add(*pk)
    s.enable(*sv)

    # desktops
    for pid in cfg["profiles"]:
        p = C.PROFILES[pid]
        s.add(*p["packages"])
        s.enable(*p.get("services", ()))
        s.skel += list(p.get("skel", ()))
        if p.get("x11"):
            s.add("xorg-server")
    if s.graphical:
        s.add(*C.DESKTOP_BASE)
        _, gpk, gsvc = C.GREETERS[s.greeter]
        s.add(*gpk)
        s.enable(gsvc)

    # graphics drivers (+ 32-bit parts when multilib is on)
    s.drivers = resolve_drivers(cfg, hw) if s.graphical or cfg["graphics"] != "auto" else []
    headers = bool(cfg["headers"])
    for d in s.drivers:
        if d == "nvidia-open":
            if kernels == ["linux"]:
                s.add("nvidia-open")
            else:
                s.add("nvidia-open-dkms")
                headers = True
            s.kms_hook = False
        base, lib32 = C.GRAPHICS_PACKAGES[d]
        s.add(*base)
        if s.multilib:
            s.add(*lib32)
    if headers:
        s.add(*[f"{k}-headers" for k in kernels])
    if cfg["vm_tools"] and hw.virt in C.VM_TOOLS:
        pk, sv = C.VM_TOOLS[hw.virt]
        s.add(*pk)
        s.enable(*sv)

    # sound, devices, security
    s.add(*C.AUDIO[cfg["audio"]][1])
    if cfg["bluetooth"]:
        s.add("bluez", "bluez-utils")
        s.enable("bluetooth")
    if cfg["printing"]:
        s.add("cups", "cups-pdf", "avahi", "nss-mdns", "ghostscript")
        if s.graphical:
            s.add("system-config-printer")
        s.enable("cups", "avahi-daemon")
    _, pk, sv = C.FIREWALLS[cfg["firewall"]]
    s.add(*pk)
    s.enable(*sv)
    if cfg["ssh"]:
        s.add("openssh")
        s.enable("sshd")

    # software
    for sid in cfg["software"]:
        item = C.SOFTWARE_INDEX[sid]
        s.add(*item["packages"])
        s.enable(*item.get("services", ()))
        for g in item.get("groups", ()):
            if g not in s.user_groups:
                s.user_groups.append(g)
    if cfg["flatpak"]:
        s.add("flatpak")
    if cfg["aur_helper"] != "none":
        s.add("base-devel", "git")
    for u in cfg["users"]:
        s.add(*C.SHELLS.get(u.get("shell", "bash"), ("", ()))[1])
    s.add(*cfg["extra_packages"])

    # swap / snapshots / time
    if cfg["swap"]["mode"] == "zram":
        s.add("zram-generator")
    root = lay.root
    if root and root.fs == "btrfs" and cfg["disk"]["btrfs"].get("snapshots"):
        s.add("snapper", "snap-pac")
        s.enable("snapper-timeline.timer", "snapper-cleanup.timer")
        if bootloader == "grub":
            s.add("grub-btrfs", "inotify-tools")
            s.enable("grub-btrfsd")
    if cfg["ntp"]:
        s.enable("systemd-timesyncd")
    s.enable("fstrim.timer")
    return s
