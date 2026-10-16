"""Screenshot the UI with WebKitGTK's own snapshot API (no screen capture).
Run inside a compositor, e.g. headless cage:  tools/screens.sh
  snap.py URL OUT.png  -> waits until the iframe's document.title == 'READY'."""
import sys

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("WebKit2", "4.1")
from gi.repository import GLib, Gtk, WebKit2  # noqa: E402

url, out = sys.argv[1], sys.argv[2]
win = Gtk.Window()
win.set_default_size(1700, 1100)
view = WebKit2.WebView()
win.add(view)
win.show_all()
view.load_uri(url)
state = {"tries": 0}


def done(v, res):
    v.get_snapshot_finish(res).write_to_png(out)
    Gtk.main_quit()


def check(v, res):
    try:
        title = v.evaluate_javascript_finish(res).to_string()
    except Exception:
        title = ""
    if title == "READY":
        GLib.timeout_add(900, lambda: v.get_snapshot(WebKit2.SnapshotRegion.FULL_DOCUMENT,
                                                     WebKit2.SnapshotOptions.NONE, None, done) and False)
    else:
        GLib.timeout_add(200, poll)


def poll():
    state["tries"] += 1
    if state["tries"] > 600:
        print("timeout", file=sys.stderr)
        Gtk.main_quit()
        return False
    view.evaluate_javascript("(document.querySelector('iframe')||{}).contentDocument ? "
                             "document.querySelector('iframe').contentDocument.title : ''",
                             -1, None, None, None, check)
    return False


GLib.timeout_add(500, poll)
Gtk.main()
