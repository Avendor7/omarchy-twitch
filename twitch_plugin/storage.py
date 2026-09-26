"""Small private JSON store. No credentials are written here."""
import json
import os
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "omarchy-twitch"
DEFAULT_CONFIG = {
    "mode": "auto",
    "notifications": True,
    "poll_interval": 90,
    "notify_all": True,
    "notification_overrides": {},
    "client_id": "",
}


def path(name):
    return ROOT / name


def read_json(name, default):
    try:
        with path(name).open(encoding="utf-8") as stream:
            data = json.load(stream)
        return data if isinstance(data, type(default)) else default.copy()
    except (FileNotFoundError, ValueError, OSError):
        return default.copy()


def write_json(name, data):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)
    fd, temp = tempfile.mkstemp(prefix=".twitch-", dir=ROOT)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, path(name))
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def config():
    data = read_json("config.json", {})
    return {**DEFAULT_CONFIG, **data}


def follows():
    data = read_json("follows.json", {"channels": []})
    return data.get("channels", []) if isinstance(data.get("channels"), list) else []
