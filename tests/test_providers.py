import unittest
from unittest.mock import patch

from twitch_plugin.providers import ProviderError, TwitchGQLProvider


class ProviderTests(unittest.TestCase):
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
