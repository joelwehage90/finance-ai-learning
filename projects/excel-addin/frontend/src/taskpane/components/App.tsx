import React from "react";
import { makeStyles, Title3, tokens } from "@fluentui/react-components";
import { AuthProvider, useAuth } from "../../auth/AuthContext";
import ExportPanel from "./ExportPanel";
import LoginScreen from "./LoginScreen";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    fontFamily: tokens.fontFamilyBase,
  },
  header: {
    padding: "12px 16px",
    borderBottom: `1px solid ${tokens.colorNeutralStroke1}`,
  },
  content: {
    flex: 1,
    overflow: "auto",
    padding: "16px",
  },
});

const AppContent: React.FC = () => {
  const styles = useStyles();
  const { isAuthenticated, companyName } = useAuth();

  if (!isAuthenticated) {
    return <LoginScreen />;
  }

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <Title3>{companyName || "Bokföring"} → Excel</Title3>
      </div>

      <div className={styles.content}>
        <ExportPanel />
      </div>
    </div>
  );
};

const App: React.FC = () => (
  <AuthProvider>
    <AppContent />
  </AuthProvider>
);

export default App;
