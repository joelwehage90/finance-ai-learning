/**
 * OAuth callback — receives the authorization code from the provider
 * and sends it to the taskpane via Office.context.ui.messageParent().
 *
 * IMPORTANT: Does NOT use localStorage (partitioned in iframes since
 * Chromium 115+). All communication goes through messageParent.
 *
 * The state parameter contains "providerType:nonce" (S5) which is
 * forwarded to the taskpane for CSRF verification.
 */

/* global Office */

Office.onReady(() => {
  const params = new URLSearchParams(window.location.search);
  const code = params.get("code");
  const state = params.get("state");
  const error = params.get("error");

  if (error) {
    Office.context.ui.messageParent(
      JSON.stringify({ type: "oauth_error", error }),
    );
    return;
  }

  if (code) {
    Office.context.ui.messageParent(
      JSON.stringify({
        type: "oauth_callback",
        code,
        state, // Contains "providerType:nonce" for CSRF verification.
        redirect_uri: window.location.origin + window.location.pathname,
      }),
    );
  }
});
