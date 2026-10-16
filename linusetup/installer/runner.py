"""Executes a plan. Dry-run is the default and never runs a command."""
import os
import re
import subprocess
import time
from pathlib import Path

from .hardware import is_live
from .plan import Cmd, Write, Step, MNT


class InstallError(Exception):
    pass


def real_mode_allowed() -> bool:
    """Real execution needs ALL of: the live-ISO marker, root, and the explicit
    opt-in LINUSETUP_REAL=1 (set only by the ISO's autostart). Anything else,
    including every run on a developer's own machine, is dry-run."""
    return (is_live() and os.geteuid() == 0
            and os.environ.get("LINUSETUP_REAL") == "1"
            and os.environ.get("LINUSETUP_DRY_RUN") != "1")


class Runner:
    def __init__(self, plan, emit, dry_run=True):
        self.plan, self.emit, self.dry_run = plan, emit, dry_run
        self._log_tail = []

    # ---- helpers ---------------------------------------------------------
    def log(self, line):
        line = line.rstrip("\n")
        self._log_tail = (self._log_tail + [line])[-40:]
        self.emit({"type": "log", "line": line})

    def capture(self, argv):
        if self.dry_run:
            self.log("[dry-run] $ " + " ".join(argv))
            return "00000000-dry-run-uuid"
        out = subprocess.run(argv, capture_output=True, text=True)
        if out.returncode != 0:
            raise InstallError(f"{argv[0]} failed: {out.stderr.strip()}")
        return out.stdout.strip()

    def _progress(self, done_w, step, frac, total_w):
        self.emit({"type": "progress",
                   "value": min(1.0, (done_w + step.weight * min(frac, 1.0)) / total_w)})

    # ---- execution -------------------------------------------------------
    def run(self):
        total_w = sum(s.weight for s in self.plan)
        done_w = 0
        try:
            for i, step in enumerate(self.plan):
                self.emit({"type": "step", "id": step.id, "label": step.label,
                           "index": i, "total": len(self.plan)})
                self._progress(done_w, step, 0.0, total_w)
                # Within a step, actions are weighted (long commands count more)
                # so progress is monotonic instead of resetting per command.
                weights = [max(a.sim, 0.15) if isinstance(a, Cmd) else 0.05
                           for a in step.actions]
                span, before = sum(weights), 0.0
                for action, w in zip(step.actions, weights):
                    if isinstance(action, Cmd):
                        self._cmd(action, lambda f, b=before, w=w: self._progress(
                            done_w, step, (b + w * f) / span, total_w))
                    else:
                        self._write(action)
                    before += w
                    self._progress(done_w, step, before / span, total_w)
                done_w += step.weight
                self._progress(done_w, step, 0.0, total_w)
            self.emit({"type": "done", "dry_run": self.dry_run})
        except Exception as e:  # report, clean up, never crash the UI thread
            self.log(f"ERROR: {e}")
            if not self.dry_run:
                subprocess.run(["umount", "-R", MNT], capture_output=True)
            self.emit({"type": "error", "message": str(e), "tail": self._log_tail[-12:]})

    def _cmd(self, c: Cmd, on_frac):
        shown = " ".join(c.argv) + (" < (stdin hidden)" if c.stdin else "")
        if self.dry_run:
            self.log(f"[dry-run] $ {shown}")
            steps = max(1, int(c.sim / 0.1))
            for k in range(steps):
                time.sleep(c.sim / steps)
                on_frac((k + 1) / steps)
            return
        self.log(f"$ {shown}")
        out = open(c.stdout_to, "a") if c.stdout_to else subprocess.PIPE
        try:
            p = subprocess.Popen(c.argv, stdin=subprocess.PIPE if c.stdin else None,
                                 stdout=out, stderr=subprocess.STDOUT if not c.stdout_to
                                 else subprocess.PIPE, text=True)
            if c.stdin:
                p.stdin.write(c.stdin)
                p.stdin.close()
            best = 0.0
            stream = p.stdout if not c.stdout_to else p.stderr
            for line in stream:
                self.log(line)
                if c.progress_re:
                    m = re.search(c.progress_re, line)
                    if m and int(m.group(2)):
                        best = max(best, int(m.group(1)) / int(m.group(2)))
                        on_frac(best)
            rc = p.wait()
        finally:
            if c.stdout_to:
                out.close()
        if rc != 0:
            raise InstallError(f"`{c.argv[0]}` exited with status {rc}")

    def _write(self, w: Write):
        text = w.content(self) if callable(w.content) else w.content
        if self.dry_run:
            self.log(f"[dry-run] write {w.path} ({len(text)} bytes)")
            time.sleep(0.05)
            return
        self.log(f"write {w.path}")
        p = Path(w.path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        p.chmod(w.mode)
