import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from twitch_plugin import cli, storage


class StorageCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "config"
        root_patch = patch.object(storage, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def run_cli(self, *args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = cli.main(list(args))
        return status, json.loads(output.getvalue())

    def test_store_uses_private_permissions_and_recovers_from_invalid_json(self):
        storage.write_json("config.json", {"mode": "manual"})
        self.assertEqual(self.root.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.root / "config.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual(storage.config()["mode"], "manual")
        self.assertEqual(storage.config()["poll_interval"], storage.DEFAULT_CONFIG["poll_interval"])
        (self.root / "config.json").write_text("{broken", encoding="utf-8")
        self.assertEqual(storage.config(), storage.DEFAULT_CONFIG)

    def test_follow_add_remove_and_import_normalize_channels(self):
        self.assertEqual(self.run_cli("follow", "add", "@Alpha"), (0, {"channels": ["alpha"]}))
        self.assertEqual(self.run_cli("follow", "add", "https://twitch.tv/Beta"),
                         (0, {"channels": ["alpha", "beta"]}))
        self.assertEqual(self.run_cli("follow", "remove", "ALPHA"), (0, {"channels": ["beta"]}))
        export = self.root / "export.json"
        export.write_text(json.dumps({"channels": ["@Gamma", "gamma", "bad/path", "beta"]}), encoding="utf-8")
        self.assertEqual(self.run_cli("follow", "import", str(export)),
                         (0, {"channels": ["gamma", "beta"]}))

    def test_invalid_import_preserves_existing_follows(self):
        storage.write_json("follows.json", {"channels": ["alpha"]})
        export = self.root / "export.json"
        export.write_text(json.dumps({"channels": ["bad/path"]}), encoding="utf-8")
        status, result = self.run_cli("follow", "import", str(export))
        self.assertEqual(status, 1)
        self.assertIn("no valid channel", result["error"])
        self.assertEqual(storage.follows(), ["alpha"])

    def test_invalid_setting_does_not_change_config(self):
        for key, value in (("mode", "unknown"), ("poll_interval", "59"),
                           ("notifications", "yes")):
            with self.subTest(key=key):
                status, result = self.run_cli("set", key, value)
                self.assertEqual(status, 1)
                self.assertIn("error", result)
                self.assertFalse((self.root / "config.json").exists())

    def test_notification_override_can_be_reset(self):
        self.assertEqual(self.run_cli("notify-channel", "@Alpha", "off")[1]
                         ["notification_overrides"], {"alpha": False})
        self.assertEqual(self.run_cli("notify-channel", "alpha", "default")[1]
                         ["notification_overrides"], {})


if __name__ == "__main__":
    unittest.main()
