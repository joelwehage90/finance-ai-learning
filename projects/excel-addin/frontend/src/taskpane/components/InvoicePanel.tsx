import React, { useState } from "react";
import {
  Button,
  Checkbox,
  Field,
  Input,
  Spinner,
  Text,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowDownloadRegular } from "@fluentui/react-icons";
import { getLRK, getKRK, type TableData } from "../../utils/api";
import { writeToSheet, isExcelAvailable } from "./ExcelWriter";

const useStyles = makeStyles({
  section: {
    marginBottom: "16px",
  },
  row: {
    display: "flex",
    gap: "8px",
    marginBottom: "8px",
  },
  checkboxGroup: {
    display: "flex",
    flexWrap: "wrap",
    gap: "4px 12px",
    marginTop: "4px",
  },
  status: {
    marginTop: "12px",
    padding: "8px",
    borderRadius: "4px",
    backgroundColor: tokens.colorNeutralBackground3,
  },
});

interface StatusOption {
  value: string;
  label: string;
}

interface InvoicePanelProps {
  type: "lrk" | "krk";
  title: string;
  statusOptions: StatusOption[];
  amountColumns: string[];
}

const InvoicePanel: React.FC<InvoicePanelProps> = ({
  type,
  title,
  statusOptions,
  amountColumns,
}) => {
  const styles = useStyles();
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [selectedStatuses, setSelectedStatuses] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const toggleStatus = (value: string) => {
    setSelectedStatuses((prev) => {
      const next = new Set(prev);
      if (next.has(value)) {
        next.delete(value);
      } else {
        next.add(value);
      }
      return next;
    });
  };

  const handleFetch = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const params: Record<string, string> = {};
      if (fromDate) params.from_date = fromDate;
      if (toDate) params.to_date = toDate;
      if (selectedStatuses.size > 0) {
        params.statuses = Array.from(selectedStatuses).join(",");
      }

      const data: TableData =
        type === "lrk" ? await getLRK(params) : await getKRK(params);

      const sheetName = type === "lrk" ? "LRK" : "KRK";

      if (isExcelAvailable()) {
        await writeToSheet(sheetName, data.headers, data.rows, amountColumns);
        setResult(`${data.count} rader skrivna till ark "${sheetName}"`);
      } else {
        // Standalone browser mode — show preview.
        setResult(
          `${data.count} rader hämtade (Excel ej tillgängligt — kör i Excel för att skriva till ark)`
        );
        console.table(data.rows.slice(0, 10));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Okänt fel");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <Text size={400} weight="semibold" block style={{ marginBottom: 12 }}>
        {title}
      </Text>

      <div className={styles.section}>
        <div className={styles.row}>
          <Field label="Från" size="small" style={{ flex: 1 }}>
            <Input
              type="date"
              value={fromDate}
              onChange={(_, d) => setFromDate(d.value)}
              size="small"
            />
          </Field>
          <Field label="Till" size="small" style={{ flex: 1 }}>
            <Input
              type="date"
              value={toDate}
              onChange={(_, d) => setToDate(d.value)}
              size="small"
            />
          </Field>
        </div>
      </div>

      <div className={styles.section}>
        <Text size={300} weight="medium">
          Statusfilter:
        </Text>
        <div className={styles.checkboxGroup}>
          {statusOptions.map((opt) => (
            <Checkbox
              key={opt.value}
              label={opt.label}
              checked={selectedStatuses.has(opt.value)}
              onChange={() => toggleStatus(opt.value)}
            />
          ))}
        </div>
      </div>

      <Button
        appearance="primary"
        icon={<ArrowDownloadRegular />}
        onClick={handleFetch}
        disabled={loading}
        size="medium"
      >
        {loading ? <Spinner size="tiny" /> : "Hämta till Excel"}
      </Button>

      {result && (
        <div className={styles.status}>
          <Text size={200}>{result}</Text>
        </div>
      )}
      {error && (
        <div className={styles.status} style={{ color: tokens.colorPaletteRedForeground1 }}>
          <Text size={200}>Fel: {error}</Text>
        </div>
      )}
    </div>
  );
};

export default InvoicePanel;
