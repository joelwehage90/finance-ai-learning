/**
 * OAuth dialog — runs inside Office.context.ui.displayDialogAsync().
 *
 * 1. Fetches provider OAuth config from the backend
 * 2. Redirects to the provider's OAuth consent page
 * 3. The provider redirects back to callback.html with ?code=...
 */

/* global Office */

const API_BASE = process.env.API_BASE_URL || "http://localhost:8000/api";

async function startOAuth(): Promise<void> {
  // Provider type could be parameterized via URL hash in the future.
  const providerType = "fortnox";

  // Fetch OAuth config from backend.
  const configResp = await fetch(`${API_BASE}/auth/config/${providerType}`);
  if (!configResp.ok) {
    document.body.textContent = "Kunde inte ladda inloggningsinställningar.";
    return;
  }
  const config = await configResp.json();

  // Build redirect URI pointing to our callback page (same origin as dialog).
  const callbackUrl = new URL("callback.html", window.location.href).toString();

  // Build OAuth URL.
  const authUrl = new URL(config.auth_url);
  authUrl.searchParams.set("client_id", config.client_id);
  authUrl.searchParams.set("redirect_uri", callbackUrl);
  authUrl.searchParams.set("scope", config.scopes);
  authUrl.searchParams.set("state", providerType);
  authUrl.searchParams.set("response_type", "code");

  // Redirect the dialog to the OAuth provider.
  window.location.href = authUrl.toString();
}

Office.onReady(() => {
  startOAuth();
});
