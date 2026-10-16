"""Whole-config validation. Returns issues grouped by UI section, plus what the
installer resolved (layout, boot loader, drivers...) for the review screen."""
import re
import zoneinfo

from . import catalog as C
from . import layout as L
from . import packages as P
from . import plan as PL

USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
PKG_RE = re.compile(r"^[a-z0-9@._+-]+$")
SERVICE_RE = re.compile(r"^[a-zA-Z0-9@._:-]+$")
MIRROR_RE = re.compile(r"^https?://\S+/\$repo/os/\$arch/?$")
RESERVED = {"root", "bin", "daemon", "sys", "adm", "nobody", "sddm", "gdm", "lightdm", "docker",
            "polkitd", "dbus", "systemd-network", "http", "ftp", "mail", "git", "uucp"}

_TZ = None


def timezones():
    global _TZ
    if _TZ is None:
        _TZ = sorted(z for z in zoneinfo.available_timezones() if "/" in z or z == "UTC")
    return _TZ


class Issues:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, section, msg):
        self.errors.append(dict(section=section, message=msg))

    def warn(self, section, msg):
        self.warnings.append(dict(section=section, message=msg))


def check(cfg, hw, disks, online=True, real=False):
    i = Issues()
    _locale(cfg, i)
    _mirrors(cfg, i)
    _users(cfg, i)
    _system(cfg, hw, i)
    _desktop(cfg, hw, i)
    _software(cfg, i)
    result = dict(layout=None, preview={}, bootloader=None, greeter=None, drivers=[],
                  package_count=0, multilib=False, steps=[], dual_boot=False)
    _disk_options(cfg, i)
    if not any(e["section"] == "disk" for e in i.errors):
        try:
            plan = PL.build(cfg, hw, disks)
            lay = plan.layout
            result.update(layout=lay.summary(), preview=lay.preview(disks), bootloader=plan.bootloader,
                          greeter=plan.selection.greeter, drivers=plan.selection.drivers,
                          package_count=len(plan.selection.packages), packages=plan.selection.packages,
                          multilib=plan.selection.multilib, dual_boot=lay.dual_boot,
                          steps=[dict(id=s.id, label=s.label) for s in plan.steps])
            if lay.shrink:
                i.warn("disk", "Before shrinking Windows, turn off Fast Startup and shut Windows down fully "
                               "(not restart). Back up anything important: resizing is always a risk.")
            if lay.dual_boot and plan.bootloader == "grub" and not cfg["bootloader"]["os_prober"]:
                i.warn("boot", "Windows won't appear in the boot menu because 'Detect other systems' is off.")
        except L.LayoutError as e:
            section = "boot" if "systemd-boot" in str(e) else "disk"
            i.err(section, str(e))
        except (KeyError, ValueError, TypeError):
            if not i.errors:        # unknown ids are reported above; anything else is a bug
                raise
    if not online:
        (i.err if real else i.warn)("network", "No internet connection. Packages are downloaded during "
                                               "the install, so connect first.")
    if hw.ram_gb and hw.ram_gb < 2:
        i.warn("system", f"Only {hw.ram_gb} GB of memory. Desktops need at least 2 GB to be pleasant.")
    return dict(errors=i.errors, warnings=i.warnings, **result)


def _locale(cfg, i):
    loc = cfg["locale"]
    known = set(C.locales())
    if loc["language"] not in known:
        i.err("locale", f"Unknown language '{loc['language']}'.")
    for l in loc["extra"]:
        if l not in known:
            i.err("locale", f"Unknown locale '{l}'.")
    if loc["keyboard"] not in C.KEYBOARDS:
        i.err("locale", "Choose a keyboard layout.")
    if cfg["timezone"] not in timezones():
        i.err("locale", f"Unknown timezone '{cfg['timezone']}'.")


def _mirrors(cfg, i):
    m = cfg["mirrors"]
    if m["mode"] not in ("auto", "iso", "custom"):
        i.err("mirrors", "Unknown mirror option.")
    bad = [c for c in m["countries"] if c not in C.COUNTRIES]
    if bad:
        i.err("mirrors", f"Unknown mirror countries: {', '.join(bad)}.")
    if m["mode"] == "custom":
        urls = [u.strip() for u in m["custom"] if u.strip()]
        if not urls:
            i.err("mirrors", "Add at least one mirror URL, or pick another option.")
        for u in urls:
            if not MIRROR_RE.match(u):
                i.err("mirrors", f"'{u}' should look like https://host/archlinux/$repo/os/$arch")
    if not 1 <= int(m["parallel"]) <= 20:
        i.err("mirrors", "Parallel downloads must be between 1 and 20.")


def _disk_options(cfg, i):
    d = cfg["disk"]
    if d["mode"] not in ("guided", "manual"):
        i.err("disk", "Unknown disk mode.")
    if d["mode"] == "guided":
        if d["scope"] not in ("wipe", "free", "shrink"):
            i.err("disk", "Unknown disk option.")
        if d["fs"] not in C.FILESYSTEMS:
            i.err("disk", "Choose a filesystem.")
    enc = d["encryption"]
    uses_enc = enc["enabled"] if d["mode"] == "guided" else (
        any(x.get("encrypt") for x in d["manual"]["new"] + d["manual"]["existing"]))
    if uses_enc:
        if not enc["passphrase"]:
            i.err("disk", "Set an encryption passphrase.")
        elif len(enc["passphrase"]) < 8:
            i.warn("disk", "The encryption passphrase is short. 8+ characters are recommended.")
        if "\n" in enc["passphrase"]:
            i.err("disk", "The passphrase can't contain line breaks.")
    b = d["btrfs"]
    if b["compress"] not in ("zstd", "lzo", "none"):
        i.err("disk", "Unknown compression.")
    if b["snapshots"] and not b["subvolumes"]:
        i.err("disk", "Snapshots need Btrfs subvolumes turned on.")
    s = cfg["swap"]
    if s["mode"] not in ("zram", "swapfile", "partition", "none"):
        i.err("system", "Unknown swap option.")
    elif s["mode"] != "none" and not 0.25 <= float(s["size_gb"]) <= 128:
        i.err("system", "Swap size must be between 0.25 and 128 GB.")
    if s["mode"] == "partition" and d["mode"] == "manual":
        i.err("system", "With manual partitioning, add a swap partition in the disk editor and set swap "
                        "here to 'None', or use zram or a swap file.")
    root_fs = d["fs"] if d["mode"] == "guided" else next(
        (x.get("fs") for x in d["manual"]["new"] + d["manual"]["existing"] if x.get("mount") == "/"), "")
    if s["mode"] == "swapfile" and root_fs == "f2fs":
        i.err("system", "F2FS doesn't support swap files. Use zram or a swap partition.")
    if b["snapshots"] and root_fs != "btrfs":
        i.warn("disk", "Snapshots only work with Btrfs; they will be skipped.")


def _users(cfg, i):
    users = cfg["users"]
    names = set()
    for u in users:
        n = u["username"]
        label = n or "a user"
        if not USERNAME_RE.match(n):
            i.err("users", f"Username '{n}' must start with a lowercase letter and use only a-z, 0-9, - and _.")
        elif n in RESERVED:
            i.err("users", f"'{n}' is reserved by the system. Pick another username.")
        if n in names:
            i.err("users", f"Username '{n}' is used twice.")
        names.add(n)
        if not u["password"]:
            i.err("users", f"Set a password for {label}.")
        if "\n" in u["password"]:
            i.err("users", f"The password for {label} can't contain line breaks.")
        if re.search(r"[:,\n]", u["fullname"]):
            i.err("users", f"The full name of {label} can't contain : or , characters.")
        if u["shell"] not in C.SHELLS:
            i.err("users", f"Unknown shell for {label}.")
    if not users and not cfg["root"]["password"]:
        i.err("users", "Create a user account (or set a root password).")
    elif not any(u["sudo"] for u in users) and not cfg["root"]["password"]:
        i.err("users", "Nobody could administer the system: make a user an administrator "
                       "or set a root password.")
    if sum(1 for u in users if u["autologin"]) > 1:
        i.err("users", "Only one user can log in automatically.")
    if "\n" in cfg["root"]["password"]:
        i.err("users", "The root password can't contain line breaks.")
    if cfg["aur_helper"] != "none" and not any(u["sudo"] for u in users):
        i.err("software", "Installing an AUR helper needs an administrator account.")
    if cfg["aur_helper"] not in C.AUR_HELPERS:
        i.err("software", "Unknown AUR helper.")


def _system(cfg, hw, i):
    if not HOSTNAME_RE.match(cfg["hostname"]):
        i.err("system", "Computer name may use letters, digits and dashes (not at the start or end).")
    b = cfg["bootloader"]
    if b["type"] not in ("auto", "systemd-boot", "grub"):
        i.err("boot", "Unknown boot loader.")
    if not 0 <= int(b["timeout"]) <= 60:
        i.err("boot", "Boot menu timeout must be 0 to 60 seconds.")
    if not cfg["kernels"]:
        i.err("boot", "Choose at least one kernel.")
    for k in cfg["kernels"]:
        if k not in C.KERNELS:
            i.err("boot", f"Unknown kernel '{k}'.")
    if re.search(r'["\n\\]', cfg["kernel_params"]):
        i.err("boot", "Kernel parameters can't contain quotes, backslashes or line breaks.")
    if cfg["network"]["manager"] not in C.NETWORK:
        i.err("network", "Unknown network option.")
    if cfg["firewall"] not in C.FIREWALLS:
        i.err("system", "Unknown firewall.")
    for s in cfg["services"]:
        if not SERVICE_RE.match(s):
            i.err("system", f"'{s}' is not a valid service name.")
    if cfg["finish"] not in ("none", "reboot", "poweroff"):
        i.err("system", "Unknown finish action.")


def _desktop(cfg, hw, i):
    if not cfg["profiles"]:
        i.err("desktop", "Choose a desktop, or 'Minimal' for none.")
    for p in cfg["profiles"]:
        if p not in C.PROFILES:
            i.err("desktop", f"Unknown profile '{p}'.")
    if cfg["greeter"] not in list(C.GREETERS) + ["auto"]:
        i.err("desktop", "Unknown login screen.")
    if cfg["graphics"] not in C.GRAPHICS:
        i.err("desktop", "Unknown graphics driver.")
    if cfg["audio"] not in C.AUDIO:
        i.err("desktop", "Unknown sound option.")
    if any(p not in C.PROFILES for p in cfg["profiles"]):
        return
    graphical = P.is_graphical(cfg)
    greeter = P.resolve_greeter(cfg)
    if not graphical:
        i.warn("desktop", "No graphical desktop is selected: the new system will boot to a text console (TTY).")
    if graphical and greeter == "none":
        i.warn("desktop", "No login screen: you'll log in on the console and start the desktop yourself.")
    if any(u["autologin"] for u in cfg["users"]) and greeter in ("none", "cosmic-greeter"):
        i.warn("users", "Automatic login needs SDDM, GDM or LightDM; it will be skipped.")
    drivers = P.resolve_drivers(cfg, hw)
    if "nvidia-open" in drivers:
        i.warn("desktop", "The NVIDIA open driver supports GTX 16xx, RTX and newer. For older cards "
                          "choose 'nouveau' under Graphics.")


def _software(cfg, i):
    for s in cfg["software"]:
        if s not in C.SOFTWARE_INDEX:
            i.err("software", f"Unknown software '{s}'.")
    for p in cfg["extra_packages"]:
        if not PKG_RE.match(p):
            i.err("software", f"'{p}' is not a valid package name.")
