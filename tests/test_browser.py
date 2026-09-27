import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from twitch_plugin import browser


class BrowserTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.home = Path(temporary.name)

    def test_firefox_reads_only_twitch_auth_cookie(self):
        db = self.home / ".mozilla/firefox/profile/cookies.sqlite"
        db.parent.mkdir(parents=True)
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("CREATE TABLE moz_cookies (name TEXT, host TEXT, value TEXT, lastAccessed INTEGER)")
            connection.executemany("INSERT INTO moz_cookies VALUES (?, ?, ?, ?)", [
                ("auth-token", ".evil.twitch.tv", "wrong-host", 5),
                ("other", ".twitch.tv", "wrong-name", 4),
                ("auth-token", ".twitch.tv", "older", 2),
                ("auth-token", "www.twitch.tv", "newer", 3),
            ])
            connection.commit()
        self.assertEqual(browser._firefox_token(self.home), ("newer", "Firefox (profile)"))

    def test_chromium_plain_cookie_and_profile_fallback(self):
        root = self.home / ".config/chromium"
        default = root / "Default/Network/Cookies"
        default.parent.mkdir(parents=True)
        default.write_text("not a database", encoding="utf-8")
        db = root / "Profile 1/Network/Cookies"
        db.parent.mkdir(parents=True)
        with closing(sqlite3.connect(db)) as connection:
            connection.execute("CREATE TABLE cookies (name TEXT, host_key TEXT, value TEXT, encrypted_value BLOB, last_access_utc INTEGER)")
            connection.executemany("INSERT INTO cookies VALUES (?, ?, ?, ?, ?)", [
                ("auth-token", "unrelated.example", "wrong", b"", 10),
                ("auth-token", ".twitch.tv", "right", b"", 1),
            ])
            connection.commit()
        with patch.object(browser, "_secret_for_browser", return_value=b""):
            self.assertEqual(browser._chromium_token(self.home), ("right", "Chromium (Profile 1)"))

    def test_environment_token_takes_precedence_over_secret_service(self):
        with patch.dict("os.environ", {"OMARCHY_TWITCH_TOKEN": " env-token "}), \
                patch.object(browser.subprocess, "run") as run:
            self.assertEqual(browser.stored_token(), "env-token")
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
