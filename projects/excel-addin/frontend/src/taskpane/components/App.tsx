import React from "react";
import { makeStyles, Title3, tokens } from "@fluentui/react-components";
import ExportPanel from "./ExportPanel";

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

const App: React.FC = () => {
  const styles = useStyles();

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <Title3>Fortnox → Excel</Title3>
      </div>

      <div className={styles.content}>
        <ExportPanel />
      </div>
    </div>
  );
};

export default App;
