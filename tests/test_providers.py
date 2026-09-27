import unittest
from unittest.mock import patch

from twitch_plugin.providers import ProviderError, TwitchGQLProvider, TwitchHelixProvider, normalize_stream


class ProviderTests(unittest.TestCase):
    def test_transient_graphql_service_error_is_retried_once(self):
        provider = TwitchGQLProvider()
        with patch("twitch_plugin.providers.request_json", side_effect=[
            {"errors": [{"message": "service timeout"}]}, {"data": {"users": []}},
        ]) as request:
            self.assertEqual(provider._query("query Test { users { id } }"), {"users": []})
        self.assertEqual(request.call_count, 2)

    def test_graphql_preview_url_is_kept_with_stream(self):
        stream = normalize_stream({"id": "1", "login": "alpha"}, {
            "title": "Live", "viewersCount": 5, "previewImageURL": "https://static-cdn.jtvnw.net/preview.jpg",
        })
        self.assertEqual(stream["thumbnail_url"], "https://static-cdn.jtvnw.net/preview.jpg")

    def test_helix_preview_url_is_sized(self):
        provider = TwitchHelixProvider("client", "token")
        page = {"data": [{"user_id": "1", "user_login": "alpha", "thumbnail_url": "https://static-cdn.jtvnw.net/live-{width}x{height}.jpg"}]}
        with patch.object(provider, "get_user", return_value={"user_id": "viewer"}), \
                patch.object(provider, "_get", return_value=page):
            streams = provider.get_live_streams()
        self.assertEqual(streams[0]["thumbnail_url"], "https://static-cdn.jtvnw.net/live-320x180.jpg")

    def test_notification_preferences_use_followed_channels_only(self):
        provider = TwitchGQLProvider("placeholder-token")
        payload = {"users": [
            {"login": "Alpha", "self": {"follower": {"notificationSettings": {"isEnabled": True}}}},
            {"login": "beta", "self": {"follower": {"notificationSettings": {"isEnabled": False}}}},
            {"login": "other", "self": {"follower": None}},
        ]}
        with patch.object(provider, "_query", return_value=payload) as query:
            self.assertEqual(provider.get_notification_preferences(["alpha", "beta", "other"]),
                             {"alpha": True, "beta": False})
        self.assertIn("notificationSettings", query.call_args.args[0])

    def test_direct_live_follows_include_channels_outside_saved_page(self):
        provider = TwitchGQLProvider("placeholder-token")
        page = {"currentUser": {"followedLiveUsers": {
            "edges": [{"cursor": "one", "node": {"id": "1", "login": "new_follow", "stream": {
                "title": "Live", "viewersCount": 3, "previewImageURL": "https://cdn.example/preview.jpg",
            }}}],
            "pageInfo": {"hasNextPage": False},
        }}}
        with patch.object(provider, "_query", return_value=page):
            streams = provider.get_live_followed_streams()
        self.assertEqual([stream["login"] for stream in streams], ["new_follow"])
        self.assertEqual(streams[0]["thumbnail_url"], "https://cdn.example/preview.jpg")

    def test_browser_pagination_warning_preserves_first_page(self):
        provider = TwitchGQLProvider("placeholder-token")
        first_page = {
            "user": {"follows": {
                "edges": [{"cursor": "cursor-1", "node": {"login": "alpha"}}],
                "pageInfo": {"hasNextPage": True},
            }}
        }
        with patch.object(provider, "get_user", return_value={"login": "viewer"}), \
                patch.object(provider, "_query", side_effect=[first_page, ProviderError("failed integrity check")]):
            self.assertEqual(provider.get_followed_channels(), ["alpha"])
        self.assertIn("partial", provider.warning)


if __name__ == "__main__":
    unittest.main()
