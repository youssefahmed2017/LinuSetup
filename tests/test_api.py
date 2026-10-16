import json
import os
import subprocess
import sys
import tempfile
import time
import unittest

from linusetup.api import Api
from linusetup.installer import config as CFG
from linusetup.installer.fixtures import FixtureSystem
from tests.helpers import cfg, PW, LUKS


def fps(api):
    return {d["path"]: d["fingerprint"] for d in api.disks()}


def wait_done(api, timeout=20):
    seen, t0 = 0, time.time()
    events = []
    while time.time() - t0 < timeout:
        r = api.poll(seen)
        for ev in r["events"]:
            events.append(ev)
            seen = ev["seq"] + 1
            if ev["type"] in ("done", "error"):
                return events
        time.sleep(0.02)
    raise AssertionError("install did not finish")


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.api = Api(FixtureSystem(), speed=0)

    def test_bootstrap(self):
        b = self.api.bootstrap()
        self.assertTrue(b["dry_run"])
        self.assertTrue(b["fixture"])
        self.assertIn("kde", [p["id"] for p in b["catalog"]["profiles"]])
        self.assertIn("UTC", b["timezones"])
        json.dumps(b)

    def test_disks_are_json_and_fingerprinted(self):
        ds = self.api.disks()
        json.dumps(ds)
        win = next(d for d in ds if d["path"] == "/dev/nvme0n1")
        self.assertTrue(win["has_windows"])
        self.assertTrue(win["free"])
        self.assertEqual(len(win["fingerprint"]), 16)

    def test_check_reports_by_section(self):
        c = cfg()
        c["users"] = []
        res = self.api.check(c)
        self.assertIn("users", {e["section"] for e in res["errors"]})
        res = self.api.check(cfg())
        self.assertEqual(res["errors"], [])
        self.assertEqual(res["bootloader"], "systemd-boot")
        self.assertTrue(res["layout"])
        json.dumps(res)

    def test_check_shrink_uses_ntfs_minimum(self):
        c = cfg(disk__device="/dev/nvme0n1", disk__scope="shrink",
                disk__shrink={"partition": "/dev/nvme0n1p3", "free_gb": 400})
        res = self.api.check(c)
        self.assertTrue(any("Windows needs" in e["message"] for e in res["errors"]))

    def test_full_dry_install(self):
        res = self.api.start_install(cfg(), fps(self.api))
        self.assertTrue(res["ok"], res)
        events = wait_done(self.api)
        self.assertEqual(events[-1]["type"], "done")
        self.assertEqual(events[0]["type"], "plan")
        self.assertNotIn(PW, json.dumps(events))

    def test_stale_disks_refused(self):
        stale = fps(self.api)
        stale["/dev/sda"] = "0" * 16
        res = self.api.start_install(cfg(), stale)
        self.assertFalse(res["ok"])
        self.assertTrue(res.get("stale"))

    def test_invalid_config_refused(self):
        c = cfg()
        c["users"][0]["username"] = "Bad Name"
        res = self.api.start_install(c, fps(self.api))
        self.assertFalse(res["ok"])

    def test_export_strips_secrets_and_import_roundtrips(self):
        c = cfg(disk__encryption={"enabled": True, "passphrase": LUKS}, root={"password": "x", "lock": False})
        text = self.api.export_config(c)["text"]
        self.assertNotIn(PW, text)
        self.assertNotIn(LUKS, text)
        back = self.api.import_config(text)
        self.assertTrue(back["ok"])
        self.assertEqual(back["config"]["disk"]["device"], "/dev/sda")
        self.assertFalse(self.api.import_config("{nope")["ok"])
        self.assertFalse(self.api.import_config('{"version": 99}')["ok"])
        self.assertFalse(self.api.import_config('{"users": "x"}')["ok"])

    def test_preview(self):
        res = self.api.preview(cfg())
        self.assertTrue(res["ok"])
        allcmds = " ".join(c for s in res["steps"] for c in s["commands"])
        self.assertIn("pacstrap", allcmds)
        self.assertNotIn(PW, allcmds)

    def test_wifi_and_search(self):
        self.assertFalse(self.api.wifi_connect("wlan0", "Home-5G", "nope")["ok"])
        self.assertTrue(self.api.wifi_connect("wlan0", "Home-5G", "password123")["ok"])
        self.assertEqual(self.api.network()["connected"], "Home-5G")
        self.assertEqual(self.api.search_packages("h")[:1], [])      # too short
        self.assertTrue(self.api.search_packages("htop"))
        self.assertEqual(self.api.search_packages("rm -rf"), [])    # not a package name


class WaitOnline(unittest.TestCase):
    def test_waits_until_online(self):
        from linusetup.api import wait_online

        class Slow:
            calls = 0

            def online(self):
                self.calls += 1
                return self.calls > 3
        clock = [0.0]
        s = Slow()
        ok = wait_online(s, timeout=180, interval=5, log=lambda m: None,
                         sleep=lambda x: clock.__setitem__(0, clock[0] + x), now=lambda: clock[0])
        self.assertTrue(ok)
        self.assertEqual(s.calls, 4)

    def test_gives_up(self):
        from linusetup.api import wait_online

        class Never:
            def online(self):
                return False
        clock = [0.0]
        ok = wait_online(Never(), timeout=30, interval=5, log=lambda m: None,
                         sleep=lambda x: clock.__setitem__(0, clock[0] + x), now=lambda: clock[0])
        self.assertFalse(ok)
        self.assertGreaterEqual(clock[0], 30)


class Cli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "linusetup", *args], capture_output=True, text=True,
                              cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def test_plan_check_and_auto_dry_run(self):
        c = cfg()
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(c, f)
        try:
            r = self.run_cli("check", f.name, "--fixtures")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            r = self.run_cli("plan", f.name, "--fixtures")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("pacstrap -K /mnt", r.stdout)
            self.assertNotIn(PW, r.stdout)
        finally:
            os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
