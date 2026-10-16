#!/usr/bin/env python3
"""A caching Arch mirror for test VMs. Each package is downloaded from the
internet once; every later VM install gets it from this PC's disk.

  pkgproxy.py [--port 8081] [--cache build/vmcache] [--seed build/pkgcache]

Serves /<repo>/os/<arch>/<file>. Repo databases are always fetched fresh;
package files are cached in --cache (and also looked up in --seed, e.g. the
ISO build's cache). A QEMU guest reaches it at http://10.0.2.2:<port>.
Binds to 127.0.0.1 only. pacman in the guest still verifies every signature.
"""
import argparse
import os
import re
import shutil
import signal
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PATH_RE = re.compile(r"^/([a-z0-9-]+)/os/(x86_64|any)/([A-Za-z0-9@._+:%-]+)$")
PKG_RE = re.compile(r"\.pkg\.tar\.(zst|xz)(\.sig)?$")


def upstream_mirrors(path="/etc/pacman.d/mirrorlist"):
    out = []
    try:
        for line in Path(path).read_text().splitlines():
            m = re.match(r"^\s*Server\s*=\s*(\S+)", line)
            if m and m.group(1).startswith(("http://", "https://")) and "10.0.2.2" not in m.group(1):
                out.append(m.group(1))
    except OSError:
        pass
    out.sort(key=lambda u: not u.startswith("https://"))       # prefer HTTPS
    return out or ["https://geo.mirror.pkgbuild.com/$repo/os/$arch"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--cache", default="build/vmcache")
    ap.add_argument("--seed", action="append", default=[])
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    cache = Path(args.cache)
    cache.mkdir(parents=True, exist_ok=True)
    seeds = [Path(s) for s in args.seed if Path(s).is_dir()]
    mirrors = upstream_mirrors()
    stats = {"hit": 0, "miss": 0, "bytes_hit": 0, "bytes_miss": 0}
    lock = threading.Lock()

    def log(msg):
        if not args.quiet:
            print(time.strftime("%H:%M:%S ") + msg, flush=True)

    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def send_file(self, path):
            size = path.stat().st_size
            self.send_response(200)
            self.send_header("Content-Length", str(size))
            self.send_header("Content-Type", "application/octet-stream")
            self.end_headers()
            if self.command == "HEAD":
                return size
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1024 * 1024)
            return size

        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            m = PATH_RE.match(self.path.split("?", 1)[0])
            if not m:
                self.send_error(404)
                return
            repo, arch, name = m.groups()
            cacheable = bool(PKG_RE.search(name))
            if cacheable:
                for d in [cache] + seeds:
                    p = d / urllib.request.unquote(name)
                    if p.is_file():
                        size = self.send_file(p)
                        with lock:
                            stats["hit"] += 1
                            stats["bytes_hit"] += size
                        log(f"HIT   {name} ({size / 1e6:.1f} MB)")
                        return
            for base in mirrors:
                url = base.replace("$repo", repo).replace("$arch", arch).rstrip("/") + "/" + name
                try:
                    resp = urllib.request.urlopen(url, timeout=30)
                except Exception as e:
                    if getattr(e, "code", None) == 404:
                        self.send_error(404)
                        return
                    continue
                with resp:
                    length = resp.headers.get("Content-Length")
                    self.send_response(200)
                    if length:
                        self.send_header("Content-Length", length)
                    else:
                        self.send_header("Transfer-Encoding", "identity")
                        self.close_connection = True
                    self.send_header("Content-Type", "application/octet-stream")
                    self.end_headers()
                    if self.command == "HEAD":
                        return
                    tmp = cache / f".{name}.{threading.get_ident()}.part" if cacheable else None
                    out = open(tmp, "wb") if tmp else None
                    got, t0 = 0, time.time()
                    try:
                        while True:
                            chunk = resp.read(256 * 1024)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            if out:
                                out.write(chunk)
                            got += len(chunk)
                    except (OSError, ConnectionError):
                        pass
                    finally:
                        if out:
                            out.close()
                            if length and got == int(length):
                                os.replace(tmp, cache / urllib.request.unquote(name))
                            else:
                                tmp.unlink(missing_ok=True)
                    if cacheable:
                        with lock:
                            stats["miss"] += 1
                            stats["bytes_miss"] += got
                        log(f"MISS  {name} ({got / 1e6:.1f} MB at {got / 1e6 / max(time.time() - t0, 0.01):.1f} MB/s)")
                return
            self.send_error(502, "no mirror answered")

    def stop(*_):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, stop)        # `make vm` stops it with kill: still print the summary
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), H)
    log(f"package proxy on 127.0.0.1:{args.port} (guest: http://10.0.2.2:{args.port}), cache {cache}, "
        f"{len(mirrors)} upstream mirrors")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        log(f"served {stats['hit']} from cache ({stats['bytes_hit'] / 1e9:.2f} GB), "
            f"downloaded {stats['miss']} ({stats['bytes_miss'] / 1e9:.2f} GB)")


if __name__ == "__main__":
    sys.exit(main())
