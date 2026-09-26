"""Read only Twitch's auth-token cookie from supported local browser profiles.

Chromium's Linux v10/v11 AES-CBC format is supported. Newer app-bound formats
cannot be decrypted here; users can use the export or manual-token modes.
"""
import hashlib
import os
import sqlite3
import subprocess
from pathlib import Path


def _firefox_token(home):
    roots = [home / ".mozilla/firefox", home / ".var/app/org.mozilla.firefox/.mozilla/firefox"]
    for root in roots:
        for db in sorted(root.glob("*/cookies.sqlite")):
            try:
                connection = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=1)
                try:
                    rows = connection.execute(
                        "SELECT value FROM moz_cookies WHERE name = ? AND host IN (?, ?, ?) ORDER BY lastAccessed DESC",
                        ("auth-token", "twitch.tv", ".twitch.tv", "www.twitch.tv"),
                    ).fetchall()
                finally:
                    connection.close()
                if rows and rows[0][0]:
                    return rows[0][0], f"Firefox ({db.parent.name})"
            except (OSError, sqlite3.Error):
                continue
    return None


def _secret_for_browser(application):
    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "application", application],
            capture_output=True, timeout=3, check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else b""
    except (OSError, subprocess.TimeoutExpired):
        return b""


def _decrypt_chromium(value, secret):
    if not isinstance(value, bytes) or value[:3] not in (b"v10", b"v11"):
        return ""
    password = b"peanuts" if value[:3] == b"v10" else secret
    if not password:
        return ""
    key = hashlib.pbkdf2_hmac("sha1", password, b"saltysalt", 1, 16)
    try:
        result = subprocess.run(
            ["openssl", "enc", "-d", "-aes-128-cbc", "-K", key.hex(), "-iv", (b" " * 16).hex()],
            input=value[3:], capture_output=True, timeout=3, check=False,
        )
        if result.returncode:
            return ""
        decoded = result.stdout
        # Chromium schema v24 prefixes encrypted cookies with SHA256(host).
        if decoded.startswith(hashlib.sha256(b".twitch.tv").digest()):
            decoded = decoded[32:]
        return decoded.decode("utf-8", "strict")
    except (OSError, subprocess.TimeoutExpired, UnicodeError):
        return ""


def _chromium_token(home):
    browsers = [
        ("Chrome", home / ".config/google-chrome", "chrome"),
        ("Chromium", home / ".config/chromium", "chromium"),
        ("Brave", home / ".config/BraveSoftware/Brave-Browser", "brave"),
    ]
    for label, root, application in browsers:
        if not root.exists():
            continue
        profiles = [root / "Default", *sorted(root.glob("Profile *"))]
        secret = _secret_for_browser(application)
        for profile in profiles:
            for db_path in (profile / "Network/Cookies", profile / "Cookies"):
                try:
                    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
                    try:
                        rows = connection.execute(
                            "SELECT value, encrypted_value FROM cookies WHERE name = ? AND host_key IN (?, ?, ?) ORDER BY last_access_utc DESC",
                            ("auth-token", "twitch.tv", ".twitch.tv", "www.twitch.tv"),
                        ).fetchall()
                    finally:
                        connection.close()
                    for plain, encrypted in rows:
                        token = plain or _decrypt_chromium(encrypted, secret)
                        if token:
                            return token, f"{label} ({profile.name})"
                except (OSError, sqlite3.Error):
                    continue
    return None


def find_twitch_token():
    home = Path.home()
    return _firefox_token(home) or _chromium_token(home)


def stored_token():
    token = os.environ.get("OMARCHY_TWITCH_TOKEN", "").strip()
    if token:
        return token
    try:
        result = subprocess.run(
            ["secret-tool", "lookup", "service", "omarchy-twitch", "account", "twitch"],
            capture_output=True, timeout=3, check=False, text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def save_token(token):
    try:
        result = subprocess.run(
            ["secret-tool", "store", "--label=Omarchy Twitch token", "service", "omarchy-twitch", "account", "twitch"],
            input=token + "\n", text=True, capture_output=True, timeout=10, check=False,
        )
        if result.returncode:
            raise RuntimeError("Could not store token in Secret Service")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError("Secret Service is unavailable") from error


def clear_token():
    try:
        subprocess.run(
            ["secret-tool", "clear", "service", "omarchy-twitch", "account", "twitch"],
            capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
