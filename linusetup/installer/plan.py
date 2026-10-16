"""Config + hardware + disks -> an ordered list of Steps. Pure: building a plan
never touches the system, so it is shown in full on the review screen and
unit-tested. Only runner.Runner executes it."""
import shlex
from dataclasses import dataclass, field
from typing import Callable, Union

from . import catalog as C
from . import layout as L
from . import packages as P
from .disks import MiB

MNT = "/mnt"


@dataclass
class Cmd:
    argv: list
    stdin: str = None          # never logged (may hold a password)
    stdout_to: str = None      # append stdout to this file
    sim: float = 0.15          # seconds in a dry run; also the action's progress weight
    progress: str = None       # "pacman": derive in-step progress from pacman's output
    optional: bool = False     # failure becomes a warning instead of aborting
    quiet: bool = False        # don't stream stdout into the log

    def show(self):
        return " ".join(shlex.quote(a) for a in self.argv) + ("  < (hidden input)" if self.stdin else "")


@dataclass
class Write:
    path: str
    content: Union[str, Callable]   # callable(runner) -> str, evaluated at run time
    mode: int = 0o644
    append: bool = False
    secret: bool = False            # content never shown in previews or logs

    sim = 0.05
    optional = False

    def show(self):
        return f"{'append to' if self.append else 'write'} {self.path}"


@dataclass
class CopyLog:
    path: str
    sim = 0.05
    optional = True

    def show(self):
        return f"save the install log to {self.path}"


@dataclass
class Step:
    id: str
    label: str
    weight: int
    actions: list = field(default_factory=list)
    always: list = field(default_factory=list)   # run even if `actions` failed (cleanup)


@dataclass
class Plan:
    steps: list
    cleanup: list
    layout: object
    bootloader: str
    selection: object

    def preview(self):
        return [dict(id=s.id, label=s.label,
                     commands=[a.show() for a in s.actions + s.always]) for s in self.steps]


def chroot(*argv, **kw):
    return Cmd(["arch-chroot", MNT, *argv], **kw)


def bash(script, **kw):
    return Cmd(["bash", "-c", script], **kw)


def _mkfs(v):
    lbl = v.label
    dev = v.device
    return {
        "ext4": ["mkfs.ext4", "-F"] + (["-L", lbl[:16]] if lbl else []) + [dev],
        "btrfs": ["mkfs.btrfs", "-f"] + (["-L", lbl] if lbl else []) + [dev],
        "xfs": ["mkfs.xfs", "-f"] + (["-L", lbl[:12]] if lbl else []) + [dev],
        "f2fs": ["mkfs.f2fs", "-f"] + (["-l", lbl] if lbl else []) + [dev],
        "vfat": ["mkfs.fat", "-F", "32"] + (["-n", lbl.upper()[:11]] if lbl else []) + [dev],
        "swap": ["mkswap"] + (["-L", lbl] if lbl else []) + [dev],
    }[v.fs]


def _mount(dev, target, opts="", mkdir=True):
    argv = ["mount"] + (["--mkdir"] if mkdir else []) + (["-o", opts] if opts else [])
    return Cmd(argv + [dev, target])


def hooks(sel, lay):
    h = ["base", "systemd", "autodetect", "microcode", "modconf"]
    if sel.kms_hook:
        h.append("kms")
    h += ["keyboard", "sd-vconsole", "block"]
    if lay.root.encrypt:
        h.append("sd-encrypt")
    h += ["filesystems", "fsck"]
    return f"HOOKS=({' '.join(h)})\n"


def root_params(lay, runner):
    r = lay.root
    out = []
    if r.encrypt:
        luks = runner.capture(["cryptsetup", "luksUUID", r.node])
        out += [f"rd.luks.name={luks}={r.mapper}", f"root=/dev/mapper/{r.mapper}"]
    else:
        out.append("root=UUID=" + runner.capture(["blkid", "-s", "UUID", "-o", "value", r.device]))
    if r.subvols:
        out.append("rootflags=subvol=@")
    out.append("rw")
    return " ".join(out)


SNAPPER_ROOT = """SUBVOLUME="/"
FSTYPE="btrfs"
QGROUP=""
SPACE_LIMIT="0.5"
FREE_LIMIT="0.2"
ALLOW_USERS=""
ALLOW_GROUPS="wheel"
SYNC_ACL="yes"
BACKGROUND_COMPARISON="yes"
NUMBER_CLEANUP="yes"
NUMBER_MIN_AGE="1800"
NUMBER_LIMIT="10"
NUMBER_LIMIT_IMPORTANT="10"
TIMELINE_CREATE="yes"
TIMELINE_CLEANUP="yes"
TIMELINE_MIN_AGE="1800"
TIMELINE_LIMIT_HOURLY="5"
TIMELINE_LIMIT_DAILY="7"
TIMELINE_LIMIT_WEEKLY="0"
TIMELINE_LIMIT_MONTHLY="0"
TIMELINE_LIMIT_YEARLY="0"
EMPTY_PRE_POST_CLEANUP="yes"
EMPTY_PRE_POST_MIN_AGE="1800"
"""


def iwd_filename(ssid):
    import re
    return ssid if re.fullmatch(r"[A-Za-z0-9 _-]+", ssid) else "=" + ssid.encode().hex()


def build(cfg, hw, disks, local_mirror=None):
    """Raises layout.LayoutError when the disk setup is impossible.
    local_mirror: a caching mirror for test VMs (tools/pkgproxy.py); used for the
    install, never left in the new system's mirror list."""
    lay = L.resolve(cfg, hw, disks)
    boot = L.resolve_bootloader(cfg, hw, lay)
    sel = P.compute(cfg, hw, lay, boot)
    disk_by_path = {d.path: d for d in disks}
    steps = []

    # ---------------------------------------------------------- 1. prepare
    prep = [
        bash("for i in $(seq 90); do systemctl is-active -q pacman-init.service && exit 0; "
             "sleep 1; done; exit 1", optional=True, sim=0.3),
        Cmd(["timedatectl", "set-ntp", "true"], optional=True),
        bash("for i in $(seq 45); do [ \"$(timedatectl show -p NTPSynchronized --value)\" = yes ] "
             "&& exit 0; sleep 1; done; exit 1", optional=True, sim=0.3),
    ]
    m = cfg["mirrors"]
    if m["mode"] == "auto":
        argv = ["timeout", "150", "reflector", "--protocol", "https", "--latest", "20",
                "--sort", "rate", "--connection-timeout", "5", "--download-timeout", "5",
                "--save", "/etc/pacman.d/mirrorlist"]
        if m["countries"]:
            argv[3:3] = ["--country", ",".join(m["countries"])]
        prep.append(Cmd(argv, optional=True, sim=1.0))
    elif m["mode"] == "custom":
        prep.append(Write("/etc/pacman.d/mirrorlist",
                          "".join(f"Server = {u.strip()}\n" for u in m["custom"] if u.strip())))
    if local_mirror:
        prep.append(Cmd(["sed", "-i", f"1i Server = {local_mirror}/$repo/os/$arch", "/etc/pacman.d/mirrorlist"]))
    prep.append(Cmd(["sed", "-i", "-E", f"s/^#?ParallelDownloads.*/ParallelDownloads = {int(m['parallel'])}/",
                     "/etc/pacman.conf"]))
    if sel.multilib:
        prep.append(Cmd(["sed", "-i", r"/^#\[multilib\]/,/^#Include/ s/^#//", "/etc/pacman.conf"]))
    prep.append(Cmd(["pacman", "-Sy", "--noconfirm", "--needed", "archlinux-keyring"], sim=1.5))
    prep.append(Cmd(["pacman", "-Sp", "--noconfirm", *sel.packages], quiet=True, sim=0.5))
    steps.append(Step("prepare", "Getting ready", 6, prep))

    # ---------------------------------------------------------- 2. disks
    dsk = []
    for s in lay.shrink:
        start_s = s.start // s.log_sec
        end_s = (s.start + s.new_size) // s.log_sec - 1
        dsk += [
            Cmd(["ntfsresize", "--no-action", "--no-progress-bar", "--size", str(s.fs_size), s.node], sim=1.0),
            Cmd(["ntfsresize", "--no-progress-bar", "--size", str(s.fs_size), s.node], stdin="y\n", sim=3.0),
            Cmd(["sgdisk", f"--delete={s.number}", f"--new={s.number}:{start_s}:{end_s}",
                 f"--typecode={s.number}:{s.type_guid}", f"--partition-guid={s.number}:{s.uuid}",
                 f"--change-name={s.number}:{s.name}", s.disk]),
        ]
    for d in lay.wipe:
        dsk += [Cmd(["wipefs", "--all", "--force", d]), Cmd(["sgdisk", "--zap-all", d]),
                Cmd(["sgdisk", "--clear", d])]
    for disk in sorted({d for d, _, _ in lay.delete}):
        dsk.append(Cmd(["sgdisk"] + [f"--delete={n}" for d, n, _ in lay.delete if d == disk] + [disk]))
    for disk in sorted({c.disk for c in lay.create}):
        sec = disk_by_path[disk].log_sec
        args = []
        for c in [c for c in lay.create if c.disk == disk]:
            args += [f"--new={c.number}:{c.start // sec}:{c.end // sec - 1}",
                     f"--typecode={c.number}:{c.typecode}", f"--change-name={c.number}:{c.name}"]
        dsk.append(Cmd(["sgdisk"] + args + [disk]))
    for disk in lay.touched_disks():
        dsk += [Cmd(["partprobe", disk]), Cmd(["udevadm", "settle"])]
    for c in lay.create:
        if c.typecode != "ef02":
            dsk.append(Cmd(["wipefs", "--all", "--force", c.node]))
    steps.append(Step("disks", "Preparing your disks", 4, dsk))

    # ---------------------------------------------------------- 3. filesystems
    pw = cfg["disk"]["encryption"]["passphrase"]
    fsa = []
    for v in lay.encrypted():
        fsa += [Cmd(["cryptsetup", "luksFormat", "--type", "luks2", "--batch-mode",
                     "--key-file=-", v.node], stdin=pw, sim=2.0),
                Cmd(["cryptsetup", "open", "--key-file=-", v.node, v.mapper], stdin=pw, sim=1.0)]
    for v in lay.volumes:
        if v.format and v.fs != "bios_grub":
            fsa.append(Cmd(_mkfs(v)))
    root = lay.root
    if root.subvols:
        fsa.append(_mount(root.device, MNT, mkdir=False))
        fsa += [Cmd(["btrfs", "subvolume", "create", f"{MNT}/{name}"]) for name, _ in root.subvols]
        fsa.append(Cmd(["umount", MNT]))
        for name, mp in sorted(root.subvols, key=lambda x: (x[1] != "/", x[1].count("/"), x[1])):
            opts = ",".join(x for x in [f"subvol={name}", root.options] if x)
            fsa.append(_mount(root.device, MNT + ("" if mp == "/" else mp), opts, mkdir=mp != "/"))
    else:
        fsa.append(_mount(root.device, MNT, root.options, mkdir=False))
    for v in lay.mount_order():
        if v is not root:
            fsa.append(_mount(v.device, MNT + v.mount, v.options))
    for v in lay.volumes:
        if v.fs == "swap" or (v.mount == "[SWAP]"):
            fsa.append(Cmd(["swapon", v.device]))
    swapfile = None
    if cfg["swap"]["mode"] == "swapfile":
        mib = int(float(cfg["swap"]["size_gb"]) * 1024)
        if root.fs == "btrfs":
            swapfile = "/swap/swapfile" if any(mp == "/swap" for _, mp in root.subvols) else "/swapfile"
            fsa.append(Cmd(["btrfs", "filesystem", "mkswap-file", "--size", f"{mib}m", "--uuid", "clear",
                            MNT + swapfile], sim=1.0))
        else:
            swapfile = "/swapfile"
            fsa.append(Cmd(["mkswap", "--size", f"{mib}M", "--file", MNT + swapfile], sim=1.0))
    steps.append(Step("filesystems", "Creating filesystems", 4, fsa))

    # ---------------------------------------------------------- 4. packages
    kb = C.KEYBOARDS[cfg["locale"]["keyboard"]]
    pkg = [
        Write(f"{MNT}/etc/vconsole.conf", f"KEYMAP={kb[1]}\n"),
        Write(f"{MNT}/etc/mkinitcpio.conf.d/10-linusetup.conf", hooks(sel, lay)),
        # stdbuf: pacman block-buffers output into a pipe, so the screen would show a
        # stale line for minutes; line-buffered, every package and hook shows up live.
        Cmd(["stdbuf", "-oL", "-eL", "pacstrap", "-K", MNT, *sel.packages], sim=8.0, progress="pacman"),
    ]
    steps.append(Step("packages", "Installing Arch Linux", 55, pkg))

    # ---------------------------------------------------------- 5. configure
    lang = cfg["locale"]["language"]
    locs = [lang] + [l for l in cfg["locale"]["extra"] if l != lang]
    host = cfg["hostname"]
    conf = [
        Cmd(["genfstab", "-U", MNT], stdout_to=f"{MNT}/etc/fstab"),
    ] + ([Cmd(["sed", "-i", f"\\#{local_mirror}#d", f"{MNT}/etc/pacman.d/mirrorlist"])] if local_mirror else []) + [
        Write(f"{MNT}/etc/hostname", host + "\n"),
        Write(f"{MNT}/etc/hosts", f"127.0.0.1 localhost\n::1 localhost\n127.0.1.1 {host}.localdomain {host}\n"),
        Write(f"{MNT}/etc/locale.gen", "# Generated by LinuSetup\n" + "".join(f"{l} UTF-8\n" for l in locs)),
        Write(f"{MNT}/etc/locale.conf", f"LANG={lang}\n"),
        chroot("locale-gen"),
        chroot("ln", "-sf", f"/usr/share/zoneinfo/{cfg['timezone']}", "/etc/localtime"),
        chroot("hwclock", "--systohc", optional=True),
        Cmd(["sed", "-i", "-E", f"s/^#?ParallelDownloads.*/ParallelDownloads = {int(m['parallel'])}/",
             f"{MNT}/etc/pacman.conf"]),
    ]
    if swapfile:
        conf.append(Write(f"{MNT}/etc/fstab", f"{swapfile} none swap defaults 0 0\n", append=True))
    if m["color"]:
        conf.append(Cmd(["sed", "-i", "s/^#Color/Color/", f"{MNT}/etc/pacman.conf"]))
    if sel.multilib:
        conf.append(Cmd(["sed", "-i", r"/^#\[multilib\]/,/^#Include/ s/^#//", f"{MNT}/etc/pacman.conf"]))
    if sel.graphical:
        opts = f'        Option "XkbOptions" "{kb[4]}"\n' if kb[4] else ""
        conf.append(Write(f"{MNT}/etc/X11/xorg.conf.d/00-keyboard.conf",
                          'Section "InputClass"\n        Identifier "system-keyboard"\n'
                          '        MatchIsKeyboard "on"\n'
                          f'        Option "XkbLayout" "{kb[2]}"\n        Option "XkbVariant" "{kb[3]}"\n'
                          + opts + "EndSection\n"))
        if "kde" in cfg["profiles"] and (kb[2] != "us" or kb[3]):
            conf.append(Write(f"{MNT}/etc/skel/.config/kxkbrc",
                              f"[Layout]\nLayoutList={kb[2]}\nVariantList={kb[3] or ','.join('' for _ in kb[2].split(','))}\n"
                              f"Use=true\n" + (f"Options={kb[4]}\nResetOldOptions=true\n" if kb[4] else "")))
    # encrypted volumes other than / are unlocked at boot with a key file kept on /
    for v in lay.encrypted():
        if v is root:
            continue
        key = f"/etc/cryptsetup-keys.d/{v.mapper}.key"
        conf += [
            Cmd(["install", "-d", "-m", "0700", f"{MNT}/etc/cryptsetup-keys.d"]),
            Cmd(["dd", "if=/dev/urandom", f"of={MNT}{key}", "bs=512", "count=8", "status=none"]),
            Cmd(["chmod", "0400", f"{MNT}{key}"]),
            Cmd(["cryptsetup", "luksAddKey", "--key-file=-", v.node, f"{MNT}{key}"], stdin=pw, sim=2.0),
            Write(f"{MNT}/etc/crypttab", (lambda v=v, key=key: lambda r: (
                f"{v.mapper} UUID={r.capture(['cryptsetup', 'luksUUID', v.node])} {key} luks\n"))(),
                append=True),
        ]
    if cfg["swap"]["mode"] == "zram":
        size = int(float(cfg["swap"]["size_gb"]) * 1024)
        conf.append(Write(f"{MNT}/etc/systemd/zram-generator.conf",
                          f"[zram0]\nzram-size = min(ram, {size})\ncompression-algorithm = zstd\n"))
    net = cfg["network"]
    if net["manager"] == "networkd":
        conf += [Write(f"{MNT}/etc/systemd/network/20-wired.network", "[Match]\nType=ether\n\n[Network]\nDHCP=yes\n"),
                 Write(f"{MNT}/etc/systemd/network/25-wireless.network",
                       "[Match]\nType=wlan\n\n[Network]\nDHCP=yes\nIgnoreCarrierLoss=3s\n")]
    wifi = net.get("wifi")
    if wifi and net["copy_wifi"] and wifi.get("ssid"):
        ssid, psk = wifi["ssid"], wifi.get("psk") or ""
        if net["manager"] == "networkmanager":
            sec = f"\n[wifi-security]\nkey-mgmt=wpa-psk\npsk={psk}\n" if psk else ""
            conf.append(Write(f"{MNT}/etc/NetworkManager/system-connections/{iwd_filename(ssid)}.nmconnection",
                              f"[connection]\nid={ssid}\ntype=wifi\n\n[wifi]\nmode=infrastructure\nssid={ssid}\n"
                              f"{sec}\n[ipv4]\nmethod=auto\n\n[ipv6]\nmethod=auto\n", mode=0o600, secret=True))
        elif net["manager"] == "networkd":
            ext = "psk" if psk else "open"
            conf.append(Write(f"{MNT}/var/lib/iwd/{iwd_filename(ssid)}.{ext}",
                              f"[Security]\nPassphrase={psk}\n" if psk else "", mode=0o600, secret=True))
    if root.fs == "btrfs" and cfg["disk"]["btrfs"].get("snapshots"):
        conf += [Write(f"{MNT}/etc/snapper/configs/root", SNAPPER_ROOT, mode=0o640),
                 Write(f"{MNT}/etc/conf.d/snapper", 'SNAPPER_CONFIGS="root"\n')]
    conf.append(chroot("mkinitcpio", "-P", sim=2.0))
    steps.append(Step("configure", "Configuring the system", 8, conf))

    # ---------------------------------------------------------- 6. boot loader
    params = cfg["kernel_params"].strip()
    timeout = int(cfg["bootloader"]["timeout"])
    if boot == "systemd-boot":
        bl = [chroot("bootctl", "install", "--esp-path=/boot"),
              Write(f"{MNT}/boot/loader/loader.conf",
                    f"default arch-{cfg['kernels'][0]}.conf\ntimeout {timeout}\nconsole-mode max\neditor no\n")]
        for k in cfg["kernels"]:
            for fb in ("", "-fallback"):
                bl.append(Write(
                    f"{MNT}/boot/loader/entries/arch-{k}{fb}.conf",
                    (lambda k=k, fb=fb: lambda r: (
                        f"title   Arch Linux ({k}{', fallback' if fb else ''})\n"
                        f"linux   /vmlinuz-{k}\ninitrd  /initramfs-{k}{fb}.img\n"
                        f"options {root_params(lay, r)} {params}\n".replace(" \n", "\n")))()))
    else:
        esp = lay.esp

        def grub_defaults(r):
            luks = ""
            if root.encrypt:
                luks = f"rd.luks.name={r.capture(['cryptsetup', 'luksUUID', root.node])}={root.mapper}"
            lines = ["", "# --- LinuSetup ---", f"GRUB_TIMEOUT={timeout}",
                     f'GRUB_CMDLINE_LINUX_DEFAULT="{params}"', f'GRUB_CMDLINE_LINUX="{luks}"']
            if cfg["bootloader"]["os_prober"] and lay.dual_boot:
                lines.append("GRUB_DISABLE_OS_PROBER=false")
            return "\n".join(lines) + "\n"
        bl = [Write(f"{MNT}/etc/default/grub", grub_defaults, append=True)]
        if hw.uefi:
            bl.append(chroot("grub-install", "--target=x86_64-efi", f"--efi-directory={esp.mount}",
                             "--bootloader-id=LinuSetup"))
            if lay.esp_fresh:
                bl.append(chroot("grub-install", "--target=x86_64-efi", f"--efi-directory={esp.mount}",
                                 "--removable"))
        else:
            bl.append(chroot("grub-install", "--target=i386-pc", lay.bios_grub_disk))
        bl.append(chroot("grub-mkconfig", "-o", "/boot/grub/grub.cfg", sim=1.0))
    steps.append(Step("bootloader", "Installing the boot loader", 4, bl))

    # ---------------------------------------------------------- 7. users
    usr = []
    for src, dest, mode in sel.skel:
        usr += [Cmd(["install", "-Dm", f"{mode:o}", f"{MNT}{src}", f"{MNT}/etc/skel/{dest}"], optional=True)]
    autologin = next((u for u in cfg["users"] if u.get("autologin")), None)
    if autologin and sel.greeter == "lightdm":
        usr.append(chroot("groupadd", "-r", "-f", "autologin"))
    for u in cfg["users"]:
        groups = (["wheel"] if u.get("sudo") else []) + (sel.user_groups if u.get("sudo") else []) \
            + (["autologin"] if u is autologin and sel.greeter == "lightdm" else [])
        argv = ["useradd", "-m", "-s", C.SHELLS[u.get("shell", "bash")][0]]
        if groups:
            argv += ["-G", ",".join(groups)]
        if u.get("fullname"):
            argv += ["-c", u["fullname"]]
        usr += [chroot(*argv, u["username"]),
                chroot("chpasswd", stdin=f"{u['username']}:{u['password']}\n")]
    if any(u.get("sudo") for u in cfg["users"]):
        usr.append(Write(f"{MNT}/etc/sudoers.d/10-wheel", "%wheel ALL=(ALL:ALL) ALL\n", mode=0o440))
    if cfg["root"]["password"]:
        usr.append(chroot("chpasswd", stdin=f"root:{cfg['root']['password']}\n"))
    elif cfg["root"]["lock"]:
        usr.append(chroot("passwd", "-l", "root"))
    steps.append(Step("users", "Creating your account", 3, usr))

    # ---------------------------------------------------------- 8. desktop & services
    svc = []
    if sel.greeter == "sddm" and "kde" in cfg["profiles"]:
        svc.append(Write(f"{MNT}/etc/sddm.conf.d/10-theme.conf", "[Theme]\nCurrent=breeze\n"))
    if autologin:
        name = autologin["username"]
        if sel.greeter == "sddm":
            sess = next((P.SDDM_SESSIONS[p] for p in cfg["profiles"] if p in P.SDDM_SESSIONS), "")
            svc.append(Write(f"{MNT}/etc/sddm.conf.d/20-autologin.conf",
                             f"[Autologin]\nUser={name}\n" + (f"Session={sess}\n" if sess else "")))
        elif sel.greeter == "gdm":
            svc.append(Write(f"{MNT}/etc/gdm/custom.conf",
                             f"[daemon]\nAutomaticLoginEnable=True\nAutomaticLogin={name}\n"))
        elif sel.greeter == "lightdm":
            svc.append(Write(f"{MNT}/etc/lightdm/lightdm.conf.d/50-autologin.conf",
                             f"[Seat:*]\nautologin-user={name}\n"))
    if cfg["firewall"] == "ufw":
        svc.append(Cmd(["sed", "-i", "s/^ENABLED=no/ENABLED=yes/", f"{MNT}/etc/ufw/ufw.conf"]))
    svc.append(chroot("systemctl", "enable", *sel.services))
    for s in cfg["services"]:
        svc.append(chroot("systemctl", "enable", s, optional=True))
    steps.append(Step("services", "Setting up your desktop", 3, svc))

    # ---------------------------------------------------------- 9. optional extras
    admin = next((u for u in cfg["users"] if u.get("sudo")), None)
    if cfg["aur_helper"] != "none" and admin:
        h, user = cfg["aur_helper"], admin["username"]
        tmp = f"{MNT}/etc/sudoers.d/99-linusetup-aur"
        steps.append(Step("aur", f"Installing {h} (AUR helper)", 6, [
            Write(tmp, f"{user} ALL=(ALL:ALL) NOPASSWD: ALL\n", mode=0o440),
            chroot("sudo", "-u", user, "bash", "-c",
                   f"cd /tmp && rm -rf {h}-bin && git clone --depth 1 https://aur.archlinux.org/{h}-bin.git "
                   f"&& cd {h}-bin && makepkg -si --noconfirm", optional=True, sim=3.0),
        ], always=[Cmd(["rm", "-f", tmp])]))
    if cfg["flatpak"]:
        steps.append(Step("flatpak", "Adding Flathub", 1, [
            chroot("flatpak", "remote-add", "--if-not-exists", "flathub",
                   "https://dl.flathub.org/repo/flathub.flatpakrepo", optional=True)]))
    if cfg["custom_commands"].strip():
        script = "/root/linusetup-post.sh"
        steps.append(Step("custom", "Running your custom commands", 2, [
            Write(MNT + script, "#!/bin/bash\nset -e\n" + cfg["custom_commands"].strip() + "\n", mode=0o700),
            chroot("bash", script, optional=True, sim=1.0),
        ], always=[Cmd(["rm", "-f", MNT + script])]))

    # ---------------------------------------------------------- 10. finish
    fin = [CopyLog(f"{MNT}/var/log/linusetup-install.log")]
    if net["manager"] == "networkd":
        fin.append(Cmd(["ln", "-sf", "../run/systemd/resolve/stub-resolv.conf", f"{MNT}/etc/resolv.conf"]))
    fin += [Cmd(["sync"]), Cmd(["swapoff", "-a"], optional=True), Cmd(["umount", "-R", MNT])]
    fin += [Cmd(["cryptsetup", "close", v.mapper], optional=True) for v in reversed(lay.encrypted())]
    steps.append(Step("finish", "Finishing up", 2, fin))

    cleanup = [Cmd(["swapoff", "-a"], optional=True), Cmd(["umount", "-R", MNT], optional=True)] + \
        [Cmd(["cryptsetup", "close", v.mapper], optional=True) for v in reversed(lay.encrypted())]
    return Plan(steps, cleanup, lay, boot, sel)
