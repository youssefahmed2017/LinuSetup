"""The GUI: a pywebview window on WebKitGTK showing linusetup/ui."""
import os
from pathlib import Path

import webview

from . import effects as E
from .api import Api

UI_DIR = Path(__file__).parent / "ui"


def run_gui(system, windowed=False, debug=False, dry_run=False, query=""):
    # WebKit's GPU compositing only where there is real acceleration; in VMs it
    # renders blank or crawls, so fall back to software rendering there.
    if E.needs_software_rendering(system.hardware()):
        os.environ.setdefault("WEBKIT_DISABLE_COMPOSITING_MODE", "1")
        os.environ.setdefault("WEBKIT_DISABLE_DMABUF_RENDERER", "1")
    api = Api(system, force_dry_run=dry_run, speed=float(os.environ.get("LINUSETUP_SPEED", "1")))
    webview.create_window(
        "LinuSetup", url=str(UI_DIR / "index.html") + query, js_api=api,
        fullscreen=not windowed, width=1280, height=800, min_size=(800, 600),
        background_color="#0b0d14", text_select=False)
    # gui='gtk' keeps us on WebKitGTK; the Qt backend would pull in Chromium.
    webview.start(gui="gtk", debug=debug, private_mode=True)
