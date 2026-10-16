"""The single API the UI talks to, via pywebview's js_api or the dev server.
Public methods are callable from JavaScript; anything starting with _ is not."""
import json
import os
import subprocess
import threading
from pathlib import Path

from . import __version__
from . import effects as E
from .installer import catalog as C
from .installer import config as CFG
from .installer import plan as PL
from .installer import validate as V
from .installer.layout import LayoutError
from .installer.runner import Runner, real_mode_allowed


class Api:
    def __init__(self, system, force_dry_run=False, speed=1.0, logfile=None):
        self._sys = system
        self._dry = bool(force_dry_run or system.fixture or not real_mode_allowed())
        self._speed = speed
        self._logfile = logfile or ("/var/log/linusetup.log" if not self._dry else None)
        self._events, self._lock = [], threading.Lock()
        self._thread = None
        self._hw = None
        self._ntfs = {}
        self._wifi = None
        self._db_synced = False
        self._mirror = os.environ.get("LINUSETUP_LOCAL_MIRROR") or None

    # ------------------------------------------------------------ internals
    def _emit(self, ev):
        with self._lock:
            ev["seq"] = len(self._events)
            self._events.append(ev)

    def _hardware(self):
        if self._hw is None:
            self._hw = self._sys.hardware()
        return self._hw

    def _prepare(self, cfg):
        cfg = CFG.normalize(cfg)
        cfg["network"]["wifi"] = self._wifi
        sh = cfg["disk"]["shrink"]
        if cfg["disk"]["mode"] == "guided" and cfg["disk"]["scope"] == "shrink" and sh["partition"]:
            info = self.ntfs_info(sh["partition"])
            sh["min_bytes"] = info.get("min_bytes")
        return cfg

    def _secrets(self, cfg):
        out = [cfg["root"]["password"], cfg["disk"]["encryption"]["passphrase"]]
        out += [u["password"] for u in cfg["users"]]
        if cfg["network"].get("wifi"):
            out.append(cfg["network"]["wifi"].get("psk") or "")
        return out

    # ------------------------------------------------------------ read-only
    def bootstrap(self):
        hw = self._hardware()
        return dict(version=__version__, dry_run=self._dry, live=self._sys.is_live(),
                    fixture=self._sys.fixture, online=self._sys.online(),
                    selftest=bool(os.environ.get("LINUSETUP_SELFTEST")),
                    effects=E.choose(hw, os.environ.get("LINUSETUP_EFFECTS")),
                    hardware=hw.to_dict(), catalog=C.for_ui(), timezones=V.timezones(),
                    defaults=CFG.default_config(), default_user=CFG.default_user())

    def disks(self):
        return [d.to_dict() for d in self._sys.disks()]

    def ntfs_info(self, node):
        if node not in self._ntfs:
            self._ntfs[node] = self._sys.ntfs_info(node)
        return self._ntfs[node]

    def network(self):
        hw = self._hardware()
        return dict(online=self._sys.online(), wifi=hw.wifi,
                    connected=self._wifi["ssid"] if self._wifi else None)

    def wifi_scan(self, iface):
        try:
            return dict(ok=True, networks=self._sys.wifi_scan(iface))
        except Exception as e:
            return dict(ok=False, error=str(e))

    def wifi_connect(self, iface, ssid, psk):
        res = self._sys.wifi_connect(iface, ssid, psk or "")
        if res.get("ok"):
            self._wifi = dict(ssid=ssid, psk=psk or "")
        return res

    def check(self, cfg):
        try:
            cfg = self._prepare(cfg)
        except ValueError as e:
            return dict(errors=[dict(section="system", message=str(e))], warnings=[])
        return V.check(cfg, self._hardware(), self._sys.disks(), online=self._sys.online(),
                       real=not self._dry)

    def preview(self, cfg):
        try:
            cfg = self._prepare(cfg)
            plan = PL.build(cfg, self._hardware(), self._sys.disks(), local_mirror=self._mirror)
        except (ValueError, KeyError) as e:
            return dict(ok=False, error=str(e))
        return dict(ok=True, steps=plan.preview())

    def search_packages(self, query):
        query = (query or "").strip()
        if len(query) < 2 or not V.PKG_RE.match(query):
            return []
        if not self._dry and not self._db_synced and not self._sys.fixture:
            subprocess.run(["pacman", "-Sy", "--noconfirm"], capture_output=True, timeout=120)
            self._db_synced = True
        return self._sys.search_packages(query)

    # ------------------------------------------------------------ config files
    def export_config(self, cfg):
        try:
            return dict(ok=True, text=CFG.dumps(CFG.normalize(cfg)))
        except ValueError as e:
            return dict(ok=False, error=str(e))

    def import_config(self, text):
        try:
            return dict(ok=True, config=CFG.loads(text))
        except ValueError as e:
            return dict(ok=False, error=str(e))

    def save_config(self, cfg):
        res = self.export_config(cfg)
        if not res["ok"]:
            return res
        path = Path("/root/linusetup-config.json") if self._sys.is_live() else \
            Path.home() / "linusetup-config.json"
        try:
            path.write_text(res["text"])
        except OSError as e:
            return dict(ok=False, error=str(e))
        return dict(ok=True, path=str(path))

    # ------------------------------------------------------------ the install
    def start_install(self, cfg, fingerprints):
        if self._thread and self._thread.is_alive():
            return dict(ok=False, error="An install is already running.")
        try:
            cfg = self._prepare(cfg)
        except ValueError as e:
            return dict(ok=False, error=str(e))
        hw, disks = self._hardware(), self._sys.disks()
        res = V.check(cfg, hw, disks, online=self._sys.online(), real=not self._dry)
        if res["errors"]:
            return dict(ok=False, error=res["errors"][0]["message"], errors=res["errors"])
        try:
            plan = PL.build(cfg, hw, disks, local_mirror=self._mirror)
        except LayoutError as e:
            return dict(ok=False, error=str(e))
        # Refuse if any disk we will touch changed since the user looked at it.
        now = {d.path: d.fingerprint() for d in disks}
        for path in plan.layout.touched_disks():
            if (fingerprints or {}).get(path) != now.get(path):
                return dict(ok=False, stale=True,
                            error=f"The partitions on {path} changed since they were shown. "
                                  "Review the disk setup again.")
        with self._lock:
            self._events = []
        runner = Runner(plan, self._emit, dry_run=self._dry, secrets=self._secrets(cfg),
                        logfile=self._logfile, speed=self._speed)
        self._thread = threading.Thread(target=runner.run, daemon=True)
        self._thread.start()
        return dict(ok=True, dry_run=self._dry)

    def poll(self, after):
        with self._lock:
            evs = self._events[int(after):]
        running = bool(self._thread and self._thread.is_alive())
        return dict(events=evs, running=running)

    def selftest_report(self, data):
        """Used by ui/js/selftest.js when running inside the real window."""
        path = os.environ.get("LINUSETUP_SELFTEST_REPORT")
        if path:
            Path(path).write_text(json.dumps(data, indent=2))
        if os.environ.get("LINUSETUP_SELFTEST_EXIT"):
            threading.Timer(0.5, lambda: os._exit(0 if not data.get("failed") else 1)).start()
        return dict(ok=True)

    def power(self, action):
        if action not in ("reboot", "poweroff"):
            return dict(ok=False)
        if self._dry:
            return dict(ok=True, dry_run=True)
        subprocess.Popen(["systemctl", action])
        return dict(ok=True, dry_run=False)


def wait_online(system, timeout=180, interval=5, log=print, sleep=None, now=None):
    """Unattended installs start on tty1 right after boot, often before DHCP/DNS
    are up. Wait for the network instead of failing validation instantly."""
    import time
    sleep, now = sleep or time.sleep, now or time.time
    deadline = now() + timeout
    while not system.online():
        if now() >= deadline:
            return False
        log("linusetup auto: waiting for the network...")
        sleep(interval)
    return True


def read_fw_cfg():
    """Unattended config passed by QEMU: -fw_cfg name=opt/linusetup/config.json,file=..."""
    p = Path("/sys/firmware/qemu_fw_cfg/by_name/opt/linusetup/config.json/raw")
    if not p.exists():
        subprocess.run(["modprobe", "qemu_fw_cfg"], capture_output=True)
    return p.read_text() if p.exists() else None
