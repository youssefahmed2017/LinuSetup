"""Catalog names checked against the real system: packages resolve the way
pacstrap resolves them (fresh system, no conflicts), keymaps exist in kbd,
layouts exist in xkb, locales exist in glibc."""
import os
import re
import shutil
import subprocess
import tempfile
import unittest

from linusetup.installer import catalog as C
from linusetup.installer import plan as PL
from tests.helpers import cfg, hw, disks

SYNC = "/var/lib/pacman/sync"
HAVE_PACMAN = shutil.which("pacman") and os.path.isdir(SYNC) and os.listdir(SYNC)


def _strip(dep):
    return re.split(r"[<>=:]", dep.strip(), 1)[0]


def _split(dep):
    """'foo>=1.2' -> ('foo', '>=', '1.2'); 'foo' -> ('foo', '', '')"""
    m = re.match(r"^([^<>=:]+)(?:(<=|>=|<|>|=)(.+))?$", dep.strip())
    return (m.group(1), m.group(2) or "", m.group(3) or "") if m else (dep, "", "")


def _vercmp(a, b, _cache={}):
    if (a, b) not in _cache:
        out = subprocess.run(["vercmp", a, b], capture_output=True, text=True).stdout.strip()
        _cache[(a, b)] = int(out or 0)
    return _cache[(a, b)]


def _satisfies(version, op, want):
    if not op:
        return True
    if not version:
        return False
    c = _vercmp(version, want)
    return {"<": c < 0, "<=": c <= 0, ">": c > 0, ">=": c >= 0, "=": c == 0}[op]


class Resolver:
    """pacman -Sp against an empty local DB = what pacstrap sees on a new disk."""
    def __init__(self):
        self.tmp = tempfile.mkdtemp(prefix="linusetup-db-")
        os.makedirs(os.path.join(self.tmp, "local"))
        os.symlink(SYNC, os.path.join(self.tmp, "sync"))
        self.info = {}

    def close(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def resolve(self, pkgs):
        r = subprocess.run(["pacman", "-Sp", "--noconfirm", "--print-format", "%n", "--dbpath", self.tmp,
                            "--logfile", "/dev/null", *pkgs], capture_output=True, text=True)
        return r.returncode, r.stdout.split(), r.stderr

    def details(self, names):
        missing = [n for n in names if n not in self.info]
        for i in range(0, len(missing), 200):
            out = subprocess.run(["pacman", "-Si", "--dbpath", self.tmp, *missing[i:i + 200]],
                                 capture_output=True, text=True).stdout
            for block in out.split("\n\n"):
                fields, key = {}, None
                for line in block.splitlines():
                    if re.match(r"^\S.*?\s+:", line):
                        key, _, val = line.partition(":")
                        key = key.strip()
                        fields[key] = val.strip()
                    elif key:
                        fields[key] += " " + line.strip()
                if "Name" in fields:
                    lst = lambda k: [] if fields.get(k, "None") == "None" else [_split(x) for x in fields[k].split()]
                    self.info[fields["Name"]] = dict(version=fields.get("Version", ""),
                                                     provides=lst("Provides"), conflicts=lst("Conflicts With"))
        return {n: self.info[n] for n in names if n in self.info}

    def conflicts(self, names):
        info = self.details(names)
        provided = {}       # name -> [(package, version it provides)]
        for n, d in info.items():
            provided.setdefault(n, []).append((n, d["version"]))
            for pname, op, ver in d["provides"]:
                provided.setdefault(pname, []).append((n, ver if op == "=" else ""))
        found = set()
        for n, d in info.items():
            for cname, op, ver in d["conflicts"]:
                for other, other_ver in provided.get(cname, ()):
                    if other != n and _satisfies(other_ver, op, ver):
                        found.add(tuple(sorted((n, other))))
        return sorted(found)


def selection(**over):
    h = over.pop("_hw", hw())
    return PL.build(cfg(**over), h, disks()).selection.packages


@unittest.skipUnless(HAVE_PACMAN, "pacman sync databases not available")
class PackagesResolve(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.r = Resolver()

    @classmethod
    def tearDownClass(cls):
        cls.r.close()

    def assert_installable(self, pkgs, label):
        rc, names, err = self.r.resolve(pkgs)
        self.assertEqual(rc, 0, f"{label}: pacman could not resolve:\n{err.strip()[:800]}")
        self.assertEqual(self.r.conflicts(names), [], f"{label}: conflicting packages")

    def test_checker_detects_real_problems(self):
        self.assertTrue(self.r.conflicts(["pulseaudio", "pipewire-pulse"]))
        rc, _, err = self.r.resolve(["base", "definitely-not-a-package"])
        self.assertNotEqual(rc, 0)

    @unittest.skipUnless(os.path.exists("/usr/share/archiso/configs/releng/packages.x86_64"), "archiso not installed")
    def test_live_iso_package_list(self):
        """releng's list + what iso/build.sh adds must install cleanly (this is mkarchiso's pacstrap)."""
        base = [l.strip() for l in open("/usr/share/archiso/configs/releng/packages.x86_64")
                if l.strip() and not l.startswith("#")]
        src = open(os.path.join(os.path.dirname(__file__), "..", "iso", "build.sh")).read()
        extra = re.search(r"packages.x86_64\" <<'EOF'\n(.*?)\nEOF", src, re.S).group(1).split()
        self.assertIn("python-pywebview", extra)
        self.assert_installable(base + extra, "live ISO")

    def test_every_profile(self):
        for pid in C.PROFILES:
            with self.subTest(profile=pid):
                self.assert_installable(selection(profiles=[pid]), pid)

    def test_everything_at_once(self):
        all_sw = list(C.SOFTWARE_INDEX)
        pk = selection(profiles=["kde"], software=all_sw, printing=True, bluetooth=True, flatpak=True,
                       ssh=True, firewall="ufw", aur_helper="yay", disk__fs="btrfs",
                       disk__btrfs={"subvolumes": True, "compress": "zstd", "snapshots": True},
                       kernels=list(C.KERNELS), headers=True,
                       _hw=hw(gpus=[("nvidia", "RTX"), ("intel", "UHD")], virt=""))
        self.assert_installable(pk, "everything + KDE + NVIDIA/Intel")

    def test_gnome_gaming_amd(self):
        self.assert_installable(selection(profiles=["gnome"], software=["steam", "wine", "gamemode", "mangohud"],
                                          firewall="firewalld"), "gnome gaming")

    def test_vm_and_drivers(self):
        for virt in C.VM_TOOLS:
            with self.subTest(virt=virt):
                self.assert_installable(selection(software=["steam"], _hw=hw(gpus=[], virt=virt)), virt)
        for drv in C.GRAPHICS_PACKAGES:
            with self.subTest(driver=drv):
                self.assert_installable(selection(graphics=drv, software=["steam"]), drv)

    def test_networkd_and_minimal(self):
        self.assert_installable(selection(profiles=["minimal"], network={"manager": "networkd"}, audio="none"),
                                "minimal")
        self.assert_installable(selection(profiles=["server"], network={"manager": "none"}), "server")

    def test_shells_and_grub(self):
        c = dict(profiles=["sway"], bootloader__type="grub")
        pk = PL.build(cfg(**c), hw(uefi=False), disks()).selection.packages + ["zsh", "fish"]
        self.assert_installable(pk, "sway grub bios")


FILESDB = os.path.join(os.path.dirname(__file__), "..", "build", "filesdb")


@unittest.skipUnless(HAVE_PACMAN and os.path.exists(os.path.join(FILESDB, "sync", "extra.files")),
                     "file lists not downloaded (make filesdb)")
class UnitsShipped(unittest.TestCase):
    """Every unit a plan enables is shipped by a package that plan installs.
    A wrong name would only fail at the very end of a real install."""

    def owner(self, unit, cache={}):
        if unit not in cache:
            name = unit if re.search(r"\.(service|timer|socket|target|path)$", unit) else unit + ".service"
            out = subprocess.run(["pacman", "-F", "-q", "--dbpath", FILESDB, "--logfile", "/dev/null",
                                  f"usr/lib/systemd/system/{name}"], capture_output=True, text=True).stdout
            cache[unit] = {l.split("/")[-1] for l in out.split()}
        return cache[unit]

    def test_units(self):
        r = Resolver()
        try:
            scenarios = [dict(profiles=[p]) for p in C.PROFILES] + [
                dict(profiles=["kde"], software=list(C.SOFTWARE_INDEX), printing=True, ssh=True, firewall="ufw",
                     disk__fs="btrfs", disk__btrfs={"subvolumes": True, "compress": "zstd", "snapshots": True}),
                dict(firewall="firewalld", network={"manager": "networkd"}, bootloader__type="grub",
                     disk__fs="btrfs", disk__btrfs={"subvolumes": True, "compress": "zstd", "snapshots": True}),
            ] + [dict(_hw=hw(virt=v, gpus=[])) for v in C.VM_TOOLS]
            for sc in scenarios:
                h = sc.pop("_hw", hw())
                plan = PL.build(cfg(**sc), h, disks())
                rc, names, err = r.resolve(plan.selection.packages)
                self.assertEqual(rc, 0, err)
                for unit in plan.selection.services:
                    with self.subTest(unit=unit, scenario=str(sc)[:80]):
                        owners = self.owner(unit)
                        self.assertTrue(owners, f"no package ships {unit}")
                        self.assertTrue(owners & set(names), f"{unit} is shipped by {owners}, none installed")
        finally:
            r.close()


class Names(unittest.TestCase):
    @unittest.skipUnless(shutil.which("localectl"), "localectl not available")
    def test_console_keymaps_exist(self):
        out = subprocess.run(["localectl", "list-keymaps"], capture_output=True, text=True).stdout.split()
        if not out:
            self.skipTest("no keymaps listed")
        for kid, (_, console, *_r) in C.KEYBOARDS.items():
            self.assertIn(console, out, kid)

    @unittest.skipUnless(os.path.exists("/usr/share/X11/xkb/rules/base.lst"), "xkb rules not available")
    def test_xkb_layouts_exist(self):
        text = open("/usr/share/X11/xkb/rules/base.lst").read()
        layouts = set(re.findall(r"^\s+(\S+)\s", text.split("! layout")[1].split("! variant")[0], re.M))
        variants = set(re.findall(r"^\s+(\S+)\s+(\S+):", text.split("! variant")[1].split("! option")[0], re.M))
        opts = set(re.findall(r"^\s+(\S+)\s", text.split("! option")[1], re.M))
        for kid, (_, _, layout, variant, opt) in C.KEYBOARDS.items():
            for l in layout.split(","):
                self.assertIn(l, layouts, kid)
            if variant:
                self.assertIn((variant, layout), variants, kid)
            if opt:
                self.assertIn(opt, opts, kid)

    def test_locales(self):
        locs = C.locales()
        self.assertIn("en_US.UTF-8", locs)
        self.assertTrue(all(l.endswith(".UTF-8") or "UTF-8" in l for l in locs))

    def test_ui_catalog_is_json_safe(self):
        import json
        json.dumps(C.for_ui())


if __name__ == "__main__":
    unittest.main()
