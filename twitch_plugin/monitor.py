"""Poll, cache and notification transition logic."""
import fcntl
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from .browser import find_twitch_token, stored_token
from .providers import ProviderError, TwitchGQLProvider, TwitchHelixProvider
from .storage import ROOT, config, follows, read_json, write_json


def normalize_channels(channels):
    seen, result = set(), []
    for item in channels:
        if not isinstance(item, str):
            continue
        login = item.strip().lstrip("@").lower()
        if login.startswith("https://www.twitch.tv/"):
            login = login.split("/", 3)[-1]
        if login.startswith("https://twitch.tv/"):
            login = login.split("/", 3)[-1]
        if re.fullmatch(r"[a-z0-9_]{1,25}", login) and login not in seen:
            seen.add(login)
            result.append(login)
    return result


def _notify(stream):
    helper = Path(__file__).resolve().parent.parent / "bin" / "omarchy-twitch"
    try:
        subprocess.Popen(
            [sys.executable, str(helper), "notification-open", stream["login"], stream["display_name"], stream["game"], stream["title"]],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        pass


def _snapshot(state, cfg, error="", stale=False):
    return {
        "streams": state.get("streams", []),
        "follows": state.get("follows", follows()),
        "checked_at": state.get("checked_at", 0),
        "source": state.get("source", ""),
        "warning": state.get("warning", ""),
        "twitch_notifications": state.get("twitch_notifications", {}),
        "error": error,
        "stale": stale,
        "config": cfg,
    }


def notification_enabled(login, cfg, twitch_notifications):
    overrides = cfg.get("notification_overrides") or {}
    if login in overrides:
        return overrides[login]
    if cfg.get("match_twitch_notifications"):
        return twitch_notifications.get(login, False)
    return cfg.get("notify_all", True)


def poll(force=False):
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(ROOT, 0o700)
    with (ROOT / "poll.lock").open("a+") as lock:
        os.chmod(ROOT / "poll.lock", 0o600)
        fcntl.flock(lock, fcntl.LOCK_EX)
        cfg = config()
        state = read_json("state.json", {})
        if not force and time.time() - state.get("checked_at", 0) < cfg["poll_interval"]:
            return _snapshot(state, cfg)

        mode = cfg["mode"]
        saved_follows = normalize_channels(follows())
        token_source = ""
        warning = ""
        twitch_notifications = {}
        live_lookup = "channels"
        try:
            if mode == "helix":
                provider = TwitchHelixProvider(cfg.get("client_id", ""), stored_token())
                channels = normalize_channels(provider.get_followed_channels())
                streams = provider.get_live_streams()
                source = "Helix OAuth"
                if cfg.get("match_twitch_notifications"):
                    warning = "Twitch notification matching needs a browser session or web session token; unknown channels will stay quiet."
            else:
                session = None
                if mode == "auto":
                    session = find_twitch_token()
                elif mode == "token":
                    token = stored_token()
                    session = (token, "manual token") if token else None
                if session:
                    provider = TwitchGQLProvider(session[0])
                    token_source = session[1]
                    source = token_source
                    try:
                        channels = normalize_channels(provider.get_followed_channels())
                        warning = provider.warning
                        if warning:
                            channels = normalize_channels([*channels, *saved_follows])
                    except ProviderError:
                        channels = saved_follows
                        warning = "Browser follow sync failed; showing the last saved list in Settings."
                    try:
                        streams = provider.get_live_followed_streams()
                        live_lookup = "followed_live"
                    except ProviderError:
                        if not channels:
                            raise
                        streams = TwitchGQLProvider().get_live_streams(channels)
                        source = "saved channels"
                        warning = (warning + " " if warning else "") + "Live-follow refresh failed; checking saved channels instead."
                    channels = normalize_channels([*channels, *(stream["login"] for stream in streams)])
                    write_json("follows.json", {"channels": channels})
                else:
                    provider = TwitchGQLProvider()
                    channels = saved_follows
                    source = "saved channels" if channels else "none"
                    warning = ""
                    streams = provider.get_live_streams(channels)
                if cfg.get("match_twitch_notifications"):
                    if provider.token:
                        try:
                            twitch_notifications = provider.get_notification_preferences(
                                [stream["login"] for stream in streams]
                            )
                        except ProviderError:
                            warning = (warning + " " if warning else "") + "Could not read Twitch notification preferences; unknown channels will stay quiet."
                    else:
                        warning = (warning + " " if warning else "") + "Twitch notification matching needs a readable browser session or session token; unknown channels will stay quiet."
                if mode == "token" and not session:
                    raise ProviderError("No saved Twitch token; add one or select another mode")
                if mode == "auto" and not session and not channels:
                    raise ProviderError("No readable Twitch browser session; import or add channels")

            current_ids = {stream["id"] or stream["login"] for stream in streams}
            same_source = state.get("source") == source and state.get("live_lookup", "channels") == live_lookup
            if cfg.get("notifications", True) and state.get("checked_at") and same_source:
                previous = set(state.get("live_ids", []))
                for stream in streams:
                    key = stream["id"] or stream["login"]
                    enabled = notification_enabled(stream["login"], cfg, twitch_notifications)
                    if key not in previous and enabled:
                        _notify(stream)
            state = {
                "streams": streams,
                "follows": channels,
                "source": source,
                "live_lookup": live_lookup,
                "warning": warning,
                "twitch_notifications": twitch_notifications,
                "live_ids": sorted(current_ids),
                "checked_at": int(time.time()),
            }
            write_json("state.json", state)
            return _snapshot(state, cfg)
        except (ProviderError, RuntimeError) as error:
            return _snapshot(state, cfg, str(error), stale=True)
