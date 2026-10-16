"""pywebview shell: exposes the install engine to the UI. No install logic here."""
import json
import subprocess
import sys
import threading
import zoneinfo
from pathlib import Path

import webview

from .installer import presets as P
from .installer.config import InstallConfig, KEYMAPS, validate
from .installer.hardware import detect_hardware, is_live, is_online, list_disks
from .installer.plan import build_plan
from .installer.runner import Runner, real_mode_allowed

UI_DIR = Path(__file__).parent / "ui"


class Api:
    """Public methods are callable from JS as window.pywebview.api.<name>().
    Attributes starting with _ are not exposed (pywebview skips them)."""

    def __init__(self, force_dry_run=False):
        self._window = None
        self._thread = None
        self._hw = None
        self._dry = force_dry_run or not real_mode_allowed()

    def _set_window(self, window):
        self._window = window

    def _emit(self, event):
        if self._window is not None:
            self._window.evaluate_js(
                f"window.LinuSetup && window.LinuSetup.onEvent({json.dumps(event)})")

    # ---- read-only info for the UI --------------------------------------
    def system_info(self):
        self._hw = detect_hardware()
        return {
            "dry_run": self._dry,
            "live": is_live(),
            "online": is_online(),
            "uefi": self._hw.uefi,
            "cpu": self._hw.cpu_vendor,
            "gpus": self._hw.gpus,
            "virt": self._hw.virt,
            "ram_gb": self._hw.ram_gb,
            "presets": [
                {"id": i, "name": P.PRESETS[i].name, "blurb": P.PRESETS[i].blurb,
                 "packages": list(P.PRESETS[i].packages)}
                for i in P.PRESET_ORDER],
            "timezones": sorted(zoneinfo.available_timezones()),
            "keymaps": list(KEYMAPS),
        }

    def disks(self):
        return [d.to_dict() for d in list_disks()]

    # ---- the one action -------------------------------------------------
    def start_install(self, cfg_dict):
        if self._thread and self._thread.is_alive():
            return {"ok": False, "error": "An install is already running."}
        hw = self._hw or detect_hardware()
        try:
            cfg = InstallConfig.from_dict(cfg_dict)
            usable = [d.path for d in list_disks() if d.usable]
            validate(cfg, usable, P.PRESETS.keys(), zoneinfo.available_timezones())
            plan = build_plan(cfg, hw)
        except (ValueError, KeyError, TypeError) as e:
            return {"ok": False, "error": str(e)}
        runner = Runner(plan, self._emit, dry_run=self._dry)
        self._thread = threading.Thread(target=runner.run, daemon=True)
        self._thread.start()
        return {"ok": True, "dry_run": self._dry}

    def reboot(self):
        if self._dry:
            return {"ok": True, "dry_run": True}
        subprocess.Popen(["systemctl", "reboot"])
        return {"ok": True, "dry_run": False}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    api = Api(force_dry_run="--dry-run" in argv)
    window = webview.create_window(
        "LinuSetup",
        url=str(UI_DIR / "index.html"),
        js_api=api,
        fullscreen="--windowed" not in argv,
        width=1180, height=760, min_size=(900, 600),
        background_color="#0b0d14",
    )
    api._set_window(window)
    # gui='gtk' keeps us on WebKitGTK; the Qt backend would pull in Chromium.
    webview.start(gui="gtk", debug="--debug" in argv)
