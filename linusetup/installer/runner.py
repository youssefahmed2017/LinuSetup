"""Executes a Plan. Dry-run is the default and never runs a command."""
import os
import re
import subprocess
import time
from pathlib import Path

from .plan import Cmd, Write, CopyLog

LIVE_MARKER = Path("/run/archiso")


class InstallError(Exception):
    pass


def real_mode_allowed():
    """Real execution needs ALL of: the live-ISO marker, root, and the explicit
    opt-in LINUSETUP_REAL=1 (set only by the ISO's autostart). Anything else,
    including every run on a developer's machine, is a dry run."""
    return (LIVE_MARKER.exists() and os.geteuid() == 0
            and os.environ.get("LINUSETUP_REAL") == "1"
            and os.environ.get("LINUSETUP_DRY_RUN") != "1")


class PacmanProgress:
    """pacman/pacstrap output (not a terminal) -> 0..1 for the progress bar.
    Downloads fill the first 70%, installing the rest. pacman prints the total
    first ("Packages (879) ..."), then " name downloading..." per file, then
    "(n/879) installing name". Other phases also print (n/m) (checking keys,
    integrity...), so only install lines count, or the bar would hit 100% early."""
    DOWNLOAD_SHARE = 0.7

    def __init__(self):
        self.total = self.downloaded = 0
        self.frac = 0.0

    def feed(self, line):
        text = line.strip()
        m = re.match(r"^Packages \((\d+)\)", text)
        if m:
            self.total = int(m.group(1))
        elif text.endswith(" downloading...") and not text.endswith(".sig downloading..."):
            self.downloaded += 1
            if self.total:
                self.frac = max(self.frac, self.DOWNLOAD_SHARE * min(1.0, self.downloaded / self.total))
        else:
            m = re.search(r"\(\s*(\d+)/(\d+)\) (installing|upgrading|reinstalling) ", text + " ")
            if m and int(m.group(2)):
                done = int(m.group(1)) / int(m.group(2))
                self.frac = max(self.frac, self.DOWNLOAD_SHARE + (1 - self.DOWNLOAD_SHARE) * done)
        return self.frac


class Runner:
    def __init__(self, plan, emit, dry_run=True, secrets=(), logfile=None, speed=1.0):
        self.plan, self.emit, self.dry_run = plan, emit, dry_run
        self.secrets = [s for s in secrets if s and len(s) >= 3]
        self.logfile = open(logfile, "a") if logfile else None
        self.lines, self.warnings = [], []
        self.speed = speed      # dry-run time multiplier (tests use 0)

    # ---------------------------------------------------------- helpers
    def scrub(self, text):
        for s in self.secrets:
            text = text.replace(s, "••••••")
        return text

    def log(self, line):
        line = self.scrub(line.rstrip("\n"))
        self.lines.append(line)
        if self.logfile:
            self.logfile.write(line + "\n")
            self.logfile.flush()
        self.emit({"type": "log", "line": line})

    def warn(self, message):
        message = self.scrub(message)
        self.warnings.append(message)
        self.log("WARNING: " + message)
        self.emit({"type": "warning", "message": message})

    def capture(self, argv):
        """Run a read-only command whose output is needed (UUIDs)."""
        if self.dry_run:
            self.log("[dry-run] $ " + " ".join(argv))
            return "dry-run-" + re.sub(r"\W+", "-", argv[-1]).strip("-")
        r = subprocess.run(argv, capture_output=True, text=True)
        if r.returncode != 0 or not r.stdout.strip():
            raise InstallError(f"{argv[0]} failed: {r.stderr.strip()}")
        return r.stdout.strip()

    def _progress(self, value):
        """Progress never moves backwards (float rounding, regex re-matches)."""
        self._last = max(getattr(self, "_last", 0.0), min(1.0, value))
        self.emit({"type": "progress", "value": self._last})

    def _sleep(self, s):
        if self.speed:
            time.sleep(s * self.speed)

    # ---------------------------------------------------------- run
    def run(self):
        t0 = time.time()
        steps = self.plan.steps
        self.emit({"type": "plan", "steps": [dict(id=s.id, label=s.label) for s in steps],
                   "dry_run": self.dry_run})
        total_w = sum(s.weight for s in steps)
        done_w = 0
        current = None
        try:
            for i, step in enumerate(steps):
                current = step
                self.emit({"type": "step", "id": step.id, "label": step.label,
                           "index": i, "total": len(steps)})
                weights = [max(getattr(a, "sim", 0.15), 0.05) for a in step.actions] or [1]
                span, before = sum(weights), 0.0

                def prog(f, b=None, w=None):
                    frac = (b + w * min(f, 1.0)) / span
                    self._progress((done_w + step.weight * frac) / total_w)
                try:
                    for action, w in zip(step.actions, weights):
                        self._do(action, lambda f, b=before, w=w: prog(f, b, w))
                        before += w
                        prog(0, before, 0)
                finally:
                    for action in step.always:
                        try:
                            self._do(action, lambda f: None)
                        except Exception as e:      # cleanup must never mask the real error
                            self.warn(f"Cleanup failed: {e}")
                done_w += step.weight
                self._progress(done_w / total_w)
            self.emit({"type": "done", "dry_run": self.dry_run, "warnings": self.warnings,
                       "seconds": round(time.time() - t0)})
        except Exception as e:
            self.log(f"ERROR: {e}")
            if not self.dry_run:
                for action in self.plan.cleanup:
                    try:
                        self._do(action, lambda f: None)
                    except Exception:
                        pass
            self.emit({"type": "error", "message": self.scrub(str(e)),
                       "step": current.label if current else "",
                       "tail": self.lines[-25:]})
        finally:
            if self.logfile:
                self.logfile.close()
                self.logfile = None

    def _do(self, action, on_frac):
        try:
            if isinstance(action, Cmd):
                self._cmd(action, on_frac)
            elif isinstance(action, Write):
                self._write(action)
            elif isinstance(action, CopyLog):
                self._copylog(action)
        except Exception as e:
            if getattr(action, "optional", False):
                self.warn(f"{action.show()}: {e}")
            else:
                raise

    def _cmd(self, c, on_frac):
        shown = c.show()
        if self.dry_run:
            self.log(f"[dry-run] $ {shown}")
            n = max(1, int(c.sim / 0.1))
            for k in range(n):
                self._sleep(c.sim / n)
                on_frac((k + 1) / n)
            return
        self.log(f"$ {shown}")
        out = open(c.stdout_to, "a") if c.stdout_to else subprocess.PIPE
        try:
            p = subprocess.Popen(
                c.argv, stdin=subprocess.PIPE if c.stdin is not None else subprocess.DEVNULL,
                stdout=out, stderr=subprocess.PIPE if c.stdout_to else subprocess.STDOUT,
                text=True, env=dict(os.environ, LC_ALL="C"))
            if c.stdin is not None:
                p.stdin.write(c.stdin)
                p.stdin.close()
            tail = []
            tracker = PacmanProgress() if c.progress == "pacman" else None
            stream = p.stderr if c.stdout_to else p.stdout
            for line in stream:
                tail = (tail + [line.rstrip()])[-6:]
                if not c.quiet:
                    self.log(line)
                if tracker:
                    before = tracker.frac
                    if tracker.feed(line) > before:
                        on_frac(tracker.frac)
            rc = p.wait()
        finally:
            if c.stdout_to:
                out.close()
        if rc != 0:
            detail = self.scrub(" / ".join(t for t in tail if t)[-300:])
            argv = c.argv[3:] if c.argv[0] == "stdbuf" else c.argv
            raise InstallError(f"`{argv[0] if argv[0] != 'arch-chroot' else ' '.join(argv[2:4])}` "
                               f"failed (exit {rc})" + (f": {detail}" if detail else ""))

    def _write(self, w):
        text = w.content(self) if callable(w.content) else w.content
        verb = "append" if w.append else "write"
        if self.dry_run:
            self.log(f"[dry-run] {verb} {w.path} ({len(text)} bytes)")
            self._sleep(0.03)
            return
        self.log(f"{verb} {w.path}")
        p = Path(w.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a" if w.append else "w") as f:
            f.write(text)
        if not w.append:
            p.chmod(w.mode)

    def _copylog(self, a):
        if self.dry_run:
            self.log(f"[dry-run] save log to {a.path}")
            return
        p = Path(a.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join(self.lines) + "\n")
        p.chmod(0o600)
