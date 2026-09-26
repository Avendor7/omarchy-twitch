// Run on twitch.tv/directory/following in your browser's developer console.
// This script sends your browser's existing session token only to Twitch's
// GraphQL endpoint. The downloaded JSON contains channel logins only.
(async () => {
  const token = window.localStorage.getItem("auth-token");
  if (!token) throw new Error("Sign in to Twitch first");
  const endpoint = "https://gql.twitch.tv/gql";
  const headers = {
    "Client-Id": "kimne78kx3ncx6brgo4mv6wki5h1ko",
    "Authorization": "OAuth " + token,
    "Content-Type": "application/json"
  };
  const integrityResponse = await fetch("https://gql.twitch.tv/integrity", {
    method: "POST", headers
  });
  if (!integrityResponse.ok) throw new Error("Twitch integrity check failed");
  const integrity = await integrityResponse.json();
  if (!integrity.token) throw new Error("Twitch did not issue an integrity token");
  headers["Client-Integrity"] = integrity.token;
  async function query(source, variables) {
    const response = await fetch(endpoint, {
      method: "POST", headers,
      body: JSON.stringify({ query: source, variables })
    });
    if (!response.ok) throw new Error("Twitch returned HTTP " + response.status);
    const payload = await response.json();
    if (payload.errors?.length) throw new Error(payload.errors[0].message);
    return payload.data;
  }
  const me = await query("query { currentUser { login } }", {});
  if (!me.currentUser?.login) throw new Error("Twitch session has no current user");
  const source = `query TwitchFollows($login: String!, $after: Cursor) {
    user(login: $login) { follows(first: 100, after: $after) {
      edges { cursor node { login } } pageInfo { hasNextPage }
    } }
  }`;
  const channels = [];
  let after = null;
  for (let page = 0; page < 100; page++) {
    const data = await query(source, { login: me.currentUser.login, after });
    const follows = data.user?.follows;
    if (!follows) throw new Error("Twitch did not return a follow list");
    for (const edge of follows.edges || []) {
      if (edge.node?.login) channels.push(edge.node.login);
    }
    if (!follows.pageInfo?.hasNextPage) break;
    const next = follows.edges?.at(-1)?.cursor;
    if (!next || next === after) throw new Error("Pagination stopped unexpectedly");
    after = next;
  }
  const blob = new Blob([JSON.stringify({ channels: [...new Set(channels)] }, null, 2) + "\n"],
    { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "twitch-follows.json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  console.log(`Exported ${channels.length} followed channels`);
})();
