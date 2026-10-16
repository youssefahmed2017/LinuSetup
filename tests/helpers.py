import copy

from linusetup.installer import config as CFG
from linusetup.installer.fixtures import FixtureSystem
from linusetup.installer.system import Hardware

PW = "correct-horse-battery"
ROOTPW = "root-secret-42"
LUKS = "luks-passphrase-99"


def cfg(**over):
    """A valid config targeting the empty fixture disk, with overrides by dotted path."""
    c = CFG.default_config()
    c["disk"]["device"] = "/dev/sda"
    c["users"] = [dict(CFG.default_user(), username="sam", fullname="Sam R", password=PW)]
    for path, val in over.items():
        node = c
        keys = path.split("__")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = copy.deepcopy(val)
    return CFG.normalize(c)


def hw(**kw):
    base = dict(uefi=True, cpu_vendor="amd", gpus=[("amd", "Radeon")], virt="", ram_gb=16, wifi=[])
    base.update(kw)
    return Hardware(**base)


def disks():
    return FixtureSystem().disks()


def disk(path):
    return next(d for d in disks() if d.path == path)
