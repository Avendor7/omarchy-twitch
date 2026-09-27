# Omarchy Twitch Following

A Quickshell bar widget for Omarchy that shows followed Twitch channels that are live. The panel shows each stream's thumbnail, title, category, viewer count and uptime. Click a row to open Twitch in your browser. It can notify you when a channel goes live.

The plugin works with a manual or exported channel list and **does not require a Twitch developer application** for those modes. Browser session sync is the default when a readable Twitch session is available. An optional Helix mode supports your own Twitch Client ID and OAuth user token.

## Requirements

- Omarchy with Quickshell plugin support
- Python 3.10 or newer
- `notify-send` for desktop notifications
- `secret-tool` for storing a manually supplied token, or for Chromium's Secret Service cookie encryption
- `openssl` for reading Chromium-family encrypted cookies

The widget itself and manual/export modes use Python's standard library. It does not run an installer or request `sudo`.

## Install

```bash
omarchy plugin add https://github.com/Avendor7/omarchy-twitch.git --enable
```

Omarchy places the widget on the right side of the bar by default. Click the purple dot and count to open the panel. Middle-click refreshes. The first successful poll establishes a baseline, so channels already live when you enable the plugin do not all generate notifications.

If you cannot see a bar widget after enabling it, restart the shell with `omarchy restart shell`.

## Choose a follow source

Open the widget's **Settings** tab and choose one of these modes:

| Mode | How it gets follows | Credentials in plugin files? |
| --- | --- | --- |
| Browser auto (default) | Reads the Twitch `auth-token` cookie from local Firefox, Chrome, Chromium, or Brave profiles and syncs follows | No |
| Manual list | Uses channel names you add in Settings or through the CLI | No |
| Export file | Imports a JSON file downloaded by the provided browser script | No |
| Session token | Uses a token you enter in a terminal, kept in Secret Service | No |
| Helix OAuth | Uses your own Client ID and OAuth user token with `user:read:follows` | No |

Browser auto supports Firefox's cookie database and Chromium's Linux `v10`/`v11` AES-CBC cookie formats. Some newer browser profiles use a different encrypted format or have a locked keyring. In that case, choose the export or manual-list mode. Auto mode uses the last saved follow list if a browser session becomes unreadable.

Twitch currently rejects some GraphQL follow-list pagination requests with an integrity error. If your account has more than 100 follows, browser auto may save only the first page of offline channels. The panel warns when this happens and keeps channels already in your saved list. Live channels are fetched through Twitch's separate signed-in live-follows query, so they can still appear even when the saved list is partial. The browser exporter can also stop with that error. For a complete saved follow list, use Helix OAuth; a manual list remains usable without a developer application.

### Add channels manually

Enter a Twitch login in the Settings tab, or run:

```bash
~/.config/omarchy/plugins/avendor7.twitch/bin/omarchy-twitch set mode manual
~/.config/omarchy/plugins/avendor7.twitch/bin/omarchy-twitch follow add cohhcarnage
```

You can remove a channel with `follow remove <login>`. Saved follows live in `~/.config/omarchy-twitch/follows.json`.

### Export follows from your browser

1. Sign in to Twitch and open its Following page.
2. Open your browser's developer console on that page.
3. Inspect and run [browser-export/export-follows.js](browser-export/export-follows.js).
4. Import the downloaded `twitch-follows.json` in the Settings tab, then select **Export file**.

The script reads your browser's Twitch session inside the browser, requests your follows from Twitch, and downloads a JSON file containing only channel logins. The plugin never receives the session token in this mode. You can also import a hand-written file:

```json
{"channels":["lirik","cohhcarnage","northernlion"]}
```

For CLI import:

```bash
~/.config/omarchy/plugins/avendor7.twitch/bin/omarchy-twitch follow import ~/Downloads/twitch-follows.json
```

### Use a manually supplied session token

Select **Session token** in Settings. Obtain your Twitch `auth-token` from your own browser's developer tools, then run:

```bash
~/.config/omarchy/plugins/avendor7.twitch/bin/omarchy-twitch auth set
```

The helper prompts without echoing the token and stores it in Secret Service. `auth status` reports whether a token exists; `auth clear` removes it. Do not put a token on a shell command line, in `config.json`, or in an issue report. A memory-only option is `OMARCHY_TWITCH_TOKEN` in the shell process environment; it is never persisted by this plugin.

### Use official Twitch Helix

This mode is for users who already have a Twitch developer application. Select **Helix OAuth**, enter your application's Client ID in Settings, and store an OAuth **user** access token with `auth set`. The token must be issued to the same Client ID and include the `user:read:follows` scope. The plugin validates the token and uses [Get Followed Channels](https://dev.twitch.tv/docs/api/reference/#get-followed-channels) and [Get Followed Streams](https://dev.twitch.tv/docs/api/reference/#get-followed-streams). Twitch's [authentication guide](https://dev.twitch.tv/docs/authentication/) describes how to get a user token for your application. The plugin does not register an application or request a client secret.

## Notifications and settings

The helper polls every 90 seconds by default; the Settings tab offers 60, 90, 120, 180 and 300 seconds. Notifications are sent only when a channel changes from offline to live after a successful earlier poll. A failed request keeps the last successful state and does not create a false transition. Click a notification's **Open stream** action to open Twitch.

Settings include a global notification switch, a default for all followed channels, and **Match Twitch**. Match Twitch is off until you enable it. With Browser auto or Session token mode and a readable Twitch session, the helper checks the notification setting of each live channel on every poll. Channels enabled on Twitch, including **Always** and **Personalized**, notify here when they first go live; **Off** channels stay quiet. The plugin sends its own notification when it detects a stream and cannot reproduce Twitch's personalized delivery timing or global delivery rules. This setting reads Twitch preferences and does not change them.

Match Twitch uses Twitch's unofficial web GraphQL API because [Helix does not provide a channel notification preference endpoint](https://dev.twitch.tv/docs/api/reference/). Manual list, Export file, and Helix OAuth modes have no web session, so channels with an unknown Twitch preference stay quiet while matching is on. The same applies if preference lookup fails. A local per-channel choice can still enable notifications for one of those channels. The channel buttons cycle through **Local on → Local off → default**; in match mode, default uses Twitch's setting. Otherwise, default uses **All follows** or **Overrides only**. The global Notifications switch always takes priority. To enable matching from a terminal, run:

```bash
~/.config/omarchy/plugins/avendor7.twitch/bin/omarchy-twitch set match_twitch_notifications true
```

Data is stored in `~/.config/omarchy-twitch/` as private `config.json`, `follows.json` and `state.json` files. `state.json` contains the last stream list, live IDs, and the last read notification switches for live channels, not credentials.

## Update or remove

```bash
omarchy plugin update avendor7.twitch
omarchy plugin remove avendor7.twitch
```

Removing the plugin does not delete `~/.config/omarchy-twitch/` or the Secret Service token. Run `omarchy-twitch auth clear` before removing it if you want the token cleared.

## Development

The bar and panel are QML in `qml/`. The Python helper in `twitch_plugin/` has two provider implementations: `TwitchGQLProvider` for Twitch's web GraphQL endpoint and `TwitchHelixProvider` for the official API. Run the focused tests with:

```bash
python3 -m unittest discover -s tests -v
```

The web GraphQL API is unofficial and can change without notice. The exporter and browser-session sync depend on it. Manual and imported lists still need its public stream-status query, while Helix mode uses Twitch's documented endpoints. Reports of breakage should include the helper's error message and mode, never tokens or cookie files.

The plugin is not submitted to the Omarchy plugin marketplace.

## License

MIT. See [LICENSE](LICENSE).
