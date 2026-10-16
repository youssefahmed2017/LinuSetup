"""Turns an InstallConfig + Hardware into an ordered list of Steps.

Pure function: building a plan never touches the system, so it can be
inspected, logged and unit-tested anywhere. Only runner.Runner executes it.
"""
from dataclasses import dataclass, field
from typing import Callable, Union

from . import presets as P
from .config import InstallConfig
from .hardware import Hardware

MNT = "/mnt"


@dataclass
class Cmd:
    argv: list
    stdin: str = None          # passed on stdin; never logged (may hold a password)
    stdout_to: str = None      # append stdout to this file (genfstab)
    sim: float = 0.15          # seconds this takes in dry-run
    progress_re: str = None    # regex with 2 groups (n, total) to derive progress


@dataclass
class Write:
    path: str
    content: Union[str, Callable]   # callable(runner) -> str, evaluated at run time
    mode: int = 0o644


@dataclass
class Step:
    id: str
    label: str
    weight: int
    actions: list = field(default_factory=list)


def part_path(disk: str, n: int) -> str:
    """/dev/sda + 2 -> /dev/sda2 ; /dev/nvme0n1 + 2 -> /dev/nvme0n1p2"""
    return f"{disk}p{n}" if disk[-1].isdigit() else f"{disk}{n}"


def chroot(*argv, **kw) -> Cmd:
    return Cmd(["arch-chroot", MNT, *argv], **kw)


def package_list(cfg: InstallConfig, hw: Hardware):
    pkgs = list(P.BASE_PACKAGES) + list(P.DESKTOP_PACKAGES)
    if hw.cpu_vendor in ("intel", "amd"):
        pkgs.append(f"{hw.cpu_vendor}-ucode")
    chosen = [P.PRESETS[p] for p in cfg.presets]
    multilib = any(p.multilib for p in chosen)
    for p in chosen:
        pkgs += p.packages
    if hw.gpus:
        for g in hw.gpus:
            base, lib32 = P.GPU_PACKAGES[g]
            pkgs += base
            if multilib:
                pkgs += lib32
    elif multilib:
        pkgs += P.FALLBACK_VULKAN + P.FALLBACK_32BIT_VULKAN
    pkgs.append("grub" if not hw.uefi else "efibootmgr")
    seen, out = set(), []
    for p in pkgs:          # de-dupe, keep order
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out, multilib


def build_plan(cfg: InstallConfig, hw: Hardware) -> list:
    disk = cfg.disk
    boot_part, root_part = part_path(disk, 1), part_path(disk, 2)
    pkgs, multilib = package_list(cfg, hw)
    chosen = [P.PRESETS[p] for p in cfg.presets]
    services = list(P.BASE_SERVICES) + [s for p in chosen for s in p.services]
    groups = ["wheel"] + [g for p in chosen for g in p.groups]

    steps = []

    # 1. Partition: GPT. UEFI -> 1 GiB ESP + root. BIOS -> 1 MiB bios_grub + root.
    first = (["-n1:0:+1GiB", "-t1:ef00", "-c1:ESP"] if hw.uefi
             else ["-n1:0:+1MiB", "-t1:ef02", "-c1:BIOSBOOT"])
    steps.append(Step("partition", "Preparing the disk", 4, [
        Cmd(["wipefs", "--all", "--force", disk]),
        Cmd(["sgdisk", "--zap-all", disk]),
        Cmd(["sgdisk", *first, "-n2:0:0", "-t2:8304", "-c2:root", disk]),
        Cmd(["partprobe", disk]),
        Cmd(["udevadm", "settle"]),
    ]))

    # 2. Filesystems + mount
    fs = [Cmd(["mkfs.ext4", "-F", "-L", "arch", root_part]),
          Cmd(["mount", root_part, MNT])]
    if hw.uefi:
        fs.insert(0, Cmd(["mkfs.fat", "-F32", "-n", "ESP", boot_part]))
        fs.append(Cmd(["mount", "--mkdir", boot_part, f"{MNT}/boot"]))
    steps.append(Step("filesystems", "Creating filesystems", 3, fs))

    # 3. Packages
    pre = []
    if multilib:
        # The live system's pacman.conf is what pacstrap uses; the ISO build
        # enables multilib there. Refresh the DBs so lib32 packages resolve.
        pre.append(Cmd(["pacman", "-Sy", "--noconfirm"], sim=0.3))
    steps.append(Step("packages", "Installing Arch Linux and your desktop", 70, pre + [
        Cmd(["pacstrap", "-K", MNT, *pkgs], sim=6.0, progress_re=r"\(\s*(\d+)/(\d+)\)"),
    ]))

    # 4. System configuration
    conf = [
        Cmd(["genfstab", "-U", MNT], stdout_to=f"{MNT}/etc/fstab"),
        Write(f"{MNT}/etc/hostname", cfg.hostname + "\n"),
        Write(f"{MNT}/etc/locale.conf", f"LANG={cfg.locale}\n"),
        Write(f"{MNT}/etc/vconsole.conf", f"KEYMAP={cfg.keymap}\n"),
        Cmd(["sed", "-i", f"s/^#{cfg.locale} UTF-8/{cfg.locale} UTF-8/", f"{MNT}/etc/locale.gen"]),
        chroot("locale-gen"),
        chroot("ln", "-sf", f"/usr/share/zoneinfo/{cfg.timezone}", "/etc/localtime"),
        chroot("hwclock", "--systohc"),
        Write(f"{MNT}/etc/hosts",
              f"127.0.0.1 localhost\n::1 localhost\n127.0.1.1 {cfg.hostname}\n"),
    ]
    if multilib:
        conf.append(Cmd(["sed", "-i", r"/^#\[multilib\]/,/^#Include/ s/^#//",
                         f"{MNT}/etc/pacman.conf"]))
    steps.append(Step("configure", "Configuring the system", 4, conf))

    # 5. User
    steps.append(Step("user", "Creating your account", 2, [
        chroot("useradd", "-m", "-G", ",".join(groups), "-s", "/bin/bash",
               "-c", cfg.fullname or cfg.username, cfg.username),
        chroot("chpasswd", stdin=f"{cfg.username}:{cfg.password}\n"),
        Write(f"{MNT}/etc/sudoers.d/10-wheel", "%wheel ALL=(ALL:ALL) ALL\n", 0o440),
        chroot("passwd", "-l", "root"),
    ]))

    # 6. Bootloader
    if hw.uefi:
        ucode = f"initrd /{hw.cpu_vendor}-ucode.img\n" if hw.cpu_vendor in ("intel", "amd") else ""

        def entry(runner):
            uuid = runner.capture(["blkid", "-s", "UUID", "-o", "value", root_part])
            return ("title   Arch Linux\nlinux   /vmlinuz-linux\n" + ucode +
                    "initrd  /initramfs-linux.img\n"
                    f"options root=UUID={uuid} rw\n")
        boot = [
            chroot("bootctl", "install"),
            Write(f"{MNT}/boot/loader/loader.conf", "default arch.conf\ntimeout 3\neditor no\n"),
            Write(f"{MNT}/boot/loader/entries/arch.conf", entry),
        ]
    else:
        boot = [
            chroot("grub-install", "--target=i386-pc", disk),
            chroot("grub-mkconfig", "-o", "/boot/grub/grub.cfg"),
        ]
    steps.append(Step("bootloader", "Installing the boot loader", 5, boot))

    # 7. Services + finish
    steps.append(Step("finish", "Finishing up", 3, [
        chroot("systemctl", "enable", *services),
        Cmd(["sync"]),
        Cmd(["umount", "-R", MNT]),
    ]))
    return steps
