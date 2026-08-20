// Grand Meridian console — access-token acquisition.
//
// Exposes window.GM_AUTH with:
//   init()            -> resolves the runtime config (mode, agent URL, guest)
//   authHeaders()     -> {} in no-auth mode, {Authorization: "Bearer …"} otherwise
//   state()           -> {mode, ready, reason} for the UI to render
//   signIn()          -> pkce mode only: starts the redirect
//
// Three modes, decided by the server, not by this file:
//
//   none    No token. The browser calls the agent directly. Only valid against
//           an unprotected agent.
//   broker  Fetch a token from this site's own /auth/token. The OAuth2 client
//           secret lives on the dev server, never here. Cached until shortly
//           before expiry.
//   pkce    Authorization code + PKCE against the IdP. No secret anywhere.
//           Correct shape for a public client.
//
// The agent performs no authentication of its own. The platform gateway in
// front of it validates the token. This file's only job is to obtain one and
// attach it; if it is missing or wrong, the gateway rejects the call and the
// widget surfaces that.
(() => {
  "use strict";

  const LS_VERIFIER = "gmPkceVerifier";
  const LS_TOKEN = "gmPkceToken";

  let config = null;
  let cached = null; // {token, expiresAt}

  // ---- config ----------------------------------------------------------
  // Served by web/serve.py. Falls back to a window global so the page still
  // works behind a plain static file server, in no-auth mode only.
  async function init() {
    try {
      const res = await fetch("/auth/config", { cache: "no-store" });
      if (res.ok) {
        config = await res.json();
        return config;
      }
    } catch (_) {}
    config = {
      mode: "none",
      agentUrl: window.GRAND_MERIDIAN_AGENT_URL || "http://127.0.0.1:8000/chat",
      guest: window.GRAND_MERIDIAN_GUEST || { id: "", name: "" },
      _fallback: true,
    };
    return config;
  }

  const cfg = () => config || { mode: "none", guest: {} };

  // A single load can override the guest, which makes the cross-user cases
  // drivable from the browser: ?guest=guest-marcus asks as someone else.
  // Client-asserted, so it proves nothing about identity - that is the point.
  function guest() {
    const g = { ...(cfg().guest || {}) };
    try {
      const q = new URLSearchParams(location.search);
      if (q.get("guest")) { g.id = q.get("guest"); g.name = q.get("guest_name") || g.id; }
    } catch (_) {}
    return g;
  }

  // ---- broker ----------------------------------------------------------
  async function brokerToken() {
    if (cached && Date.now() < cached.expiresAt - 30000) return cached.token;
    const res = await fetch("/auth/token", { method: "POST" });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.access_token) {
      const why = body.detail || body.error || `HTTP ${res.status}`;
      throw new Error(`could not obtain an access token: ${why}`);
    }
    cached = {
      token: body.access_token,
      expiresAt: Date.now() + (Number(body.expires_in) || 300) * 1000,
    };
    return cached.token;
  }

  // ---- pkce ------------------------------------------------------------
  function randomString(bytes) {
    const a = new Uint8Array(bytes);
    crypto.getRandomValues(a);
    return btoa(String.fromCharCode(...a)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  async function challengeFor(verifier) {
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    return btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  async function signIn() {
    const c = cfg();
    if (!c.authorizeUrl || !c.clientId) {
      throw new Error("pkce mode needs OAUTH_AUTHORIZE_URL and OAUTH_CLIENT_ID in dev/web.env");
    }
    const verifier = randomString(48);
    sessionStorage.setItem(LS_VERIFIER, verifier);
    const params = new URLSearchParams({
      response_type: "code",
      client_id: c.clientId,
      redirect_uri: c.redirectUri || location.origin + "/",
      code_challenge: await challengeFor(verifier),
      code_challenge_method: "S256",
      state: randomString(16),
    });
    if (c.scopes) params.set("scope", c.scopes);
    location.assign(`${c.authorizeUrl}?${params}`);
  }

  // Exchange the code if we came back from the IdP. Done in the browser
  // because a public client has no secret to protect.
  async function completePkceRedirect() {
    let code = null;
    try { code = new URLSearchParams(location.search).get("code"); } catch (_) {}
    if (!code) return false;
    const c = cfg();
    const verifier = sessionStorage.getItem(LS_VERIFIER) || "";
    sessionStorage.removeItem(LS_VERIFIER);
    const res = await fetch(c.tokenUrl, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        code,
        client_id: c.clientId,
        redirect_uri: c.redirectUri || location.origin + "/",
        code_verifier: verifier,
      }),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.access_token) {
      throw new Error(body.error_description || body.error || `token exchange failed (HTTP ${res.status})`);
    }
    cached = { token: body.access_token, expiresAt: Date.now() + (Number(body.expires_in) || 300) * 1000 };
    try { sessionStorage.setItem(LS_TOKEN, JSON.stringify(cached)); } catch (_) {}
    // Drop code and state from the address bar so a reload does not re-exchange.
    history.replaceState({}, "", location.pathname);
    return true;
  }

  function restorePkceToken() {
    try {
      const raw = sessionStorage.getItem(LS_TOKEN);
      if (!raw) return;
      const saved = JSON.parse(raw);
      if (saved && saved.token && Date.now() < saved.expiresAt - 30000) cached = saved;
    } catch (_) {}
  }

  // ---- public ----------------------------------------------------------
  async function authHeaders() {
    const mode = cfg().mode;
    if (mode === "none") return {};
    if (mode === "broker") return { Authorization: `Bearer ${await brokerToken()}` };
    if (mode === "pkce") {
      if (cached && Date.now() < cached.expiresAt - 30000) {
        return { Authorization: `Bearer ${cached.token}` };
      }
      throw new Error("not signed in");
    }
    throw new Error(`unknown auth mode ${mode}`);
  }

  function state() {
    const c = cfg();
    if (c.mode === "none") {
      return { mode: "none", ready: true, reason: c._fallback ? "no dev server; running unsecured" : "" };
    }
    if (c.mode === "broker") {
      return {
        mode: "broker",
        ready: !!c.brokerReady,
        reason: c.brokerReady ? "" : "token broker not configured — fill in dev/web.env",
      };
    }
    if (c.mode === "pkce") {
      const signedIn = !!(cached && Date.now() < cached.expiresAt - 30000);
      return { mode: "pkce", ready: signedIn, reason: signedIn ? "" : "sign in required" };
    }
    return { mode: c.mode, ready: false, reason: "unknown mode" };
  }

  window.GM_AUTH = {
    init: async () => {
      await init();
      if (cfg().mode === "pkce") {
        restorePkceToken();
        try { await completePkceRedirect(); } catch (e) { console.warn("pkce exchange failed", e); }
      }
      return cfg();
    },
    authHeaders,
    state,
    signIn,
    guest,
    agentUrl: () => cfg().agentUrl,
  };
})();
