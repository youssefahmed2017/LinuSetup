"""LinuSetup command line.

  python -m linusetup                 GUI (fullscreen; add --windowed for a window)
  python -m linusetup serve           UI + fixture backend on http://127.0.0.1:8765
  python -m linusetup plan  CFG.json  print every command an install would run
  python -m linusetup check CFG.json  validate a config
  python -m linusetup auto  [--fw-cfg | CFG.json]   unattended install (see DECISIONS.md)
"""
import argparse
import json
import sys


def _system(fixtures):
    if fixtures:
        from .installer.fixtures import FixtureSystem
        return FixtureSystem()
    from .installer.system import RealSystem
    return RealSystem()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="linusetup")
    sub = ap.add_subparsers(dest="cmd")
    g = sub.add_parser("gui")
    for p in (ap, g):
        p.add_argument("--windowed", action="store_true")
        p.add_argument("--debug", action="store_true")
        p.add_argument("--dry-run", action="store_true")
        p.add_argument("--fixtures", action="store_true", help="pretend hardware (implies dry run)")
        p.add_argument("--query", default="", help=argparse.SUPPRESS)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--real-hardware", action="store_true", help="read this machine instead of fixtures")
    s.add_argument("--report")
    s.add_argument("--exit-after-report", action="store_true")
    s.add_argument("--speed", type=float, default=1.0)
    s.add_argument("--quiet", action="store_true")
    for name in ("plan", "check"):
        p = sub.add_parser(name)
        p.add_argument("config")
        p.add_argument("--fixtures", action="store_true")
    a = sub.add_parser("auto")
    a.add_argument("config", nargs="?")
    a.add_argument("--fw-cfg", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd in (None, "gui"):
        from .app import run_gui
        return run_gui(_system(args.fixtures), windowed=args.windowed, debug=args.debug,
                       dry_run=args.dry_run, query=args.query)
    if args.cmd == "serve":
        from .devserver import serve
        return serve(_system(not args.real_hardware), port=args.port, report_path=args.report,
                     exit_after_report=args.exit_after_report, speed=args.speed, quiet=args.quiet)
    if args.cmd in ("plan", "check"):
        return _plan_or_check(args)
    if args.cmd == "auto":
        return _auto(args)


def _plan_or_check(args):
    from .installer import config as CFG, plan as PL, validate as V
    from .installer.layout import LayoutError
    sysm = _system(args.fixtures)
    cfg = CFG.loads(open(args.config).read())
    hw, disks = sysm.hardware(), sysm.disks()
    if args.cmd == "check":
        res = V.check(cfg, hw, disks, online=True)
        for e in res["errors"]:
            print(f"ERROR   [{e['section']}] {e['message']}")
        for w in res["warnings"]:
            print(f"warning [{w['section']}] {w['message']}")
        print("OK" if not res["errors"] else f"{len(res['errors'])} error(s)")
        return 1 if res["errors"] else 0
    try:
        plan = PL.build(cfg, hw, disks)
    except LayoutError as e:
        print(f"ERROR: {e}")
        return 1
    for step in plan.preview():
        print(f"\n## {step['label']}")
        for c in step["commands"]:
            print("  " + c)
    return 0


def _auto(args):
    """Headless install. Real only from QEMU fw_cfg on the live ISO; a config
    file given on the command line always runs as a dry run."""
    from .api import Api, read_fw_cfg, wait_online
    from .installer.system import RealSystem
    text = read_fw_cfg() if args.fw_cfg else open(args.config).read() if args.config else None
    if not text:
        print("linusetup auto: no config (pass a file or --fw-cfg)", flush=True)
        return 2
    api = Api(RealSystem(), force_dry_run=not args.fw_cfg)
    imp = api.import_config(text)
    if not imp["ok"]:
        print(f"linusetup auto: {imp['error']}", flush=True)
        return 2
    cfg = imp["config"]
    raw = json.loads(text)          # secrets are allowed in an unattended config
    cfg["root"]["password"] = raw.get("root", {}).get("password", "")
    cfg["disk"]["encryption"]["passphrase"] = raw.get("disk", {}).get("encryption", {}).get("passphrase", "")
    for u, ru in zip(cfg["users"], raw.get("users", [])):
        u["password"] = ru.get("password", "")
    if not cfg["disk"]["device"] and cfg["disk"]["mode"] == "guided":
        print("linusetup auto: the config must name disk.device explicitly", flush=True)
        return 2
    if not wait_online(api._sys, log=lambda m: print(m, flush=True)):
        print("LINUSETUP-FAILED: no network after 3 minutes", flush=True)
        return 1
    fps = {d["path"]: d["fingerprint"] for d in api.disks()}
    res = api.start_install(cfg, fps)
    if not res["ok"]:
        print(f"LINUSETUP-FAILED: {res['error']}", flush=True)
        return 1
    seen, ok = 0, None
    import time
    while ok is None:
        r = api.poll(seen)
        for ev in r["events"]:
            seen = ev["seq"] + 1
            if ev["type"] == "log":
                print(ev["line"], flush=True)
            elif ev["type"] == "step":
                print(f"=== [{ev['index'] + 1}/{ev['total']}] {ev['label']}", flush=True)
            elif ev["type"] == "done":
                ok = True
            elif ev["type"] == "error":
                print(f"LINUSETUP-FAILED: {ev['message']}", flush=True)
                ok = False
        if ok is None and not r["running"]:
            time.sleep(0.5)
            if not api.poll(seen)["events"]:
                ok = False
        time.sleep(0.3)
    print("LINUSETUP-SUCCESS" if ok else "LINUSETUP-FAILED", flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
