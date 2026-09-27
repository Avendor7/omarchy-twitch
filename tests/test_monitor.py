import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from twitch_plugin import monitor, storage


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.patches = [patch.object(storage, "ROOT", root), patch.object(monitor, "ROOT", root)]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)
        storage.write_json("config.json", {**storage.DEFAULT_CONFIG, "mode": "manual"})
        storage.write_json("follows.json", {"channels": ["alpha", "beta"]})

    def test_only_new_live_transition_notifies(self):
        alpha = {"id": "1", "login": "alpha", "display_name": "Alpha", "game": "Game", "title": "A", "viewers": 10, "started_at": "2026-01-01T00:00:00Z", "url": "https://www.twitch.tv/alpha"}
        beta = {**alpha, "id": "2", "login": "beta", "display_name": "Beta"}
        streams = iter([[alpha], [alpha, beta], [alpha, beta], [beta], [alpha, beta]])
        with patch.object(monitor, "TwitchGQLProvider") as provider, patch.object(monitor, "_notify") as notify:
            provider.return_value.get_live_streams.side_effect = lambda channels: next(streams)
            for _ in range(5):
                monitor.poll(force=True)
            self.assertEqual([call.args[0]["login"] for call in notify.call_args_list], ["beta", "alpha"])

    def test_failed_poll_keeps_previous_live_state(self):
        item = {"id": "1", "login": "alpha", "display_name": "Alpha", "game": "", "title": "", "viewers": 0, "started_at": "", "url": "https://www.twitch.tv/alpha"}
        with patch.object(monitor, "TwitchGQLProvider") as provider, patch.object(monitor, "_notify") as notify:
            provider.return_value.get_live_streams.side_effect = [[item], monitor.ProviderError("offline"), [item]]
            self.assertFalse(monitor.poll(force=True)["stale"])
            self.assertTrue(monitor.poll(force=True)["stale"])
            self.assertFalse(monitor.poll(force=True)["stale"])
            notify.assert_not_called()

    def test_channel_input_is_strict_and_deduplicated(self):
        self.assertEqual(monitor.normalize_channels(["@Alpha", "alpha", "https://twitch.tv/Beta", "bad/path", "été"]), ["alpha", "beta"])

    def test_twitch_matching_respects_switch_and_local_overrides(self):
        cfg = {"notify_all": True, "match_twitch_notifications": True,
               "notification_overrides": {"beta": True, "gamma": False}}
        twitch = {"alpha": True, "beta": False, "gamma": True, "delta": False}
        self.assertTrue(monitor.notification_enabled("alpha", cfg, twitch))
        self.assertTrue(monitor.notification_enabled("beta", cfg, twitch))
        self.assertFalse(monitor.notification_enabled("gamma", cfg, twitch))
        self.assertFalse(monitor.notification_enabled("delta", cfg, twitch))
        self.assertFalse(monitor.notification_enabled("unknown", cfg, twitch))
        cfg["match_twitch_notifications"] = False
        self.assertTrue(monitor.notification_enabled("unknown", cfg, twitch))

    def test_matching_reads_preferences_before_notifying_new_live_channels(self):
        cfg = {**storage.DEFAULT_CONFIG, "mode": "auto", "match_twitch_notifications": True}
        storage.write_json("config.json", cfg)
        alpha = {"id": "1", "login": "alpha", "display_name": "Alpha", "game": "", "title": "", "url": "https://www.twitch.tv/alpha"}
        beta = {**alpha, "id": "2", "login": "beta", "display_name": "Beta"}
        with patch.object(monitor, "find_twitch_token", return_value=("test-token", "browser")), \
                patch.object(monitor, "TwitchGQLProvider") as provider, \
                patch.object(monitor, "_notify") as notify:
            provider.return_value.get_followed_channels.return_value = ["alpha", "beta"]
            provider.return_value.warning = ""
            provider.return_value.get_live_followed_streams.side_effect = [[], [alpha, beta]]
            provider.return_value.get_notification_preferences.return_value = {"alpha": True, "beta": False}
            monitor.poll(force=True)
            snapshot = monitor.poll(force=True)
        self.assertEqual(snapshot["twitch_notifications"], {"alpha": True, "beta": False})
        self.assertEqual([call.args[0]["login"] for call in notify.call_args_list], ["alpha"])

    def test_direct_live_follows_survive_follow_sync_failure(self):
        storage.write_json("config.json", {**storage.DEFAULT_CONFIG, "mode": "auto"})
        live = {"id": "3", "login": "outside_page", "display_name": "Outside", "game": "", "title": "", "url": "https://www.twitch.tv/outside_page"}
        with patch.object(monitor, "find_twitch_token", return_value=("test-token", "browser")), \
                patch.object(monitor, "TwitchGQLProvider") as provider:
            provider.return_value.get_followed_channels.side_effect = monitor.ProviderError("service error")
            provider.return_value.get_live_followed_streams.return_value = [live]
            snapshot = monitor.poll(force=True)
        self.assertFalse(snapshot["stale"])
        self.assertEqual([stream["login"] for stream in snapshot["streams"]], ["outside_page"])
        self.assertIn("outside_page", storage.follows())

    def test_switch_to_direct_live_follows_sets_a_new_notification_baseline(self):
        storage.write_json("config.json", {**storage.DEFAULT_CONFIG, "mode": "auto"})
        storage.write_json("state.json", {"source": "browser", "checked_at": 1, "live_ids": ["1"]})
        live = {"id": "2", "login": "outside_page", "display_name": "Outside", "game": "", "title": "", "url": "https://www.twitch.tv/outside_page"}
        with patch.object(monitor, "find_twitch_token", return_value=("test-token", "browser")), \
                patch.object(monitor, "TwitchGQLProvider") as provider, \
                patch.object(monitor, "_notify") as notify:
            provider.return_value.warning = ""
            provider.return_value.get_followed_channels.return_value = ["alpha"]
            provider.return_value.get_live_followed_streams.return_value = [live]
            monitor.poll(force=True)
        notify.assert_not_called()


if __name__ == "__main__":
    unittest.main()
