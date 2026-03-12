"""One-time OAuth2 setup for Fortnox integration.

Run this script once to authorize your integration and obtain
the TenantId needed for Client Credentials authentication.

Usage:
    1. Copy .env.example to .env and fill in FORTNOX_CLIENT_ID and
       FORTNOX_CLIENT_SECRET from the Fortnox Developer Portal.
    2. Set FORTNOX_REDIRECT_URI below to match the one registered
       in the Developer Portal.
    3. Run: python auth_setup.py
    4. A browser window opens — log in to Fortnox and approve scopes.
    5. The script captures the authorization code, exchanges it for
       tokens, extracts TenantId, and saves it to .env.
"""

import base64
import json
import os
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

import httpx
from dotenv import load_dotenv

load_dotenv()

# Configuration — adjust these as needed
REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}/callback"
SCOPES = "companyinformation bookkeeping invoice customer supplier supplierinvoice costcenter project"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP handler that captures the OAuth authorization code."""

    auth_code: str | None = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<h1>Auktorisering klar!</h1>"
                "<p>Du kan stänga denna flik och gå tillbaka till terminalen.</p>"
                .encode("utf-8")
            )
        else:
            error = params.get("error", ["unknown"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                f"<h1>Fel: {error}</h1><p>Försök igen.</p>".encode("utf-8")
            )

    def log_message(self, format, *args):
        # Suppress default request logging
        pass


def decode_jwt_payload(token: str) -> dict:
    """Decode JWT payload without verification (we only need TenantId)."""
    payload_b64 = token.split(".")[1]
    # Add padding if needed
    padding = 4 - len(payload_b64) % 4
    if padding != 4:
        payload_b64 += "=" * padding
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    return json.loads(payload_bytes)


def main():
    client_id = os.environ.get("FORTNOX_CLIENT_ID")
    client_secret = os.environ.get("FORTNOX_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("Fel: Sätt FORTNOX_CLIENT_ID och FORTNOX_CLIENT_SECRET i .env")
        print("Kopiera .env.example till .env och fyll i värdena.")
        return

    # Step 1: Build authorization URL and open browser
    auth_params = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": "setup",
        "access_type": "offline",
        "response_type": "code",
        "account_type": "service",
    })
    auth_url = f"https://apps.fortnox.se/oauth-v1/auth?{auth_params}"

    print(f"Öppnar Fortnox-inloggning i webbläsaren...")
    print(f"Om webbläsaren inte öppnas, gå till:\n{auth_url}\n")
    webbrowser.open(auth_url)

    # Step 2: Start local server and wait for callback
    print(f"Väntar på callback på http://localhost:{REDIRECT_PORT}/callback ...")
    server = HTTPServer(("localhost", REDIRECT_PORT), OAuthCallbackHandler)
    server.handle_request()  # Handle one request, then stop

    auth_code = OAuthCallbackHandler.auth_code
    if not auth_code:
        print("Fel: Ingen authorization code mottagen.")
        return

    print(f"Authorization code mottagen!")

    # Step 3: Exchange code for tokens
    credentials = base64.b64encode(
        f"{client_id}:{client_secret}".encode()
    ).decode()

    with httpx.Client() as http:
        response = http.post(
            "https://apps.fortnox.se/oauth-v1/token",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Authorization": f"Basic {credentials}",
            },
            data={
                "grant_type": "authorization_code",
                "code": auth_code,
                "redirect_uri": REDIRECT_URI,
            },
        )

        if response.status_code != 200:
            print(f"Fel vid token-utbyte: {response.status_code}")
            print(response.text)
            return

        token_data = response.json()

    access_token = token_data["access_token"]
    print("Access token mottagen!")

    # Step 4: Extract TenantId from JWT
    jwt_payload = decode_jwt_payload(access_token)
    tenant_id = jwt_payload.get("tenantId") or jwt_payload.get("TenantId")

    if not tenant_id:
        # Fallback: fetch from company information endpoint
        print("TenantId ej i JWT, hämtar från /3/companyinformation ...")
        with httpx.Client() as http:
            response = http.get(
                "https://api.fortnox.se/3/companyinformation",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                },
            )
            if response.status_code == 200:
                company = response.json().get("CompanyInformation", {})
                tenant_id = company.get("DatabaseNumber")

    if not tenant_id:
        print("Fel: Kunde inte hämta TenantId. Kontrollera dina scopes.")
        return

    # Step 5: Save TenantId to .env
    env_path = os.path.join(os.path.dirname(__file__), ".env")

    # Read existing .env or create from example
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            env_content = f.read()
    else:
        example_path = os.path.join(os.path.dirname(__file__), ".env.example")
        with open(example_path, "r") as f:
            env_content = f.read()

    # Update or add FORTNOX_TENANT_ID
    if "FORTNOX_TENANT_ID=" in env_content:
        lines = env_content.split("\n")
        lines = [
            f"FORTNOX_TENANT_ID={tenant_id}" if l.startswith("FORTNOX_TENANT_ID=") else l
            for l in lines
        ]
        env_content = "\n".join(lines)
    else:
        env_content += f"\nFORTNOX_TENANT_ID={tenant_id}\n"

    with open(env_path, "w") as f:
        f.write(env_content)

    print(f"\nKlart! TenantId: {tenant_id}")
    print(f"Sparat till {env_path}")
    print(f"\nDu kan nu starta MCP-servern:")
    print(f"  python fortnox_server.py")


if __name__ == "__main__":
    main()
