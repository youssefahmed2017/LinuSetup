"""User choices and their validation."""
import re
from dataclasses import dataclass, field

USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
HOSTNAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$")
RESERVED_USERNAMES = {"root", "daemon", "bin", "sys", "nobody", "sddm", "docker"}
KEYMAPS = ("us", "uk", "de", "fr", "es", "it", "pt-latin9", "br-abnt2", "ru", "ara")


@dataclass
class InstallConfig:
    disk: str = ""
    presets: list = field(default_factory=list)
    fullname: str = ""
    username: str = ""
    hostname: str = "linusetup"
    password: str = ""
    timezone: str = "UTC"
    keymap: str = "us"
    locale: str = "en_US.UTF-8"

    @classmethod
    def from_dict(cls, d: dict):
        known = {k: d[k] for k in cls.__dataclass_fields__ if k in d}
        return cls(**known)


def validate(cfg: InstallConfig, usable_disk_paths, valid_presets, valid_timezones):
    """Raise ValueError with a user-readable message on the first problem."""
    if cfg.disk not in set(usable_disk_paths):
        raise ValueError("The selected disk is not available.")
    if not set(cfg.presets) <= set(valid_presets):
        raise ValueError("Unknown preset selected.")
    if not USERNAME_RE.match(cfg.username) or cfg.username in RESERVED_USERNAMES:
        raise ValueError("Username must be lowercase letters, digits, - or _ "
                         "and not a reserved name.")
    if not HOSTNAME_RE.match(cfg.hostname):
        raise ValueError("Computer name may only contain letters, digits and dashes.")
    if len(cfg.password) < 4:
        raise ValueError("Password is too short.")
    if "\n" in cfg.password or ":" in cfg.fullname or "\n" in cfg.fullname or "," in cfg.fullname:
        raise ValueError("Name or password contains characters that are not allowed.")
    if cfg.timezone not in valid_timezones:
        raise ValueError("Unknown timezone.")
    if cfg.keymap not in KEYMAPS:
        raise ValueError("Unknown keyboard layout.")
    if cfg.locale != "en_US.UTF-8":
        raise ValueError("Only en_US.UTF-8 is supported in this version.")
