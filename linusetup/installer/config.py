"""The install configuration: one JSON document, the same for the GUI, a saved
config file and an unattended install. Defaults live here; validation is in
validate.py so it can see hardware and disks too."""
import copy
import json

VERSION = 1

# Keys holding secrets. Exported configs never contain them.
SECRET_PATHS = (("root", "password"), ("disk", "encryption", "passphrase"),
                ("network", "wifi"))


def default_config():
    return {
        "version": VERSION,
        "locale": {"language": "en_US.UTF-8", "extra": [], "keyboard": "us"},
        "timezone": "UTC",
        "ntp": True,
        "mirrors": {"mode": "auto", "countries": [], "custom": [], "parallel": 5,
                    "multilib": False, "color": True},
        "disk": {
            "mode": "guided",               # guided | manual
            "device": "",                   # guided: target disk
            "scope": "wipe",                # guided: wipe | free | shrink
            "shrink": {"partition": "", "free_gb": 0},
            "fs": "ext4",
            "home": {"separate": False, "root_gb": 60},
            "btrfs": {"subvolumes": True, "compress": "zstd", "snapshots": False},
            "encryption": {"enabled": False, "passphrase": ""},
            "manual": {"wipe": [], "delete": [], "new": [], "existing": []},
        },
        "swap": {"mode": "zram", "size_gb": 4},     # zram | swapfile | partition | none
        "bootloader": {"type": "auto", "timeout": 3, "os_prober": True},
        "kernels": ["linux"],
        "kernel_params": "loglevel=3 quiet",
        "headers": False,
        "network": {"manager": "networkmanager", "copy_wifi": True, "wifi": None},
        "hostname": "archlinux",
        "root": {"password": "", "lock": True},
        "users": [],
        "profiles": ["kde"],
        "greeter": "auto",
        "graphics": "auto",
        "vm_tools": True,
        "audio": "pipewire",
        "bluetooth": True,
        "printing": False,
        "firewall": "none",
        "ssh": False,
        "software": ["firefox"],
        "extra_packages": [],
        "flatpak": False,
        "aur_helper": "none",
        "services": [],
        "custom_commands": "",
        "finish": "none",           # none | reboot | poweroff
    }


def merge(base, override):
    """Deep-merge override into a copy of base; unknown keys are kept so a
    newer config still round-trips, but types of known keys are enforced."""
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = merge(out[k], v)
        elif k in out and out[k] is not None and v is not None and type(out[k]) is not type(v) \
                and not (isinstance(out[k], (int, float)) and isinstance(v, (int, float))
                         and not isinstance(v, bool)):
            raise ValueError(f"Setting '{k}' has the wrong type.")
        else:
            out[k] = copy.deepcopy(v)
    return out


def normalize(cfg):
    """Fill in defaults. Raises ValueError for structurally wrong input."""
    if not isinstance(cfg, dict):
        raise ValueError("The configuration must be a JSON object.")
    if cfg.get("version", VERSION) != VERSION:
        raise ValueError(f"Unsupported config version {cfg.get('version')}.")
    out = merge(default_config(), cfg)
    out["users"] = [merge(default_user(), u) for u in out["users"]]
    return out


def default_user():
    return {"username": "", "fullname": "", "password": "", "sudo": True,
            "shell": "bash", "autologin": False}


def redact(cfg):
    """Copy without secrets, for saving to disk or showing."""
    out = copy.deepcopy(cfg)
    for path in SECRET_PATHS:
        node = out
        for key in path[:-1]:
            node = node.get(key, {}) if isinstance(node, dict) else {}
        if isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = None if path[-1] == "wifi" else ""
    for u in out.get("users", []):
        u["password"] = ""
    return out


def dumps(cfg):
    return json.dumps(redact(cfg), indent=2, ensure_ascii=False)


def loads(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not valid JSON: {e.msg} (line {e.lineno})")
    return normalize(data)
