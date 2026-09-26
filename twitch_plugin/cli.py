"""CLI called by the Quickshell widget and available to users."""
import argparse
import getpass
import json
import subprocess
import sys
from pathlib import Path

from .browser import clear_token, save_token, stored_token
from .monitor import normalize_channels, poll
from .storage import config, follows, write_json

MODES = ("auto", "manual", "import", "token", "helix")


def _set_config(key, value):
    data = config()
    if key == "mode":
        if value not in MODES:
            raise ValueError("mode must be auto, manual, import, token, or helix")
        data[key] = value
    elif key in ("notifications", "notify_all", "match_twitch_notifications"):
        if value not in ("true", "false"):
            raise ValueError("value must be true or false")
        data[key] = value == "true"
    elif key == "poll_interval":
        seconds = int(value)
        if not 60 <= seconds <= 900:
            raise ValueError("poll interval must be 60–900 seconds")
        data[key] = seconds
    elif key == "client_id":
        if not value.isalnum() or len(value) > 100:
            raise ValueError("invalid Twitch Client ID")
        data[key] = value
    else:
        raise ValueError("unknown configuration setting")
    write_json("config.json", data)
    return data


def _update_follows(action, value):
    old = normalize_channels(follows())
    if action == "add":
        updated = normalize_channels([*old, value])
    elif action == "remove":
        updated = [login for login in old if login not in normalize_channels([value])]
    else:
        with Path(value).expanduser().open(encoding="utf-8") as stream:
            data = json.load(stream)
        entries = data.get("channels") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise ValueError("export must contain a channels array")
        updated = normalize_channels(entries)
        if not updated and entries:
            raise ValueError("export had no valid channel logins")
    write_json("follows.json", {"channels": updated})
    return updated


def _notify_open(login, display_name, game, title):
    if normalize_channels([login]) != [login]:
        return 2
    body = ("Playing " + game + "\n" if game else "") + title
    try:
        result = subprocess.run(
            ["notify-send", "--app-name=Omarchy Twitch", "--icon=video-display",
             "--action=default=Open stream", "--wait", display_name + " is live", body],
            capture_output=True, text=True, timeout=60, check=False,
        )
        if result.returncode == 0 and result.stdout.strip() == "default":
            subprocess.Popen(["xdg-open", "https://www.twitch.tv/" + login],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
    except (OSError, subprocess.TimeoutExpired):
        pass
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Omarchy Twitch helper")
    commands = parser.add_subparsers(dest="command", required=True)
    p_poll = commands.add_parser("poll", help="refresh live streams and output a JSON snapshot")
    p_poll.add_argument("--force", action="store_true")
    p_set = commands.add_parser("set", help="change a setting")
    p_set.add_argument("key")
    p_set.add_argument("value")
    p_follow = commands.add_parser("follow", help="manage saved channel list")
    p_follow.add_argument("action", choices=("add", "remove", "import"))
    p_follow.add_argument("value")
    p_override = commands.add_parser("notify-channel", help="set per-channel notification override")
    p_override.add_argument("login")
    p_override.add_argument("value", choices=("on", "off", "default"))
    p_auth = commands.add_parser("auth", help="manage token in Secret Service")
    p_auth.add_argument("action", choices=("set", "clear", "status"))
    p_notify = commands.add_parser("notification-open", help=argparse.SUPPRESS)
    p_notify.add_argument("login")
    p_notify.add_argument("display_name")
    p_notify.add_argument("game")
    p_notify.add_argument("title")
    args = parser.parse_args(argv)
    try:
        if args.command == "poll":
            result = poll(args.force)
        elif args.command == "set":
            result = _set_config(args.key, args.value)
        elif args.command == "follow":
            result = {"channels": _update_follows(args.action, args.value)}
        elif args.command == "notify-channel":
            channels = normalize_channels([args.login])
            if not channels:
                raise ValueError("invalid channel login")
            data = config()
            overrides = data.get("notification_overrides") or {}
            if args.value == "default":
                overrides.pop(channels[0], None)
            else:
                overrides[channels[0]] = args.value == "on"
            data["notification_overrides"] = overrides
            write_json("config.json", data)
            result = data
        elif args.command == "auth":
            if args.action == "set":
                token = getpass.getpass("Twitch token: ") if sys.stdin.isatty() else sys.stdin.readline().strip()
                if not token or len(token) > 4096:
                    raise ValueError("missing or invalid token")
                save_token(token)
                result = {"stored": True}
            elif args.action == "clear":
                clear_token()
                result = {"stored": False}
            else:
                result = {"stored": bool(stored_token())}
        elif args.command == "notification-open":
            return _notify_open(args.login, args.display_name, args.game, args.title)
        else:
            return 2
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(json.dumps({"error": str(error)}))
        return 1
