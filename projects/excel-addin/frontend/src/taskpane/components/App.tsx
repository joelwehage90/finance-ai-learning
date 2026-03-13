import React, { useState } from "react";
import {
  Tab,
  TabList,
  SelectTabEvent,
  SelectTabData,
  makeStyles,
  Title3,
  tokens,
} from "@fluentui/react-components";
import InvoicePanel from "./InvoicePanel";
import ReportPanel from "./ReportPanel";

const useStyles = makeStyles({
  root: {
    display: "flex",
    flexDirection: "column",
    height: "100vh",
    fontFamily: tokens.fontFamilyBase,
  },
  header: {
    padding: "12px 16px 0",
    borderBottom: `1px solid ${tokens.colorNeutralStroke1}`,
  },
  content: {
    flex: 1,
    overflow: "auto",
    padding: "16px",
  },
});

type TabValue = "lrk" | "krk" | "rr" | "br";

const App: React.FC = () => {
  const styles = useStyles();
  const [activeTab, setActiveTab] = useState<TabValue>("lrk");

  const onTabSelect = (_: SelectTabEvent, data: SelectTabData) => {
    setActiveTab(data.value as TabValue);
  };

  return (
    <div className={styles.root}>
      <div className={styles.header}>
        <Title3>Fortnox → Excel</Title3>
        <TabList
          selectedValue={activeTab}
          onTabSelect={onTabSelect}
          size="small"
          style={{ marginTop: 8 }}
        >
          <Tab value="lrk">LRK</Tab>
          <Tab value="krk">KRK</Tab>
          <Tab value="rr">RR</Tab>
          <Tab value="br">BR</Tab>
        </TabList>
      </div>

      <div className={styles.content}>
        {activeTab === "lrk" && (
          <InvoicePanel
            type="lrk"
            title="Leverantörsreskontra"
            statusOptions={[
              { value: "booked", label: "Bokförda" },
              { value: "unbooked", label: "Ej bokförda" },
              { value: "unpaid", label: "Obetalda" },
              { value: "fullypaid", label: "Betalda" },
              { value: "cancelled", label: "Makulerade" },
              { value: "unpaidoverdue", label: "Förfallna" },
            ]}
            amountColumns={["Belopp", "Saldo"]}
          />
        )}
        {activeTab === "krk" && (
          <InvoicePanel
            type="krk"
            title="Kundreskontra"
            statusOptions={[
              { value: "booked", label: "Bokförda" },
              { value: "unbooked", label: "Ej bokförda" },
              { value: "unpaid", label: "Obetalda" },
              { value: "fullypaid", label: "Betalda" },
              { value: "cancelled", label: "Makulerade" },
              { value: "unpaidoverdue", label: "Förfallna" },
            ]}
            amountColumns={["Belopp", "Saldo"]}
          />
        )}
        {activeTab === "rr" && <ReportPanel type="rr" title="Resultaträkning" />}
        {activeTab === "br" && <ReportPanel type="br" title="Balansräkning" />}
      </div>
    </div>
  );
};

export default App;
