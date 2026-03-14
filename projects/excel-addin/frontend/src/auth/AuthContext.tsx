/**
 * Auth context — manages OAuth state and provides login/logout
 * functionality via the Office Dialog API.
 *
 * The login flow:
 * 1. Opens dialog.html via displayDialogAsync()
 * 2. dialog.html redirects to the OAuth provider
 * 3. Provider redirects back to callback.html with auth code
 * 4. callback.html sends the code to taskpane via messageParent()
 * 5. Taskpane POSTs the code to backend /api/auth/callback
 * 6. Backend returns a JWT session token
 *
 * SECURITY NOTE (S12): The JWT is stored in a module-level JS variable
 * (not an HttpOnly cookie) because Office add-in taskpanes run in
 * sandboxed iframes where cookies are partitioned (Chromium 115+).
 * This is a known trade-off: XSS prevention is critical since any
 * XSS vulnerability could steal the token.
 */

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { setAuthToken } from "../utils/api";

/* global Office */

interface AuthState {
  token: string | null;
  companyName: string | null;
  providerType: string | null;
  isAuthenticated: boolean;
}

interface AuthContextType extends AuthState {
  login: () => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

const API_BASE = process.env.API_BASE_URL || "http://localhost:8000/api";

/** Max retries for server-side logout (S21). */
const LOGOUT_MAX_RETRIES = 2;

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [state, setState] = useState<AuthState>({
    token: null,
    companyName: null,
    providerType: null,
    isAuthenticated: false,
  });

  // Sync auth token to API client whenever it changes.
  useEffect(() => {
    setAuthToken(state.token);
  }, [state.token]);

  const login = useCallback(async () => {
    // Build dialog URL relative to current page.
    const dialogUrl = new URL("dialog.html", window.location.href).toString();

    return new Promise<void>((resolve, reject) => {
      Office.context.ui.displayDialogAsync(
        dialogUrl,
        { height: 60, width: 40 },
        (result) => {
          if (result.status !== Office.AsyncResultStatus.Succeeded) {
            reject(new Error("Could not open login dialog"));
            return;
          }

          const dialog = result.value;

          dialog.addEventHandler(
            Office.EventType.DialogMessageReceived,
            async (args: { message?: string; error?: number }) => {
              dialog.close();

              if (args.error || !args.message) {
                reject(new Error(`Dialog error: ${args.error}`));
                return;
              }

              const message = JSON.parse(args.message);

              if (message.type === "oauth_error") {
                reject(new Error(message.error));
                return;
              }

              if (message.type === "oauth_callback") {
                try {
                  // Exchange code for session token via backend.
                  // S5: The state contains "providerType:nonce" — the
                  // backend extracts the provider type from the state.
                  const resp = await fetch(`${API_BASE}/auth/callback`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                      code: message.code,
                      state: message.state,
                      redirect_uri: message.redirect_uri,
                    }),
                  });

                  if (!resp.ok) {
                    reject(new Error("Authentication failed"));
                    return;
                  }

                  const session = await resp.json();
                  setState({
                    token: session.token,
                    companyName: session.company_name,
                    providerType: session.provider_type,
                    isAuthenticated: true,
                  });
                  resolve();
                } catch (err) {
                  reject(err);
                }
              }
            },
          );

          dialog.addEventHandler(
            Office.EventType.DialogEventReceived,
            () => {
              reject(new Error("Dialog closed by user"));
            },
          );
        },
      );
    });
  }, []);

  const logout = useCallback(() => {
    // S15: Send JWT in Authorization header for proper caller verification.
    // S21: Retry on failure so session gets revoked server-side.
    if (state.token) {
      const token = state.token;
      const attemptLogout = (retries: number) => {
        fetch(`${API_BASE}/auth/logout`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ token }),
        }).catch(() => {
          if (retries > 0) {
            setTimeout(() => attemptLogout(retries - 1), 1000);
          }
          // After all retries fail, the session will expire naturally
          // via JWT expiry (24h). This is an accepted degradation.
        });
      };
      attemptLogout(LOGOUT_MAX_RETRIES);
    }

    setState({
      token: null,
      companyName: null,
      providerType: null,
      isAuthenticated: false,
    });
  }, [state.token]);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
};
