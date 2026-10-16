#!/usr/bin/env python3
"""Check every package in a pacman cache directory, and quarantine (never
delete) any that are damaged, with a report saying exactly what is wrong.

  verify_pkgcache.py CACHE_DIR [--dbpath DIR] [--quarantine DIR]

Checks per file:
  * zstd integrity (the archive's built-in checksum; catches truncation and bit rot)
  * size and SHA-256 against the repo database, when that exact version is in it
Exit status: 0 = all good, 1 = damaged files found (moved if --quarantine).
Read-only unless --quarantine is given.
"""
import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from pathlib import Path


def repo_index(dbpath):
    """filename -> (sha256, size, repo) from <dbpath>/sync/*.db"""
    index = {}
    for db in sorted(Path(dbpath, "sync").glob("*.db")):
        try:
            with tarfile.open(db) as t:
                for m in t.getmembers():
                    if not m.name.endswith("/desc"):
                        continue
                    d = t.extractfile(m).read().decode(errors="replace")
                    fn = re.search(r"%FILENAME%\n(.+)", d)
                    sha = re.search(r"%SHA256SUM%\n(.+)", d)
                    size = re.search(r"%CSIZE%\n(\d+)", d)
                    if fn:
                        index[fn.group(1)] = (sha.group(1) if sha else None,
                                              int(size.group(1)) if size else None, db.stem)
        except (tarfile.TarError, OSError) as e:
            print(f"warning: could not read {db}: {e}", file=sys.stderr)
    return index


def check(path, index):
    problems = []
    r = subprocess.run(["zstd", "-tq", str(path)], capture_output=True, text=True)
    if r.returncode != 0:
        problems.append("zstd integrity test failed: " + (r.stderr.strip().splitlines() or ["?"])[-1])
    expected = index.get(path.name)
    size = path.stat().st_size
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    if expected:
        want_sha, want_size, repo = expected
        if want_size is not None and size != want_size:
            problems.append(f"size {size} bytes, repo [{repo}] says {want_size}")
        if want_sha and sha != want_sha:
            problems.append(f"sha256 {sha}, repo [{repo}] says {want_sha}")
    return problems, sha, size, bool(expected)


def describe(path):
    """Cheap hints about what kind of damage it is."""
    data = path.read_bytes()
    zero_runs = len(re.findall(rb"\x00{4096,}", data))
    return (f"first bytes {data[:8].hex()} (zstd starts with 28b52ffd), "
            f"{zero_runs} run(s) of >=4 KiB of zero bytes, modified {time.ctime(path.stat().st_mtime)}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cache")
    ap.add_argument("--dbpath", default="/var/lib/pacman")
    ap.add_argument("--quarantine")
    args = ap.parse_args()
    cache = Path(args.cache)
    index = repo_index(args.dbpath)
    files = sorted(cache.glob("*.pkg.tar.zst"))
    bad, known = [], 0
    for f in files:
        problems, sha, size, in_db = check(f, index)
        known += in_db
        if problems:
            bad.append((f, problems, describe(f)))
    print(f"verified {len(files)} packages in {cache} ({known} against the repo database): {len(bad)} damaged")
    if not bad:
        return 0
    report = []
    for f, problems, hint in bad:
        report.append(f"{f.name}\n  " + "\n  ".join(problems) + f"\n  {hint}")
        print("DAMAGED " + report[-1])
    if args.quarantine:
        q = Path(args.quarantine) / time.strftime("%Y%m%d-%H%M%S")
        q.mkdir(parents=True, exist_ok=True)
        for f, _, _ in bad:
            shutil.move(str(f), q / f.name)
            sig = f.with_name(f.name + ".sig")
            if sig.exists():
                shutil.move(str(sig), q / sig.name)
        (q / "REPORT.txt").write_text("Damaged packages moved here instead of being deleted.\n\n"
                                      + "\n\n".join(report) + "\n")
        print(f"moved {len(bad)} damaged file(s) to {q} (see REPORT.txt)")
    return 1


if __name__ == "__main__":
    sys.exit(main())
