import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from ccsl import installer, paths
from tests.helpers import Sandbox

ROOT = Path(__file__).resolve().parent.parent


class TestInstaller(Sandbox):
    def settings(self):
        return json.loads(paths.settings_file().read_text(encoding="utf-8"))

    def install(self, **kw):
        with mock.patch.object(installer, "bin_dir", lambda: self.home / ".local" / "bin"):
            plan, warnings = installer.install(ROOT, **kw)
            plan.run(False)
        return warnings

    def uninstall(self):
        with mock.patch.object(installer, "bin_dir", lambda: self.home / ".local" / "bin"):
            installer.uninstall().run(False)

    def test_only_the_statusline_key_is_written_and_a_backup_kept(self):
        paths.settings_file().write_text('{"theme": "dark", "model": "opus"}', encoding="utf-8")
        self.install()
        data = self.settings()
        self.assertEqual((data["theme"], data["model"]), ("dark", "opus"))
        self.assertIn("run.py", data["statusLine"]["command"])
        self.assertTrue(list(self.claude.glob("settings.json.bak-*")))

    def test_a_foreign_status_line_is_kept_unless_forced_and_restored_later(self):
        foreign = {"type": "command", "command": "mine.sh"}
        paths.settings_file().write_text(json.dumps({"statusLine": foreign}), encoding="utf-8")
        warnings = self.install()
        self.assertEqual(self.settings()["statusLine"], foreign)
        self.assertTrue(warnings)
        self.install(force=True)
        self.assertNotEqual(self.settings()["statusLine"], foreign)
        self.install()                       # a second run keeps the memory
        self.uninstall()
        self.assertEqual(self.settings()["statusLine"], foreign)

    def test_dry_run_changes_nothing(self):
        with mock.patch.object(installer, "bin_dir", lambda: self.home / ".local" / "bin"):
            plan, _ = installer.install(ROOT, choices={"theme": "traffic"})
            lines = plan.run(True)
        self.assertTrue(lines)
        self.assertFalse(paths.settings_file().exists())
        self.assertFalse(paths.data_dir().exists())

    def test_uninstall_removes_only_our_things_and_keeps_data(self):
        self.install(choices={"cost_tracking": True})
        foreign = self.home / ".local" / "bin" / "other"
        foreign.write_text("x", encoding="utf-8")
        self.uninstall()
        self.assertNotIn("statusLine", self.settings())
        self.assertFalse((self.home / ".local" / "bin" / "claude-costs").exists())
        self.assertTrue(foreign.exists())
        self.assertTrue((paths.data_dir() / "config.json").exists())

    def test_broken_settings_are_left_alone(self):
        paths.settings_file().write_text("{nope", encoding="utf-8")
        with self.assertRaises(ValueError):
            installer.install(ROOT)

    def test_launcher_runs_the_line_and_never_fails(self):
        self.install()
        run = paths.data_file("run.py")
        out = subprocess.run([sys.executable, str(run), "statusline"], input="{}",
                             capture_output=True, text=True, timeout=60,
                             env=dict(os.environ, CCSL_LIVE_LOOKUP="0"))
        self.assertEqual(out.returncode, 0)
        paths.data_file("install.json").write_text('{"code": "/nowhere"}', encoding="utf-8")
        out = subprocess.run([sys.executable, str(run), "statusline"], input="{}",
                             capture_output=True, text=True, timeout=60)
        self.assertEqual((out.returncode, out.stderr), (0, ""))

    def test_launcher_prefers_the_newest_plugin_version(self):
        self.install(mode="plugin")
        for version in ("1.0.0", "1.10.0", "1.9.2"):
            folder = self.claude / "plugins" / "cache" / "milhero" / "calm-statusline" / version
            folder.mkdir(parents=True)
            (folder / "statusline.py").write_text(
                "print('version {}')\n".format(version), encoding="utf-8")
        out = subprocess.run([sys.executable, str(paths.data_file("run.py")), "statusline"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.stdout.strip(), "version 1.10.0")

    def test_install_script_help_installs_nothing(self):
        out = subprocess.run([sys.executable, str(ROOT / "install.py"), "--help"],
                             capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0)
        self.assertIn("--dry-run", out.stdout)
        self.assertFalse(paths.settings_file().exists())

    def test_version_check(self):
        self.assertTrue(installer.version_at_least("2.1.300 (Claude Code)", (2, 1, 251)))
        self.assertFalse(installer.version_at_least("2.0", (2, 1, 251)))
        self.assertIsNone(installer.version_at_least("dev", (2, 1, 251)))


if __name__ == "__main__":
    unittest.main()
