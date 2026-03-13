import React, { useEffect, useState } from "react";
import {
  Button,
  Field,
  Select,
  Spinner,
  Text,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import { ArrowDownloadRegular } from "@fluentui/react-icons";
import {
  getFinancialYears,
  getRR,
  getBR,
  type FinancialYear,
  type ReportData,
} from "../../utils/api";
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
  status: {
    marginTop: "12px",
    padding: "8px",
    borderRadius: "4px",
    backgroundColor: tokens.colorNeutralBackground3,
  },
});

interface ReportPanelProps {
  type: "rr" | "br";
  title: string;
}

/** Generate period options (YYYY-01 through YYYY-12) for a year. */
function periodsForYear(fy: FinancialYear | null): string[] {
  if (!fy) return [];
  const year = fy.from_date.substring(0, 4);
  return Array.from({ length: 12 }, (_, i) => {
    const m = String(i + 1).padStart(2, "0");
    return `${year}-${m}`;
  });
}

const ReportPanel: React.FC<ReportPanelProps> = ({ type, title }) => {
  const styles = useStyles();

  const [years, setYears] = useState<FinancialYear[]>([]);
  const [selectedYear, setSelectedYear] = useState<FinancialYear | null>(null);
  const [fromPeriod, setFromPeriod] = useState("");
  const [toPeriod, setToPeriod] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Fetch financial years on mount.
  useEffect(() => {
    getFinancialYears()
      .then((data) => {
        setYears(data);
        if (data.length > 0) {
          setSelectedYear(data[0]);
          const year = data[0].from_date.substring(0, 4);
          setFromPeriod(`${year}-01`);
          setToPeriod(`${year}-03`);
        }
      })
      .catch((err) => setError(err.message));
  }, []);

  const periods = periodsForYear(selectedYear);

  const handleYearChange = (yearId: string) => {
    const fy = years.find((y) => y.id === Number(yearId));
    if (fy) {
      setSelectedYear(fy);
      const year = fy.from_date.substring(0, 4);
      setFromPeriod(`${year}-01`);
      setToPeriod(`${year}-03`);
    }
  };

  const handleFetch = async () => {
    if (!selectedYear) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      let data: ReportData;
      let sheetName: string;

      if (type === "rr") {
        data = await getRR({
          financial_year_id: String(selectedYear.id),
          from_period: fromPeriod,
          to_period: toPeriod,
        });
        sheetName = `RR ${fromPeriod}–${toPeriod}`;
      } else {
        data = await getBR({
          financial_year_id: String(selectedYear.id),
          period: toPeriod,
        });
        sheetName = `BR ${toPeriod}`;
      }

      // Amount columns for formatting.
      const amountCols =
        type === "rr" ? ["Belopp"] : ["Saldo"];

      if (isExcelAvailable()) {
        await writeToSheet(sheetName, data.headers, data.rows, amountCols);
        setResult(
          `${data.rows.length} rader skrivna till ark "${sheetName}"`
        );
      } else {
        setResult(
          `${data.rows.length} rader hämtade (Excel ej tillgängligt)`
        );
        console.table(data.rows.slice(0, 20));
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
        <Field label="Räkenskapsår" size="small">
          <Select
            size="small"
            value={selectedYear ? String(selectedYear.id) : ""}
            onChange={(_, d) => handleYearChange(d.value)}
          >
            {years.map((fy) => (
              <option key={fy.id} value={fy.id}>
                {fy.label}
              </option>
            ))}
          </Select>
        </Field>
      </div>

      <div className={styles.section}>
        <div className={styles.row}>
          <Field label="Från period" size="small" style={{ flex: 1 }}>
            <Select
              size="small"
              value={fromPeriod}
              onChange={(_, d) => setFromPeriod(d.value)}
            >
              {periods.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label={type === "rr" ? "Till period" : "T.o.m. period"}
            size="small"
            style={{ flex: 1 }}
          >
            <Select
              size="small"
              value={toPeriod}
              onChange={(_, d) => setToPeriod(d.value)}
            >
              {periods.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </div>

      <Button
        appearance="primary"
        icon={<ArrowDownloadRegular />}
        onClick={handleFetch}
        disabled={loading || !selectedYear}
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
        <div
          className={styles.status}
          style={{ color: tokens.colorPaletteRedForeground1 }}
        >
          <Text size={200}>Fel: {error}</Text>
        </div>
      )}
    </div>
  );
};

export default ReportPanel;
