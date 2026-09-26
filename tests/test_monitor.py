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


if __name__ == "__main__":
    unittest.main()
