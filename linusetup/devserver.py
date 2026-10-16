"""Development server: serves the UI and exposes the real Api over HTTP, backed
by fixture hardware by default. Used for `make preview` and the UI self-test.
Binds to 127.0.0.1 only."""
import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import Api

UI_DIR = (Path(__file__).parent / "ui").resolve()


def serve(system, port=8765, report_path=None, exit_after_report=False, speed=1.0, quiet=False):
    api = Api(system, force_dry_run=True, speed=speed)
    state = {"server": None}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            if not quiet:
                super().log_message(*a)

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else body.encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.startswith("/__frame"):
                # The UI inside a fixed-size iframe: test small screens in any browser.
                from urllib.parse import parse_qs, urlsplit
                q = parse_qs(urlsplit(self.path).query)
                w, h = int(q.get("w", ["800"])[0]), int(q.get("h", ["600"])[0])
                inner = q.get("q", [""])[0]
                return self._send(200, f'<!doctype html><body style="margin:0;background:#000">'
                                       f'<iframe src="/?{inner}" style="width:{w}px;height:{h}px;border:0"></iframe>',
                                  "text/html")
            rel = self.path.split("?", 1)[0].lstrip("/") or "index.html"
            f = (UI_DIR / rel).resolve()
            if UI_DIR not in f.parents and f != UI_DIR or not f.is_file():
                return self._send(404, "not found", "text/plain")
            self._send(200, f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")

        def do_POST(self):
            name = self.path.split("?", 1)[0].removeprefix("/api/")
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
            if name == "_report":
                if report_path:
                    Path(report_path).write_text(json.dumps(body, indent=2))
                self._send(200, "{}")
                if exit_after_report:
                    threading.Thread(target=state["server"].shutdown, daemon=True).start()
                return
            fn = getattr(api, name, None)
            if name.startswith("_") or not callable(fn):
                return self._send(404, json.dumps({"error": "no such method"}))
            try:
                self._send(200, json.dumps(fn(*body.get("args", []))))
            except Exception as e:      # surface backend bugs to the UI/self-test
                import traceback
                traceback.print_exc()
                self._send(500, json.dumps({"error": f"{type(e).__name__}: {e}"}))

    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    state["server"] = srv
    if not quiet:
        print(f"LinuSetup dev server: http://127.0.0.1:{port}/  (fixture={system.fixture}, dry run)")
    srv.serve_forever()
