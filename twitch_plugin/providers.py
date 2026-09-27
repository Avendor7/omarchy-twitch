"""Twitch-specific data providers. The web GraphQL API is unofficial."""
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

WEB_CLIENT_ID = "kimne78kx3ncx6brgo4mv6wki5h1ko"
GQL_URL = "https://gql.twitch.tv/gql"
HELIX_URL = "https://api.twitch.tv/helix"


class ProviderError(RuntimeError):
    pass


def request_json(url, headers=None, payload=None):
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, headers=headers or {}, method="POST" if body else "GET")
    try:
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except HTTPError as error:
        raise ProviderError(f"Twitch HTTP {error.code}") from error
    except (URLError, TimeoutError, ValueError) as error:
        raise ProviderError(f"Twitch request failed: {error}") from error


def validate_token(token):
    data = request_json("https://id.twitch.tv/oauth2/validate", {"Authorization": "OAuth " + token})
    if not data.get("login") or not data.get("user_id"):
        raise ProviderError("Twitch token has no user identity")
    return data


def normalize_stream(user, stream):
    return {
        "id": str(user.get("id", "")),
        "login": user.get("login", ""),
        "display_name": user.get("displayName") or user.get("login", ""),
        "title": stream.get("title", ""),
        "game": (stream.get("game") or {}).get("name", ""),
        "viewers": int(stream.get("viewersCount") or 0),
        "started_at": stream.get("createdAt", ""),
        "thumbnail_url": stream.get("previewImageURL") or "",
        "url": "https://www.twitch.tv/" + user.get("login", ""),
    }


class TwitchGQLProvider:
    def __init__(self, token=None):
        self.token = token
        self.integrity = None
        self.warning = ""

    def _integrity_token(self):
        if self.integrity:
            return self.integrity
        headers = {"Client-Id": WEB_CLIENT_ID, "Authorization": "OAuth " + self.token}
        request = Request("https://gql.twitch.tv/integrity", data=b"", headers=headers, method="POST")
        try:
            with urlopen(request, timeout=15) as response:
                self.integrity = json.load(response).get("token")
        except HTTPError as error:
            raise ProviderError(f"Twitch integrity HTTP {error.code}") from error
        except (URLError, TimeoutError, ValueError) as error:
            raise ProviderError(f"Twitch integrity request failed: {error}") from error
        if not self.integrity:
            raise ProviderError("Twitch did not issue an integrity token")
        return self.integrity

    def _query(self, query, variables=None):
        headers = {"Client-Id": WEB_CLIENT_ID, "Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = "OAuth " + self.token
            headers["Client-Integrity"] = self._integrity_token()
        for attempt in range(2):
            result = request_json(GQL_URL, headers, {"query": query, "variables": variables or {}})
            if result.get("errors"):
                message = str(result["errors"][0].get("message", "unknown error"))
                if attempt == 0 and message.lower() in ("service error", "service timeout"):
                    continue
                raise ProviderError("Twitch GraphQL: " + message)
            return result.get("data") or {}

    def get_user(self):
        if not self.token:
            return None
        return validate_token(self.token)

    def get_followed_channels(self):
        user = self.get_user()
        if not user:
            raise ProviderError("A Twitch session token is required to sync follows")
        query = """query TwitchFollows($login: String!, $after: Cursor) {
          user(login: $login) { follows(first: 100, after: $after) {
            edges { cursor node { id login displayName } }
            pageInfo { hasNextPage }
          } }
        }"""
        channels, after = [], None
        for _ in range(100):
            try:
                connection = ((self._query(query, {"login": user["login"], "after": after}).get("user") or {}).get("follows") or {})
            except ProviderError as error:
                if channels and "integrity" in str(error).lower():
                    self.warning = "Twitch blocked follow-list pagination; the saved follow list may be partial. Live follows are checked separately."
                    return channels
                raise
            edges = connection.get("edges") or []
            channels.extend(node["node"]["login"] for node in edges if node.get("node", {}).get("login"))
            if not (connection.get("pageInfo") or {}).get("hasNextPage"):
                return channels
            next_cursor = edges[-1].get("cursor") if edges else None
            if not next_cursor or next_cursor == after:
                raise ProviderError("Twitch follows pagination stopped unexpectedly")
            after = next_cursor
        raise ProviderError("Twitch follows pagination exceeded 10,000 channels")

    def get_live_streams(self, channels):
        query = """query TwitchLive($logins: [String!]!) {
          users(logins: $logins) { id login displayName
            stream { id title viewersCount createdAt previewImageURL(width: 320, height: 180) game { name } }
          }
        }"""
        streams = []
        for index in range(0, len(channels), 50):
            users = self._query(query, {"logins": channels[index:index + 50]}).get("users") or []
            streams.extend(normalize_stream(user, user["stream"]) for user in users if user and user.get("stream"))
        return sorted(streams, key=lambda item: item["viewers"], reverse=True)

    def get_live_followed_streams(self):
        """Fetch all live follows directly, without relying on follow-list pagination."""
        if not self.token:
            raise ProviderError("A Twitch session token is required for live follows")
        query = """query TwitchFollowedLive($after: Cursor) {
          currentUser { followedLiveUsers(first: 100, after: $after) {
            edges { cursor node { id login displayName
              stream { id title viewersCount createdAt previewImageURL(width: 320, height: 180) game { name } }
            } }
            pageInfo { hasNextPage }
          } }
        }"""
        streams, after = [], None
        for _ in range(100):
            account = self._query(query, {"after": after}).get("currentUser") or {}
            connection = account.get("followedLiveUsers")
            if not isinstance(connection, dict):
                raise ProviderError("Twitch did not return the signed-in live follows")
            edges = connection.get("edges") or []
            streams.extend(normalize_stream(node, node["stream"]) for edge in edges
                           if (node := edge.get("node")) and node.get("stream"))
            if not (connection.get("pageInfo") or {}).get("hasNextPage"):
                return sorted(streams, key=lambda item: item["viewers"], reverse=True)
            next_cursor = edges[-1].get("cursor") if edges else None
            if not next_cursor or next_cursor == after:
                raise ProviderError("Twitch live follows pagination stopped unexpectedly")
            after = next_cursor
        raise ProviderError("Twitch live follows pagination exceeded 10,000 channels")

    def get_notification_preferences(self, channels):
        """Read the signed-in viewer's per-follow notification switch for live channels."""
        if not self.token:
            raise ProviderError("A Twitch session token is required to match notifications")
        query = """query TwitchNotify($logins: [String!]!) {
          users(logins: $logins) { login self { follower {
            notificationSettings { isEnabled }
          } } }
        }"""
        preferences = {}
        for index in range(0, len(channels), 50):
            users = self._query(query, {"logins": channels[index:index + 50]}).get("users") or []
            for user in users:
                if not user or not user.get("login"):
                    continue
                settings = (((user.get("self") or {}).get("follower") or {}).get("notificationSettings") or {})
                if isinstance(settings.get("isEnabled"), bool):
                    preferences[user["login"].lower()] = settings["isEnabled"]
        return preferences


class TwitchHelixProvider:
    def __init__(self, client_id, token):
        if not client_id or not token:
            raise ProviderError("Helix needs a Client ID and user access token")
        self.client_id = client_id
        self.token = token

    def get_user(self):
        user = validate_token(self.token)
        if user.get("client_id") != self.client_id:
            raise ProviderError("The OAuth token belongs to a different Twitch Client ID")
        if "user:read:follows" not in user.get("scopes", []):
            raise ProviderError("OAuth token needs the user:read:follows scope")
        return user

    def _get(self, endpoint, params):
        url = HELIX_URL + endpoint + "?" + urlencode(params)
        return request_json(url, {"Client-Id": self.client_id, "Authorization": "Bearer " + self.token})

    def _pages(self, endpoint, user_id):
        after = None
        for _ in range(100):
            params = {"user_id": user_id, "first": 100}
            if after:
                params["after"] = after
            page = self._get(endpoint, params)
            yield page.get("data") or []
            cursor = (page.get("pagination") or {}).get("cursor")
            if not cursor or cursor == after:
                return
            after = cursor
        raise ProviderError("Twitch Helix pagination exceeded 10,000 items")

    def get_followed_channels(self):
        user_id = self.get_user()["user_id"]
        return [item["broadcaster_login"] for page in self._pages("/channels/followed", user_id)
                for item in page if item.get("broadcaster_login")]

    def get_live_streams(self, channels=None):
        user_id = self.get_user()["user_id"]
        streams = []
        for page in self._pages("/streams/followed", user_id):
            for item in page:
                login = item.get("user_login", "")
                streams.append({
                    "id": item.get("user_id", ""), "login": login,
                    "display_name": item.get("user_name") or login,
                    "title": item.get("title", ""), "game": item.get("game_name", ""),
                    "viewers": int(item.get("viewer_count") or 0),
                    "started_at": item.get("started_at", ""),
                    "thumbnail_url": (item.get("thumbnail_url") or "").replace("{width}", "320").replace("{height}", "180"),
                    "url": "https://www.twitch.tv/" + login,
                })
        return sorted(streams, key=lambda item: item["viewers"], reverse=True)
