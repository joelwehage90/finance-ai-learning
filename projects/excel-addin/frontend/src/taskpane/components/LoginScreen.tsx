/**
 * Login screen — shown when the user is not authenticated.
 *
 * Provides a "Logga in med Fortnox" button that triggers the
 * OAuth flow via the Office Dialog API.
 */

import React, { useState } from "react";
import {
  Button,
  makeStyles,
  MessageBar,
  MessageBarBody,
  Title3,
  tokens,
} from "@fluentui/react-components";
import { useAuth } from "../../auth/AuthContext";

const useStyles = makeStyles({
  container: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    justifyContent: "center",
    padding: "40px 20px",
    gap: "16px",
    textAlign: "center",
    minHeight: "300px",
  },
  description: {
    color: tokens.colorNeutralForeground2,
    maxWidth: "280px",
  },
});

const LoginScreen: React.FC = () => {
  const styles = useStyles();
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      await login();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Inloggningen misslyckades");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className={styles.container}>
      <Title3>Logga in</Title3>
      <p className={styles.description}>
        Anslut ditt bokföringssystem för att hämta rapporter och fakturor direkt
        till Excel.
      </p>
      <Button
        appearance="primary"
        onClick={handleLogin}
        disabled={loading}
        size="large"
      >
        {loading ? "Loggar in..." : "Logga in med Fortnox"}
      </Button>
      {error && (
        <MessageBar intent="error">
          <MessageBarBody>{error}</MessageBarBody>
        </MessageBar>
      )}
    </div>
  );
};

export default LoginScreen;
